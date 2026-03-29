"""PostgreSQL专用工具集
PostgreSQL特有的诊断和操作工具
"""
import time
from typing import Any
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


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
        
        # 使用PG适配器获取会话
        db_connector = context.get("db_connector")
        if db_connector:
            sessions = await db_connector.get_sessions(limit=params.get("limit", 100))
            
            if state_filter:
                sessions = [s for s in sessions if getattr(s, "state", "") == state_filter]
            
            return ToolResult(
                success=True,
                data={
                    "sessions": [
                        {
                            "pid": s.pid,
                            "username": s.username,
                            "db": s.db,
                            "state": getattr(s, "state", ""),
                            "query": getattr(s, "query", ""),
                            "query_start": getattr(s, "query_start", None),
                            "wait_event": s.wait_event,
                        }
                        for s in sessions
                    ],
                    "total": len(sessions),
                    "active_count": len([s for s in sessions if getattr(s, "state", "") == "active"]),
                    "idle_count": len([s for s in sessions if getattr(s, "state", "") == "idle"]),
                    "idle_in_transaction_count": len([s for s in sessions if getattr(s, "state", "") == "idle in transaction"]),
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
            locks = await db_connector.get_locks()
            
            return ToolResult(
                success=True,
                data={
                    "locks": [
                        {
                            "lock_type": l.lock_type,
                            "mode": l.mode_requested,
                            "pid": l.pid,
                            "blocker_pid": l.blocker_pid,
                            "relation": l.relation,
                            "granted": l.granted,
                            "wait_seconds": l.wait_seconds,
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
            rep_info = await db_connector.get_replication()
            
            return ToolResult(
                success=True,
                data={
                    "role": rep_info.role,
                    "replication_enabled": rep_info.replication_enabled,
                    "replicas": rep_info.replicas,
                    "wal_lag": rep_info.wal_lag,
                    "replay_lag": rep_info.replay_lag,
                    "flush_lag": rep_info.flush_lag,
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
        
        # Mock膨胀数据
        tables = [
            {"schemaname": "public", "tablename": "orders", "wasted_percent": 15.5, "wasted_mb": 150, "recommendation": "VACUUM"},
            {"schemaname": "public", "tablename": "order_items", "wasted_percent": 22.0, "wasted_mb": 500, "recommendation": "VACUUM FULL"},
            {"schemaname": "public", "tablename": "audit_log", "wasted_percent": 35.0, "wasted_mb": 2048, "recommendation": "VACUUM FULL + CLUSTER"},
            {"schemaname": "public", "tablename": "products", "wasted_percent": 8.0, "wasted_mb": 5, "recommendation": "Normal"},
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
        
        indexes = [
            {"tablename": "orders", "indexname": "orders_pkey", "indexed_col": "id", "usage_scan": 15000, "size_mb": 45, "redundant": False},
            {"tablename": "orders", "indexname": "idx_orders_status", "indexed_col": "status", "usage_scan": 8000, "size_mb": 120, "redundant": False},
            {"tablename": "orders", "indexname": "idx_orders_created", "indexed_col": "created_at", "usage_scan": 0, "size_mb": 200, "redundant": True, "recommendation": "DROP unused index"},
            {"tablename": "order_items", "indexname": "idx_items_order_id", "indexed_col": "order_id", "usage_scan": 50000, "size_mb": 80, "redundant": False},
            {"tablename": "products", "indexname": "idx_products_name", "indexed_col": "name", "usage_scan": 200, "size_mb": 15, "redundant": False},
        ]
        
        table_filter = params.get("table", "")
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


# 注册PostgreSQL工具
def register_postgres_tools(registry):
    """注册所有PostgreSQL专用工具"""
    tools = [
        PGSessionAnalysisTool(),
        PGLockAnalysisTool(),
        PGReplicationStatusTool(),
        PGBloatAnalysisTool(),
        PGIndexAnalysisTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return tools
