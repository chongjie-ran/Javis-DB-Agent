"""会话分析工具集 - Round 13 新增"""
import time
from typing import Any, Optional
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


# ============================================================================
# 会话列表工具
# ============================================================================
class SessionListTool(BaseTool):
    """列出所有数据库会话"""
    
    definition = ToolDefinition(
        name="session_list",
        description="列出数据库所有会话，包括活跃/idle/等待中的会话",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
            ToolParam(name="state_filter", type="string", description="状态过滤: active/idle/locked/waiting", required=False, default=""),
            ToolParam(name="limit", type="int", description="返回条数", required=False, default=50, constraints={"min": 1, "max": 500}),
        ],
        example="session_list(instance_id='INS-001', db_type='mysql', state_filter='active', limit=50)"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        db_type = params.get("db_type", "mysql")
        state_filter = params.get("state_filter", "")
        limit = params.get("limit", 50)
        
        # 模拟会话数据
        if db_type == "mysql":
            sessions = self._mysql_mock_sessions()
        elif db_type == "pg":
            sessions = self._pg_mock_sessions()
        else:
            sessions = self._oracle_mock_sessions()
        
        if state_filter:
            sessions = [s for s in sessions if s.get("state") == state_filter]
        
        sessions = sessions[:limit]
        
        # 统计
        state_counts = {}
        for s in sessions:
            st = s.get("state", "unknown")
            state_counts[st] = state_counts.get(st, 0) + 1
        
        return ToolResult(
            success=True,
            data={
                "instance_id": instance_id,
                "db_type": db_type,
                "sessions": sessions,
                "total": len(sessions),
                "state_counts": state_counts,
                "timestamp": time.time(),
            }
        )
    
    def _mysql_mock_sessions(self):
        return [
            {"session_id": "1001", "thread_id": 1001, "user": "app_user", "host": "192.168.1.10", "db": "shop_db", "command": "Query", "state": "executing", "time": 5, "info": "SELECT * FROM orders WHERE status='pending'"},
            {"session_id": "1002", "thread_id": 1002, "user": "app_user", "host": "192.168.1.11", "db": "shop_db", "command": "Sleep", "state": "idle", "time": 120, "info": ""},
            {"session_id": "1003", "thread_id": 1003, "user": "app_user", "host": "192.168.1.12", "db": "shop_db", "command": "Query", "state": "locked", "time": 30, "info": "UPDATE inventory SET count=count-1 WHERE id=1"},
            {"session_id": "1004", "thread_id": 1004, "user": "app_user", "host": "192.168.1.13", "db": "shop_db", "command": "Query", "state": "waiting", "time": 15, "info": "SELECT * FROM products FOR UPDATE"},
            {"session_id": "1005", "thread_id": 1005, "user": "backup_user", "host": "192.168.1.20", "db": "shop_db", "command": "Binlog Dump", "state": "active", "time": 3600, "info": ""},
            {"session_id": "1006", "thread_id": 1006, "user": "app_user", "host": "192.168.1.14", "db": "shop_db", "command": "Query", "state": "executing", "time": 2, "info": "INSERT INTO order_items (order_id, product_id) VALUES (1, 100)"},
            {"session_id": "1007", "thread_id": 1007, "user": "app_user", "host": "192.168.1.15", "db": "shop_db", "command": "Sleep", "state": "idle", "time": 45, "info": ""},
            {"session_id": "1008", "thread_id": 1008, "user": "app_user", "host": "192.168.1.16", "db": "shop_db", "command": "Query", "state": "locked", "time": 60, "info": "DELETE FROM audit_log WHERE created_at < '2024-01-01'"},
        ]
    
    def _pg_mock_sessions(self):
        return [
            {"pid": 10001, "username": "app_user", "db": "shop_db", "state": "active", "query": "SELECT * FROM orders WHERE status='pending'", "query_start": "2026-03-29 18:50:00", "wait_event": None, "application_name": "psql"},
            {"pid": 10002, "username": "app_user", "db": "shop_db", "state": "idle", "query": None, "query_start": "2026-03-29 18:48:00", "wait_event": None, "application_name": "psql"},
            {"pid": 10003, "username": "app_user", "db": "shop_db", "state": "idle in transaction", "query": "BEGIN; UPDATE accounts SET balance=balance-100 WHERE id=1;", "query_start": "2026-03-29 18:45:00", "wait_event": "Lock", "application_name": "psql"},
            {"pid": 10004, "username": "app_user", "db": "shop_db", "state": "active", "query": "SELECT * FROM products FOR UPDATE", "query_start": "2026-03-29 18:52:00", "wait_event": "Lock", "application_name": "psql"},
            {"pid": 10005, "username": "postgres", "db": "shop_db", "state": "active", "query": "CHECKPOINT", "query_start": "2026-03-29 18:53:00", "wait_event": None, "application_name": "postgres"},
        ]
    
    def _oracle_mock_sessions(self):
        return [
            {"sid": 1001, "serial#": 20345, "username": "APP_USER", "status": "ACTIVE", "program": "JDBC", "machine": "192.168.1.10", "event": "db file sequential read", "seconds_in_wait": 5, "sql_id": "abc123", "sql_text": "SELECT * FROM orders WHERE status='pending'"},
            {"sid": 1002, "serial#": 20346, "username": "APP_USER", "status": "INACTIVE", "program": "JDBC", "machine": "192.168.1.11", "event": None, "seconds_in_wait": 120, "sql_id": None, "sql_text": None},
            {"sid": 1003, "serial#": 20347, "username": "APP_USER", "status": "ACTIVE", "program": "JDBC", "machine": "192.168.1.12", "event": "enq: TX - row lock contention", "seconds_in_wait": 30, "sql_id": "def456", "sql_text": "UPDATE inventory SET count=count-1 WHERE id=1"},
        ]


