"""
数据库类型识别与版本检测
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional, List

from .scanner import DBType, DiscoveredInstance

# asyncpg 可能未安装
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

# aiomysql 可能未安装
try:
    import aiomysql
    AIOMYSQL_AVAILABLE = True
except ImportError:
    AIOMYSQL_AVAILABLE = False


@dataclass
class IdentifiedInstance:
    """识别后的完整实例信息"""
    instance: DiscoveredInstance
    version: str
    version_major: int
    version_minor: int
    edition: str = ""  # MySQL Community / Enterprise, PG Standard / Enterprise
    max_connections: int = 100
    current_connections: int = 0
    # instance_id is derived from instance, not stored separately

    def instance_id(self) -> str:
        """派生属性：实例唯一标识"""
        return self.instance.instance_id


class DatabaseIdentifier:
    """
    数据库识别器

    功能：
    1. 连接测试（无需认证的info查询）
    2. 版本检测
    3. 类型确认（区分MySQL/MariaDB）
    """

    SCAN_TIMEOUT = 3.0
    MARIADB_INDICATORS = ["MariaDB", "maria", "mariadb"]

    def __init__(self, scan_timeout: float = SCAN_TIMEOUT):
        """
        初始化识别器

        Args:
            scan_timeout: 连接和命令超时时间（秒）
        """
        self.scan_timeout = scan_timeout

    async def identify(self, instance: DiscoveredInstance) -> Optional[IdentifiedInstance]:
        """识别单个实例，返回完整信息，失败返回None"""
        if instance.db_type == DBType.POSTGRESQL:
            return await self._identify_postgres(instance)
        elif instance.db_type in (DBType.MYSQL, DBType.MARIADB):
            return await self._identify_mysql(instance)
        elif instance.db_type == DBType.ORACLE:
            return await self._identify_oracle(instance)
        return None

    async def identify_all(
        self, instances: List[DiscoveredInstance]
    ) -> List[IdentifiedInstance]:
        """批量识别"""
        results = await asyncio.gather(
            *[self.identify(inst) for inst in instances],
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, IdentifiedInstance)]

    async def _identify_postgres(self, instance: DiscoveredInstance) -> Optional[IdentifiedInstance]:
        """识别PostgreSQL实例"""
        if not ASYNCPG_AVAILABLE:
            return None
        try:
            conn = await asyncpg.connect(
                host=instance.host,
                port=instance.port,
                database="postgres",
                timeout=self.SCAN_TIMEOUT,
                command_timeout=self.SCAN_TIMEOUT,
            )
            try:
                version_row = await conn.fetchrow("SELECT version()")
                version_str = version_row["version"]

                # 解析版本号
                version_match = re.search(r"(\d+)\.(\d+)", version_str)
                major = int(version_match.group(1)) if version_match else 0
                minor = int(version_match.group(2)) if version_match else 0

                # 尝试获取连接数
                try:
                    conn_count = await conn.fetchval("SELECT count(*) FROM pg_stat_activity")
                except Exception:
                    conn_count = 0

                try:
                    max_conn = await conn.fetchval("SHOW max_connections")
                    max_conn_int = int(max_conn) if max_conn else 100
                except Exception:
                    max_conn_int = 100

                instance.version = version_str
                instance.status = "identified"

                return IdentifiedInstance(
                    instance=instance,
                    version=version_str,
                    version_major=major,
                    version_minor=minor,
                    max_connections=max_conn_int,
                    current_connections=conn_count or 0,
                )
            finally:
                await conn.close()
        except Exception:
            return None

    async def _identify_mysql(self, instance: DiscoveredInstance) -> Optional[IdentifiedInstance]:
        """识别MySQL/MariaDB实例"""
        if not AIOMYSQL_AVAILABLE:
            return None
        try:
            conn = await aiomysql.connect(
                host=instance.host,
                port=instance.port,
                timeout=self.SCAN_TIMEOUT,
            )
            try:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        "SELECT VERSION() as version, @@max_connections as max_conn"
                    )
                    row = await cursor.fetchone()

                    if not row:
                        return None

                    version_str = row["version"]
                    is_mariadb = any(
                        indicator in version_str.lower()
                        for indicator in self.MARIADB_INDICATORS
                    )
                    edition = "MariaDB" if is_mariadb else "MySQL"

                    version_match = re.search(r"(\d+)\.(\d+)", version_str)
                    major = int(version_match.group(1)) if version_match else 0
                    minor = int(version_match.group(2)) if version_match else 0

                    if is_mariadb:
                        instance.db_type = DBType.MARIADB

                    instance.version = version_str
                    instance.status = "identified"

                    return IdentifiedInstance(
                        instance=instance,
                        version=version_str,
                        version_major=major,
                        version_minor=minor,
                        edition=edition,
                        max_connections=int(row["max_connections"]) if row["max_connections"] else 100,
                    )
            finally:
                await conn.close()
        except Exception:
            return None

    async def _identify_oracle(self, instance: DiscoveredInstance) -> Optional[IdentifiedInstance]:
        """识别Oracle实例（预留，当前仅端口确认）"""
        instance.status = "unverified_requires_oracle_client"
        return IdentifiedInstance(
            instance=instance,
            version="unknown",
            version_major=0,
            version_minor=0,
        )
