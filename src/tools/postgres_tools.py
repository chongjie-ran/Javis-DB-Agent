"""PostgreSQL专用工具集

PostgreSQL特有的诊断和操作工具。
支持直连（DirectPostgresConnector）和API适配器（PostgresConnector）两种模式。
"""
import os
from typing import Any, Optional
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


# ---------------------------------------------------------------------------
# 默认连接器工厂
# ---------------------------------------------------------------------------

def get_default_postgres_connector():
    """从环境变量创建DirectPostgresConnector"""
    host = os.environ.get("JAVIS_PG_HOST", "localhost")
    port = int(os.environ.get("JAVIS_PG_PORT", "5432"))
    user = os.environ.get("JAVIS_PG_USER", "postgres")
    password = os.environ.get("JAVIS_PG_PASSWORD", "")
    database = os.environ.get("JAVIS_PG_DATABASE", "postgres")
    from src.db.direct_postgres_connector import DirectPostgresConnector
    return DirectPostgresConnector(host, port, user, password, database)


# ---------------------------------------------------------------------------
# 工具基类：自动识别直连/适配器模式
# ---------------------------------------------------------------------------

def _getattr(obj: Any, key: str, default: Any = None) -> Any:
    """安全获取属性或dict key"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ============================================================================
# PostgreSQL工具：会话分析
# ============================================================================
class PGSessionAnalysisTool(BaseTool):
    """PostgreSQL会话分析 - pg_stat_activity"""

    definition = ToolDefinition(
        name="pg_session_analysis",
        description="分析PostgreSQL会话状态，包括活跃/idle/idle in transaction",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="state_filter", type="string", description="状态过滤: active/idle/idle in transaction", required=False, default=""),
            ToolParam(name="limit", type="int", description="返回条数", required=False, default=100),
        ],
        example="pg_session_analysis(instance_id='INS-002', state_filter='idle in transaction')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        state_filter = params.get("state_filter", "")
        limit = params.get("limit", 100)

        db_connector = context.get("db_connector")
        if db_connector:
            # 尝试直连（返回dict）
            if hasattr(db_connector, "get_sessions") and callable(db_connector.get_sessions):
                sessions = await db_connector.get_sessions(limit=limit)
                if sessions and isinstance(sessions[0], dict):
                    # DirectPostgresConnector 模式
                    if state_filter:
                        sessions = [s for s in sessions if _getattr(s, "state") == state_filter]
                    return ToolResult(
                        success=True,
                        data={
                            "sessions": [
                                {
                                    "pid": _getattr(s, "pid"),
                                    "username": _getattr(s, "username"),
                                    "db": _getattr(s, "db"),
                                    "state": _getattr(s, "state"),
                                    "query": _getattr(s, "query"),
                                    "query_start": str(_getattr(s, "query_start")) if _getattr(s, "query_start") else None,
                                    "wait_event": _getattr(s, "wait_event"),
                                    "machine": _getattr(s, "machine"),
                                }
                                for s in sessions
                            ],
                            "total": len(sessions),
                            "active_count": len([s for s in sessions if _getattr(s, "state") == "active"]),
                            "idle_count": len([s for s in sessions if _getattr(s, "state") == "idle"]),
                            "idle_in_transaction_count": len([s for s in sessions if _getattr(s, "state") == "idle in transaction"]),
                        }
                    )
                else:
                    # PostgresConnector 模式（返回SessionInfo对象）
                    if state_filter:
                        sessions = [s for s in sessions if _getattr(s, "state") == state_filter]
                    return ToolResult(
                        success=True,
                        data={
                            "sessions": [
                                {
                                    "pid": s.pid,
                                    "username": s.username,
                                    "db": s.db,
                                    "state": _getattr(s, "state"),
                                    "query": _getattr(s, "query"),
                                    "query_start": str(_getattr(s, "query_start")) if _getattr(s, "query_start") else None,
                                    "wait_event": _getattr(s, "wait_event"),
                                }
                                for s in sessions
                            ],
                            "total": len(sessions),
                            "active_count": len([s for s in sessions if _getattr(s, "state") == "active"]),
                            "idle_count": len([s for s in sessions if _getattr(s, "state") == "idle"]),
                            "idle_in_transaction_count": len([s for s in sessions if _getattr(s, "state") == "idle in transaction"]),
                        }
                    )

        # Mock fallback
        return ToolResult(success=True, data={"mock": "pg_session_analysis", "instance_id": instance_id})


# ============================================================================
# PostgreSQL工具：锁分析
# ============================================================================
class PGLockAnalysisTool(BaseTool):
    """PostgreSQL锁分析 - pg_locks"""

    definition = ToolDefinition(
        name="pg_lock_analysis",
        description="分析PostgreSQL锁等待和死锁情况",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="include_graph", type="bool", description="是否包含锁等待图", required=False, default=False),
        ],
        example="pg_lock_analysis(instance_id='INS-002', include_graph=True)"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]

        db_connector = context.get("db_connector")
        if db_connector:
            if hasattr(db_connector, "get_locks") and callable(db_connector.get_locks):
                locks = await db_connector.get_locks()
                if locks and isinstance(locks[0], dict):
                    # DirectPostgresConnector 模式
                    return ToolResult(
                        success=True,
                        data={
                            "locks": [
                                {
                                    "lock_type": _getattr(l, "locktype"),
                                    "mode": _getattr(l, "mode"),
                                    "pid": _getattr(l, "pid"),
                                    "blocker_pid": _getattr(l, "blocker_pid"),
                                    "relation": str(_getattr(l, "relation")) if _getattr(l, "relation") else None,
                                    "granted": _getattr(l, "granted"),
                                }
                                for l in locks
                            ],
                            "total": len(locks),
                            "granted_count": len([l for l in locks if _getattr(l, "granted")]),
                            "waiting_count": len([l for l in locks if not _getattr(l, "granted")]),
                        }
                    )
                else:
                    # PostgresConnector 模式
                    return ToolResult(
                        success=True,
                        data={
                            "locks": [
                                {
                                    "lock_type": l.lock_type,
                                    "mode": _getattr(l, "mode_requested"),
                                    "pid": l.pid,
                                    "blocker_pid": _getattr(l, "blocker_pid"),
                                    "relation": _getattr(l, "relation"),
                                    "granted": l.granted,
                                }
                                for l in locks
                            ],
                            "total": len(locks),
                            "granted_count": len([l for l in locks if l.granted]),
                            "waiting_count": len([l for l in locks if not l.granted]),
                        }
                    )

        return ToolResult(success=True, data={"mock": "pg_lock_analysis", "instance_id": instance_id})


# ============================================================================
# PostgreSQL工具：复制状态
# ============================================================================
class PGReplicationStatusTool(BaseTool):
    """PostgreSQL复制状态分析"""

    definition = ToolDefinition(
        name="pg_replication_status",
        description="分析PostgreSQL流复制状态和延迟",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
        ],
        example="pg_replication_status(instance_id='INS-002')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]

        db_connector = context.get("db_connector")
        if db_connector:
            if hasattr(db_connector, "get_replication") and callable(db_connector.get_replication):
                rep_info = await db_connector.get_replication()
                if isinstance(rep_info, dict):
                    return ToolResult(
                        success=True,
                        data={
                            "role": rep_info.get("role"),
                            "replication_enabled": rep_info.get("replication_enabled"),
                            "replicas": rep_info.get("replicas", []),
                            "wal_lag": rep_info.get("wal_lag"),
                            "replay_lag": rep_info.get("replay_lag"),
                            "flush_lag": rep_info.get("flush_lag"),
                        }
                    )
                else:
                    # ReplicationInfo 对象
                    return ToolResult(
                        success=True,
                        data={
                            "role": rep_info.role,
                            "replication_enabled": rep_info.replication_enabled,
                            "replicas": rep_info.replicas,
                            "wal_lag": _getattr(rep_info, "wal_lag"),
                            "replay_lag": _getattr(rep_info, "replay_lag"),
                            "flush_lag": _getattr(rep_info, "flush_lag"),
                        }
                    )

        return ToolResult(success=True, data={"mock": "pg_replication_status", "instance_id": instance_id})


# ============================================================================
# PostgreSQL工具：膨胀分析
# ============================================================================
class PGBloatAnalysisTool(BaseTool):
    """PostgreSQL表膨胀分析"""

    definition = ToolDefinition(
        name="pg_bloat_analysis",
        description="分析PostgreSQL表膨胀情况，识别需要VACUUM的表",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="min_bloat_percent", type="float", description="最小膨胀百分比", required=False, default=10.0),
            ToolParam(name="schema", type="string", description="Schema过滤", required=False, default=""),
        ],
        example="pg_bloat_analysis(instance_id='INS-002', min_bloat_percent=20.0)"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        min_bloat = params.get("min_bloat_percent", 10.0)
        schema = params.get("schema", "")

        db_connector = context.get("db_connector")
        if db_connector:
            if hasattr(db_connector, "execute_sql") and callable(db_connector.execute_sql):
                # 使用直连的真实SQL查询
                sql = """
                    WITH table_sizes AS (
                        SELECT
                            schemaname,
                            tablename,
                            pg_total_relation_size(schemaname||'.'||tablename) AS total_bytes,
                            pg_relation_size(schemaname||'.'||tablename) AS table_bytes,
                            pg_total_relation_size(schemaname||'.'||tablename)
                                - pg_relation_size(schemaname||'.'||tablename) AS wasted_bytes
                        FROM pg_tables
                        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                    )
                    SELECT
                        schemaname,
                        tablename,
                        pg_size_pretty(total_bytes) AS total_size,
                        pg_size_pretty(table_bytes) AS table_size,
                        pg_size_pretty(wasted_bytes) AS wasted_size,
                        CASE WHEN total_bytes > 0
                             THEN round((wasted_bytes::numeric / total_bytes) * 100, 1)
                             ELSE 0
                        END AS wasted_percent
                    FROM table_sizes
                    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY wasted_bytes DESC
                    LIMIT 30
                """
                rows = await db_connector.execute_sql(sql)

                tables = []
                for r in rows:
                    wasted_pct = _getattr(r, "wasted_percent", 0) or 0
                    if wasted_pct >= min_bloat:
                        if schema and _getattr(r, "schemaname") != schema:
                            continue
                        tables.append({
                            "schemaname": _getattr(r, "schemaname"),
                            "tablename": _getattr(r, "tablename"),
                            "total_size": _getattr(r, "total_size"),
                            "table_size": _getattr(r, "table_size"),
                            "wasted_size": _getattr(r, "wasted_size"),
                            "wasted_percent": wasted_pct,
                            "recommendation": "VACUUM FULL" if wasted_pct > 30 else "VACUUM",
                        })

                return ToolResult(
                    success=True,
                    data={
                        "tables": tables,
                        "total": len(tables),
                        "critical_count": len([t for t in tables if t["wasted_percent"] > 30]),
                        "recommendation": "对高膨胀表执行VACUUM或VACUUM FULL",
                    }
                )

        # Mock fallback
        tables = [
            {"schemaname": "public", "tablename": "orders", "wasted_percent": 15.5, "wasted_size": "150 MB", "recommendation": "VACUUM"},
            {"schemaname": "public", "tablename": "order_items", "wasted_percent": 22.0, "wasted_size": "500 MB", "recommendation": "VACUUM FULL"},
            {"schemaname": "public", "tablename": "audit_log", "wasted_percent": 35.0, "wasted_size": "2 GB", "recommendation": "VACUUM FULL + CLUSTER"},
            {"schemaname": "public", "tablename": "products", "wasted_percent": 8.0, "wasted_size": "5 MB", "recommendation": "Normal"},
        ]
        if min_bloat > 0:
            tables = [t for t in tables if t["wasted_percent"] >= min_bloat]
        if schema:
            tables = [t for t in tables if t["schemaname"] == schema]

        return ToolResult(
            success=True,
            data={
                "tables": tables,
                "total": len(tables),
                "critical_count": len([t for t in tables if t["wasted_percent"] > 20]),
                "recommendation": "对高膨胀表执行VACUUM或VACUUM FULL",
            }
        )


# ============================================================================
# PostgreSQL工具：索引分析
# ============================================================================
class PGIndexAnalysisTool(BaseTool):
    """PostgreSQL索引分析"""

    definition = ToolDefinition(
        name="pg_index_analysis",
        description="分析PostgreSQL索引使用率和冗余索引",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="table", type="string", description="表名过滤", required=False, default=""),
        ],
        example="pg_index_analysis(instance_id='INS-002', table='orders')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        table_filter = params.get("table", "")

        db_connector = context.get("db_connector")
        if db_connector:
            if hasattr(db_connector, "execute_sql") and callable(db_connector.execute_sql):
                sql = """
                    SELECT
                        schemaname,
                        tablename,
                        indexname,
                        indexdef,
                        pg_relation_size(schemaname||'.'||indexname) AS index_size
                    FROM pg_indexes
                    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY pg_relation_size(schemaname||'.'||indexname) DESC
                """
                rows = await db_connector.execute_sql(sql)
                indexes = []
                for r in rows:
                    idx_size_mb = _getattr(r, "index_size", 0)
                    if idx_size_mb:
                        idx_size_mb = idx_size_mb / (1024 * 1024)
                    indexes.append({
                        "schemaname": _getattr(r, "schemaname"),
                        "tablename": _getattr(r, "tablename"),
                        "indexname": _getattr(r, "indexname"),
                        "indexdef": _getattr(r, "indexdef"),
                        "size_mb": round(idx_size_mb, 2),
                    })

                if table_filter:
                    indexes = [i for i in indexes if _getattr(i, "tablename") == table_filter]

                return ToolResult(
                    success=True,
                    data={
                        "indexes": indexes,
                        "total": len(indexes),
                        "total_size_mb": round(sum(_getattr(i, "size_mb", 0) for i in indexes), 2),
                        "recommendation": f"共 {len(indexes)} 个索引，总大小 {round(sum(_getattr(i, 'size_mb', 0) for i in indexes), 2)} MB",
                    }
                )

        # Mock fallback
        indexes = [
            {"tablename": "orders", "indexname": "orders_pkey", "size_mb": 45, "redundant": False},
            {"tablename": "orders", "indexname": "idx_orders_status", "size_mb": 120, "redundant": False},
            {"tablename": "orders", "indexname": "idx_orders_created", "size_mb": 200, "redundant": True},
            {"tablename": "order_items", "indexname": "idx_items_order_id", "size_mb": 80, "redundant": False},
            {"tablename": "products", "indexname": "idx_products_name", "size_mb": 15, "redundant": False},
        ]
        if table_filter:
            indexes = [i for i in indexes if i["tablename"] == table_filter]
        redundant = [i for i in indexes if i.get("redundant")]

        return ToolResult(
            success=True,
            data={
                "indexes": indexes,
                "total": len(indexes),
                "redundant_count": len(redundant),
                "total_size_mb": sum(i["size_mb"] for i in indexes),
                "redundant_indexes": redundant,
                "recommendation": f"可删除{len(redundant)}个冗余索引节省{sum(i['size_mb'] for i in redundant)}MB空间",
            }
        )


# ============================================================================
# PostgreSQL工具：终止会话（危险操作）
# ============================================================================
class PGKillSessionTool(BaseTool):
    """PostgreSQL会话终止工具（高风险）"""

    definition = ToolDefinition(
        name="pg_kill_session",
        description="终止PostgreSQL会话（危险操作，需要L4审批）",
        category="action",
        risk_level=RiskLevel.L4_MEDIUM,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="pid", type="int", description="要终止的进程PID", required=True),
            ToolParam(name="kill_type", type="string", description="terminate(SIGTERM)或cancel(SIGINT)", required=False, default="terminate"),
        ],
        example="pg_kill_session(instance_id='INS-002', pid=12345, kill_type='terminate')"
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        pid = params["pid"]
        kill_type = params.get("kill_type", "terminate")

        if kill_type not in ("terminate", "cancel"):
            return ToolResult(
                success=False,
                error=f"Invalid kill_type: {kill_type}. Must be 'terminate' or 'cancel'.",
            )

        db_connector = context.get("db_connector")
        if db_connector:
            # 优先使用有kill_backend方法的直连器
            if hasattr(db_connector, "kill_backend") and callable(db_connector.kill_backend):
                result = await db_connector.kill_backend(pid, kill_type)
                return ToolResult(
                    success=True,
                    data={
                        "killed": pid,
                        "kill_type": kill_type,
                        "result": result.get("result"),
                        "message": f"PID {pid} 已通过 pg_{kill_type}_backend 终止",
                    }
                )
            elif hasattr(db_connector, "execute_sql") and callable(db_connector.execute_sql):
                # fallback: 直接执行SQL
                sql = f"SELECT pg_{kill_type}_backend({pid})"
                rows = await db_connector.execute_sql(sql)
                return ToolResult(
                    success=True,
                    data={
                        "killed": pid,
                        "kill_type": kill_type,
                        "result": rows[0] if rows else None,
                        "message": f"PID {pid} 已通过 pg_{kill_type}_backend 终止",
                    }
                )

        return ToolResult(success=False, error="No db_connector available")


# ============================================================================
# 注册PostgreSQL工具
# ============================================================================
def register_postgres_tools(registry):
    """注册所有PostgreSQL专用工具"""
    tools = [
        PGSessionAnalysisTool(),
        PGLockAnalysisTool(),
        PGReplicationStatusTool(),
        PGBloatAnalysisTool(),
        PGIndexAnalysisTool(),
        PGKillSessionTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return tools