# ============================================================================
# 会话详情工具
# ============================================================================
class SessionDetailTool(BaseTool):
    """查询指定会话的详细信息"""
    
    definition = ToolDefinition(
        name="session_detail",
        description="查询指定会话的详细信息，包括执行的SQL、等待事件、锁信息等",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="session_id", type="string", description="会话ID (MySQL为thread_id, PG为pid, Oracle为sid)", required=True),
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
        ],
        example="session_detail(instance_id='INS-001', session_id='1001', db_type='mysql')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        session_id = params["session_id"]
        db_type = params.get("db_type", "mysql")
        
        # 模拟会话详情
        if db_type == "mysql":
            detail = self._mysql_session_detail(session_id)
        elif db_type == "pg":
            detail = self._pg_session_detail(session_id)
        else:
            detail = self._oracle_session_detail(session_id)
        
        return ToolResult(
            success=True,
            data={
                "instance_id": instance_id,
                "session_id": session_id,
                "db_type": db_type,
                "detail": detail,
                "timestamp": time.time(),
            }
        )
    
    def _mysql_session_detail(self, session_id):
        session_map = {
            "1001": {
                "thread_id": 1001, "session_id": "1001",
                "user": "app_user", "host": "192.168.1.10:54321",
                "db": "shop_db", "command": "Query", "state": "executing",
                "time": 5, "sql_text": "SELECT * FROM orders WHERE status='pending'",
                "sql_id": None, "plan": None,
                "locks_held": [], "locks_waiting": [],
                "memory_used_mb": 12.5, "temporary_tables": 0,
                "files_opened": 3, "tables_accessed": ["orders", "customers"],
                "connections_from": "192.168.1.10",
            },
            "1003": {
                "thread_id": 1003, "session_id": "1003",
                "user": "app_user", "host": "192.168.1.12:54321",
                "db": "shop_db", "command": "Query", "state": "locked",
                "time": 30, "sql_text": "UPDATE inventory SET count=count-1 WHERE id=1",
                "sql_id": None, "plan": None,
                "locks_held": [{"lock_type": "ROW", "mode": "X", "table": "inventory", "page": 0, "row": 1}],
                "locks_waiting": [],
                "blocking_session": "1004",
                "memory_used_mb": 8.2, "temporary_tables": 0,
                "files_opened": 1, "tables_accessed": ["inventory"],
                "connections_from": "192.168.1.12",
            },
        }
        return session_map.get(session_id, {"error": f"Session {session_id} not found"})
    
    def _pg_session_detail(self, pid):
        session_map = {
            "10001": {
                "pid": 10001, "username": "app_user", "db": "shop_db",
                "state": "active", "query": "SELECT * FROM orders WHERE status='pending'",
                "query_start": "2026-03-29 18:50:00", "wait_event": None,
                "application_name": "psql", "client_addr": "192.168.1.10",
                "locks": [], "temp_files": 0, "memory_mb": 15.3,
                "xact_start": "2026-03-29 18:49:55",
            },
            "10003": {
                "pid": 10003, "username": "app_user", "db": "shop_db",
                "state": "idle in transaction", "query": "BEGIN; UPDATE accounts SET balance=balance-100 WHERE id=1;",
                "query_start": "2026-03-29 18:45:00", "wait_event": "Lock",
                "application_name": "psql", "client_addr": "192.168.1.12",
                "locks": [{"locktype": "transactionid", "mode": "ExclusiveLock", "granted": True, "pid": 10003}],
                "temp_files": 0, "memory_mb": 10.1,
                "xact_start": "2026-03-29 18:44:50",
                "idle_in_transaction_seconds": 480,
            },
        }
        return session_map.get(pid, {"error": f"PID {pid} not found"})
    
    def _oracle_session_detail(self, sid):
        session_map = {
            "1001": {
                "sid": 1001, "serial#": 20345, "username": "APP_USER",
                "status": "ACTIVE", "program": "JDBC", "machine": "192.168.1.10",
                "event": "db file sequential read", "seconds_in_wait": 5,
                "sql_id": "abc123", "sql_text": "SELECT * FROM orders WHERE status='pending'",
                "plan_hash_value": 1234567890, "buffer_gets": 15000, "disk_reads": 1200,
                "executions": 1, "rows_processed": 1000,
                "locks": [], "temp_segments_mb": 0,
            },
        }
        return session_map.get(sid, {"error": f"SID {sid} not found"})


