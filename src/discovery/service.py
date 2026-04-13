"""
数据库发现与纳管服务

编排扫描、识别、注册全流程。
R1: 基础编排，R3+集成知识库
"""

import asyncio
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Callable

from .scanner import DatabaseScanner, DiscoveredInstance
from .identifier import DatabaseIdentifier, IdentifiedInstance
from .registry import LocalRegistry, ManagedInstance
from .knowledge_base import LocalKnowledgeBase

logger = logging.getLogger(__name__)


@dataclass
class OnboardingResult:
    """纳管结果"""
    session_id: str
    started_at: str
    finished_at: Optional[str] = None
    discovered: List[DiscoveredInstance] = field(default_factory=list)
    identified: List[IdentifiedInstance] = field(default_factory=list)
    registered: List[ManagedInstance] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    new_count: int = 0
    changed_count: int = 0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "discovered_count": len(self.discovered),
            "identified_count": len(self.identified),
            "registered_count": len(self.registered),
            "new_count": self.new_count,
            "changed_count": self.changed_count,
            "errors": self.errors,
        }


class DiscoveryService:
    """
    数据库发现与纳管服务

    编排完整纳管流程：
    1. scan() → 扫描本地数据库
    2. identify() → 识别类型和版本
    3. register() → 注册到SQLite
    4. enrich() → 写入ChromaDB知识库（R3+）

    Attributes:
        registry: 本地注册表
        knowledge_base: 知识库（可选）
        scanner: 数据库扫描器
        identifier: 数据库识别器
    """

    def __init__(
        self,
        registry: Optional[LocalRegistry] = None,
        knowledge_base: Optional[LocalKnowledgeBase] = None,
        scanner: Optional[DatabaseScanner] = None,
        identifier: Optional[DatabaseIdentifier] = None,
    ):
        """
        初始化发现服务

        Args:
            registry: 本地注册表，默认创建新实例
            knowledge_base: 知识库，默认创建新实例
            scanner: 扫描器，默认创建新实例
            identifier: 识别器，默认创建新实例
        """
        self.registry = registry or LocalRegistry()
        self.kb = knowledge_base
        self.scanner = scanner or DatabaseScanner()
        self.identifier = identifier or DatabaseIdentifier()
        self._running = False

    async def discover_and_onboard(
        self,
        auto_onboard: bool = True,
        capture_knowledge: bool = False,
    ) -> OnboardingResult:
        """
        完整的发现与纳管流程

        Args:
            auto_onboard: 是否自动纳管（注册到SQLite）
            capture_knowledge: 是否捕获知识（写入ChromaDB，R3+）

        Returns:
            OnboardingResult: 纳管结果详情
        """
        session_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        result = OnboardingResult(session_id=session_id, started_at=started_at)

        try:
            # 创建扫描会话
            self.registry.create_scan_session(session_id)

            # Step 1: 扫描
            discovered = await self.scanner.scan_local()
            result.discovered = discovered

            if not discovered:
                logger.info(f"Session {session_id}: No database instances found")
                self.registry.finish_scan_session(
                    session_id,
                    instances_found=0,
                    instances_new=0,
                )
                result.finished_at = datetime.now(timezone.utc).isoformat()
                return result

            # Step 2: 识别
            identified = await self.identifier.identify_all(discovered)
            result.identified = identified

            # 过滤识别失败的
            identified = [i for i in identified if i.instance.status == "identified"]
            if not identified:
                logger.warning(f"Session {session_id}: Failed to identify any instances")
                self.registry.finish_scan_session(
                    session_id,
                    instances_found=len(discovered),
                    instances_new=0,
                    error_message="Failed to identify instances",
                )
                result.finished_at = datetime.now(timezone.utc).isoformat()
                return result

            # Step 3: 注册
            new_count = 0
            for ident_inst in identified:
                # 检查是否已存在
                existing = self.registry.get_by_key(
                    ident_inst.instance.db_type.value,
                    ident_inst.instance.host,
                    ident_inst.instance.port,
                )

                managed = ManagedInstance.from_identified(
                    ident_inst,
                    status="onboarded" if auto_onboard else "discovered"
                )

                if existing:
                    # 更新现有实例
                    instance_id = existing.id
                    managed.id = instance_id
                    self.registry.register(managed)
                else:
                    # 注册新实例
                    instance_id = self.registry.register(managed)
                    managed.id = instance_id
                    new_count += 1

                result.registered.append(managed)

                # Step 4: 知识库充实（R3+）
                if capture_knowledge and self.kb and auto_onboard:
                    await self._capture_instance_knowledge(managed, ident_inst)

            result.new_count = new_count
            result.changed_count = len(result.registered) - new_count

            # 完成扫描会话
            self.registry.finish_scan_session(
                session_id,
                instances_found=len(discovered),
                instances_new=new_count,
                instances_changed=result.changed_count,
            )

        except Exception as e:
            logger.exception(f"Session {session_id}: Error during discovery: {e}")
            result.errors.append(str(e))
            self.registry.finish_scan_session(
                session_id,
                instances_found=len(result.discovered),
                instances_new=result.new_count,
                error_message=str(e),
            )

        result.finished_at = datetime.now(timezone.utc).isoformat()
        return result

    async def discover_only(self) -> List[DiscoveredInstance]:
        """
        仅执行发现扫描，不注册

        Returns:
            发现的实例列表
        """
        return await self.scanner.scan_local()

    async def identify_only(
        self, instances: List[DiscoveredInstance]
    ) -> List[IdentifiedInstance]:
        """
        仅执行识别，不注册

        Args:
            instances: 待识别的实例列表

        Returns:
            识别后的实例列表
        """
        return await self.identifier.identify_all(instances)

    async def _capture_instance_knowledge(
        self, managed: ManagedInstance, identified: IdentifiedInstance
    ):
        """捕获实例知识（schema + config）"""
        if not self.kb:
            return

        try:
            if managed.db_type == "postgresql":
                await self._capture_pg_knowledge(managed)
            elif managed.db_type in ("mysql", "mariadb"):
                await self._capture_mysql_knowledge(managed)
        except Exception as e:
            # 知识捕获失败不影响主流程
            logger.warning(f"Failed to capture knowledge for {managed.id}: {e}")

    async def _capture_pg_knowledge(self, managed: ManagedInstance):
        """捕获PostgreSQL schema和配置"""
        try:
            import asyncpg
            from .knowledge_base import SchemaKnowledge, ConfigKnowledge

            # 尝试连接多个数据库查找用户表
            databases_to_try = ["postgres", "javis_test_db", "template1"]
            all_tables = []
            connected_db = None
            conn = None

            for db_name in databases_to_try:
                try:
                    conn = await asyncpg.connect(
                        host=managed.host,
                        port=managed.port,
                        database=db_name,
                        timeout=10.0,
                    )
                    connected_db = db_name
                    break
                except Exception:
                    continue

            if not conn:
                logger.warning(f"Could not connect to any database for {managed.id}")
                return

            try:
                # 获取schema信息 - 使用pg_tables和pg_stat_user_tables联合
                # 注意：pg_tables是实例级别的，可以跨数据库查询
                rows = await conn.fetch("""
                    SELECT
                        t.schemaname,
                        t.tablename,
                        t.tableowner,
                        COALESCE(s.n_live_tup, 0)::bigint as row_count,
                        pg_total_relation_size(t.schemaname||'.'||t.tablename)::bigint as size_bytes
                    FROM pg_tables t
                    LEFT JOIN pg_stat_user_tables s
                        ON t.schemaname = s.schemaname AND t.tablename = s.relname
                    WHERE t.schemaname NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY size_bytes DESC
                    LIMIT 100
                """)

                for t in rows:
                    all_tables.append({
                        "table_name": f"{t['schemaname']}.{t['tablename']}",
                        "owner": t["tableowner"],
                        "row_count": t["row_count"],
                        "size_bytes": t["size_bytes"],
                        "columns": [],
                    })
                
                # 如果没有找到表，尝试连接其他数据库
                if not all_tables and connected_db == "postgres":
                    await conn.close()
                    for db_name in ["javis_test_db", "zcloud_agent_test"]:
                        try:
                            conn = await asyncpg.connect(
                                host=managed.host,
                                port=managed.port,
                                database=db_name,
                                timeout=10.0,
                            )
                            rows = await conn.fetch("""
                                SELECT
                                    t.schemaname,
                                    t.tablename,
                                    t.tableowner,
                                    COALESCE(s.n_live_tup, 0)::bigint as row_count,
                                    pg_total_relation_size(t.schemaname||'.'||t.tablename)::bigint as size_bytes
                                FROM pg_tables t
                                LEFT JOIN pg_stat_user_tables s
                                    ON t.schemaname = s.schemaname AND t.tablename = s.relname
                                WHERE t.schemaname NOT IN ('pg_catalog', 'information_schema')
                                ORDER BY size_bytes DESC
                                LIMIT 100
                            """)
                            for t in rows:
                                all_tables.append({
                                    "table_name": f"{t['schemaname']}.{t['tablename']}",
                                    "owner": t["tableowner"],
                                    "row_count": t["row_count"],
                                    "size_bytes": t["size_bytes"],
                                    "columns": [],
                                })
                            if all_tables:
                                connected_db = db_name
                                break
                        except Exception:
                            continue

                # 获取配置参数
                params = await conn.fetch("""
                    SELECT name, setting, unit
                    FROM pg_settings
                    WHERE context IN ('postmaster', 'sighup')
                    AND name NOT LIKE 'pg_%'
                    ORDER BY name
                """)

                from .knowledge_base import SchemaKnowledge, ConfigKnowledge

                # 写入知识库
                self.kb.add_schema(SchemaKnowledge(
                    instance_id=managed.id,
                    db_name=connected_db or "postgres",
                    tables=all_tables,
                    indexes=[],
                    version=managed.version,
                    captured_at=datetime.now(timezone.utc).isoformat(),
                ))

                self.kb.add_config(ConfigKnowledge(
                    instance_id=managed.id,
                    db_type="postgresql",
                    version=managed.version,
                    parameters={p["name"]: str(p["setting"]) for p in params},
                    captured_at=datetime.now(timezone.utc).isoformat(),
                ))
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(f"Failed to capture PG knowledge for {managed.id}: {e}")

    async def _capture_mysql_knowledge(self, managed: ManagedInstance):
        """捕获MySQL schema和配置"""
        try:
            import aiomysql

            conn = await aiomysql.connect(
                host=managed.host,
                port=managed.port,
                connect_timeout=10.0,
            )
            try:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    # 获取数据库列表
                    await cursor.execute("SHOW DATABASES")
                    databases = await cursor.fetchall()
                    
                    all_tables = []
                    
                    for db_row in databases:
                        db_name = db_row.get("Database", db_row.get("database"))
                        if db_name in ("information_schema", "performance_schema", "mysql", "sys"):
                            continue
                        
                        # 获取表信息
                        await cursor.execute(
                            """
                            SELECT 
                                TABLE_SCHEMA as db_name,
                                TABLE_NAME as table_name,
                                TABLE_ROWS as row_count,
                                ROUND(DATA_LENGTH + INDEX_LENGTH) as size_bytes,
                                TABLE_TYPE,
                                ENGINE
                            FROM information_schema.TABLES
                            WHERE TABLE_SCHEMA = %s
                            AND TABLE_TYPE = 'BASE TABLE'
                            ORDER BY (DATA_LENGTH + INDEX_LENGTH) DESC
                            LIMIT 100
                            """,
                            (db_name,)
                        )
                        tables = await cursor.fetchall()
                        
                        for t in tables:
                            all_tables.append({
                                "table_name": f"{t['db_name']}.{t['table_name']}",
                                "engine": t.get("ENGINE", ""),
                                "row_count": t.get("row_count", 0) or 0,
                                "size_bytes": t.get("size_bytes", 0) or 0,
                                "columns": [],
                            })
                        
                        # 获取列信息（前10个表）
                        if len(all_tables) <= 10:
                            for t in tables[:10]:
                                await cursor.execute(
                                    """
                                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
                                    FROM information_schema.COLUMNS
                                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                                    ORDER BY ORDINAL_POSITION
                                    """,
                                    (db_name, t['table_name'])
                                )
                                columns = await cursor.fetchall()
                                for entry in all_tables:
                                    if entry["table_name"] == f"{db_name}.{t['table_name']}":
                                        entry["columns"] = [
                                            {
                                                "name": c["COLUMN_NAME"],
                                                "type": c["DATA_TYPE"],
                                                "nullable": c["IS_NULLABLE"] == "YES",
                                                "key": c["COLUMN_KEY"],
                                            }
                                            for c in columns
                                        ]
                                        break
                    
                    # 获取配置参数
                    await cursor.execute("SHOW GLOBAL VARIABLES")
                    params = await cursor.fetchall()
                    
                    from .knowledge_base import SchemaKnowledge, ConfigKnowledge
                    
                    # 写入schema知识库
                    if all_tables:
                        self.kb.add_schema(SchemaKnowledge(
                            instance_id=managed.id,
                            db_name="mysql",
                            tables=all_tables,
                            indexes=[],
                            version=managed.version,
                            captured_at=datetime.now(timezone.utc).isoformat(),
                        ))
                    
                    # 写入配置知识库
                    self.kb.add_config(ConfigKnowledge(
                        instance_id=managed.id,
                        db_type=managed.db_type,
                        version=managed.version,
                        parameters={p["Variable_name"]: str(p["Value"]) for p in params},
                        captured_at=datetime.now(timezone.utc).isoformat(),
                    ))
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Failed to capture MySQL knowledge for {managed.id}: {e}")

    async def health_check_all(self) -> Dict[str, Dict]:
        """
        对所有已纳管实例执行健康检查

        Returns:
            Dict[instance_id, health_status]
        """
        results = {}
        for managed in self.registry.get_all(status_filter="onboarded"):
            try:
                # 简单的健康检查：尝试连接
                if managed.db_type == "postgresql":
                    health = await self._health_check_postgres(managed)
                elif managed.db_type in ("mysql", "mariadb"):
                    health = await self._health_check_mysql(managed)
                else:
                    health = {"status": "unknown", "message": "Unsupported db_type"}
            except Exception as e:
                health = {"status": "error", "message": str(e)}
            results[managed.id] = {
                "instance_id": managed.id,
                "db_type": managed.db_type,
                "port": managed.port,
                **health,
            }
        return results

    async def _health_check_postgres(self, managed: ManagedInstance) -> Dict:
        """PostgreSQL健康检查"""
        try:
            import asyncpg
            import os
            # 优先使用环境变量作为认证信息
            user = os.environ.get("PGUSER", "postgres")
            password = os.environ.get("PGPASSWORD", os.environ.get("POSTGRES_PASSWORD", ""))
            conn = await asyncpg.connect(
                host=managed.host,
                port=managed.port,
                user=user,
                password=password,
                timeout=3.0,
            )
            await conn.close()
            return {"status": "healthy"}
        except Exception as e:
            return {"status": "unhealthy", "message": str(e)}

    async def _health_check_mysql(self, managed: ManagedInstance) -> Dict:
        """MySQL健康检查"""
        try:
            import aiomysql
            import os
            # 优先使用环境变量作为认证信息
            user = os.environ.get("MYSQL_USER", "root")
            password = os.environ.get("MYSQL_PASSWORD", os.environ.get("MYSQL_ROOT_PASSWORD", ""))
            conn = await aiomysql.connect(
                host=managed.host,
                port=managed.port,
                user=user,
                password=password,
                connect_timeout=3.0,
            )
            conn.close()
            return {"status": "healthy"}
        except Exception as e:
            return {"status": "unhealthy", "message": str(e)}

    def get_onboarded_instances(self) -> List[ManagedInstance]:
        """获取所有已纳管实例"""
        return self.registry.get_all(status_filter="onboarded")

    def get_all_instances(self) -> List[ManagedInstance]:
        """获取所有实例（包括各种状态）"""
        return self.registry.get_all()

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = {
            "registry": self.registry.get_stats(),
        }
        if self.kb:
            stats["knowledge_base"] = self.kb.get_stats()
        return stats

    def remove_instance(self, instance_id: str) -> bool:
        """
        移除实例（软删除）

        Args:
            instance_id: 实例ID

        Returns:
            是否成功
        """
        return self.registry.remove(instance_id)