# ============================================================================
# 连接池分析工具
# ============================================================================
class ConnectionPoolTool(BaseTool):
    """分析数据库连接池状况"""
    
    definition = ToolDefinition(
        name="connection_pool",
        description="分析数据库连接池的使用情况，包括活跃/空闲/等待/泄漏检测",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
        ],
        example="connection_pool(instance_id='INS-001', db_type='mysql')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        db_type = params.get("db_type", "mysql")
        
        # 模拟连接池数据
        if db_type == "mysql":
            pool_data = self._mysql_pool()
        elif db_type == "pg":
            pool_data = self._pg_pool()
        else:
            pool_data = self._oracle_pool()
        
        # 分析
        issues = []
        warnings = []
        
        active = pool_data["active_connections"]
        total = pool_data["max_connections"]
        usage_pct = (active / total * 100) if total > 0 else 0
        
        if usage_pct > 80:
            issues.append({"type": "HIGH_USAGE", "severity": "high", "message": f"连接使用率 {usage_pct:.1f}%，接近上限", "recommendation": "考虑增加max_connections或优化连接复用"})
        elif usage_pct > 60:
            warnings.append({"type": "MODERATE_USAGE", "severity": "medium", "message": f"连接使用率 {usage_pct:.1f}%"})
        
        if pool_data.get("waiting_threads", 0) > 0:
            issues.append({"type": "CONNECTION_WAIT", "severity": "high", "message": f"有 {pool_data['waiting_threads']} 个线程在等待连接", "recommendation": "连接不足，增加连接池大小或优化SQL执行时间"})
        
        if pool_data.get("aborted_connections", 0) > 10:
            warnings.append({"type": "ABORTED_CONNECTIONS", "severity": "medium", "message": f"有 {pool_data['aborted_connections']} 个异常断开连接", "recommendation": "检查网络稳定性或客户端超时配置"})
        
        pool_data["analysis"] = {"issues": issues, "warnings": warnings, "usage_percent": round(usage_pct, 1)}
        
        return ToolResult(
            success=True,
            data={
                "instance_id": instance_id,
                "db_type": db_type,
                "pool": pool_data,
                "timestamp": time.time(),
            }
        )
    
    def _mysql_pool(self):
        return {
            "max_connections": 500,
            "active_connections": 420,
            "idle_connections": 60,
            "waiting_threads": 15,
            "aborted_connections": 8,
            "cached_connections": 25,
            "connection_errors": 3,
            "threads_connected": 480,
            "threads_running": 25,
            "threads_cached": 20,
            "max_used_connections": 450,
            "connection_age_distribution": {"<1min": 50, "1-5min": 200, "5-30min": 150, ">30min": 20},
            "top_holders": [
                {"user": "app_user", "host": "192.168.1.10", "count": 45},
                {"user": "app_user", "host": "192.168.1.11", "count": 38},
            ],
        }
    
    def _pg_pool(self):
        return {
            "max_connections": 200,
            "active_connections": 85,
            "idle_connections": 50,
            "waiting_connections": 5,
            "max_used_connections": 120,
            "superuser_reserved": 3,
            "autovacuum_workers": 3,
            "pool_stats": {
                "pool_size": 100,
                "max_client_conn": 500,
                "reserved_pool": 0,
                "reserve_pool_timeout": 5000,
            },
            "issues": [],
        }
    
    def _oracle_pool(self):
        return {
            "processes_limit": 500,
            "sessions_limit": 1025,
            "current_processes": 350,
            "current_sessions": 450,
            "active_sessions": 180,
            "inactive_sessions": 270,
            "waiting_sessions": 20,
            "average_active_sessions": 150,
            "max_peak_sessions": 800,
        }


# ============================================================================
# 死锁检测工具
# ============================================================================
class DeadlockDetectionTool(BaseTool):
    """检测数据库死锁情况"""
    
    definition = ToolDefinition(
        name="deadlock_detection",
        description="检测数据库死锁，返回死锁链和等待图",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="db_type", type="string", description="数据库类型: mysql/pg/oracle", required=False, default="mysql"),
        ],
        example="deadlock_detection(instance_id='INS-001', db_type='mysql')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        db_type = params.get("db_type", "mysql")
        
        # 模拟检测结果
        if db_type == "mysql":
            result = self._mysql_deadlock()
        elif db_type == "pg":
            result = self._pg_deadlock()
        else:
            result = self._oracle_deadlock()
        
        return ToolResult(
            success=True,
            data={
                "instance_id": instance_id,
                "db_type": db_type,
                "deadlock_info": result,
                "timestamp": time.time(),
            }
        )
    
    def _mysql_deadlock(self):
        # 模拟检测到一个死锁
        return {
            "has_deadlock": True,
            "deadlock_count_last_hour": 2,
            "deadlocks": [
                {
                    "id": 1,
                    "detected_at": "2026-03-29 18:51:30",
                    "victim_transaction": {"thread_id": 1004, "time": 0.001, "sql": "UPDATE products SET stock=stock-1 WHERE id=100"},
                    "wait_for_lock": {"index": "PRIMARY", "mode": "X", "page": 12345, "row": 567},
                    "blocking_transaction": {"thread_id": 1003, "time": 60.5, "sql": "DELETE FROM products WHERE id=100"},
                    "wait_for_lock": {"index": "idx_category", "mode": "X", "page": 999, "row": 0},
                    "wait_chain": [
                        {"session": "1003", "sql": "DELETE FROM products WHERE id=100", "locks": ["PRIMARY:12345:567"], "waiting_for": "idx_category:999:0"},
                        {"session": "1004", "sql": "UPDATE products SET stock=stock-1 WHERE id=100", "locks": ["idx_category:999:0"], "waiting_for": "PRIMARY:12345:567"},
                    ],
                    "recommendation": "重写SQL避免交叉更新，或使用SELECT FOR UPDATE NOWAIT处理",
                }
            ],
            "wait_graph": "session_1003 -> idx_category:999:0 [BLOCKED by session_1004] -> PRIMARY:12345:567 [BLOCKED by session_1003]",
        }
    
    def _pg_deadlock(self):
        return {
            "has_deadlock": False,
            "deadlock_count_last_hour": 0,
            "deadlocks": [],
            "pending_locks": 15,
            "lock_wait_summary": [
                {"lock_type": "transactionid", "waiting_count": 8, "blocking_count": 3},
                {"lock_type": "relation", "waiting_count": 5, "blocking_count": 2},
                {"lock_type": "tuple", "waiting_count": 2, "blocking_count": 1},
            ],
            "recommendation": "当前无死锁，建议监控长时间锁等待",
        }
    
    def _oracle_deadlock(self):
        return {
            "has_deadlock": True,
            "deadlock_count_last_hour": 1,
            "deadlocks": [
                {
                    "id": 1,
                    "detected_at": "2026-03-29 18:50:00",
                    "victim_session": {"sid": 1004, "serial#": 20348, "sql": "UPDATE PRODUCTS SET STOCK=STOCK-1 WHERE ID=100"},
                    "blocking_session": {"sid": 1003, "serial#": 20347, "sql": "DELETE FROM PRODUCTS WHERE ID=100"},
                    "wait_event": "enq: TX - row lock contention",
                    "lock_mode": "Row-X (SX)",
                    "object_id": 12345,
                    "recommendation": "使用SELECT FOR UPDATE NOWAIT避免长时间等待",
                }
            ],
        }


# 注册会话分析工具
def register_session_tools(registry):
    """注册所有会话分析工具"""
    tools = [
        SessionListTool(),
        SessionDetailTool(),
        ConnectionPoolTool(),
        DeadlockDetectionTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return tools
