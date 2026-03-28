"""补充查询类工具集 - 第二轮迭代新增"""
import time
from typing import Any
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


# ============================================================================
# 查询工具：表空间信息
# ============================================================================
class QueryTablespaceTool(BaseTool):
    """查询表空间信息"""
    
    definition = ToolDefinition(
        name="query_tablespace",
        description="查询数据库表空间使用情况，包括数据文件、自动扩展等",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="tablespace_name", type="string", description="表空间名称（可选，不传则查全部）", required=False),
        ],
        pre_check="确认实例ID有效",
        post_check="确认返回数据完整",
        example="query_tablespace(instance_id='INS-001', tablespace_name='SYSTEM')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        tablespace_name = params.get("tablespace_name")
        
        # 模拟表空间数据
        tablespaces = [
            {
                "tablespace_name": "SYSTEM",
                "status": "ONLINE",
                "total_size_mb": 1024 * 10,
                "used_size_mb": 1024 * 8,
                "free_size_mb": 1024 * 2,
                "usage_percent": 80.0,
                "auto_extensible": True,
                "max_size_mb": 1024 * 32,
                "data_files": 1,
            },
            {
                "tablespace_name": "USERS",
                "status": "ONLINE",
                "total_size_mb": 1024 * 5,
                "used_size_mb": 1024 * 3,
                "free_size_mb": 1024 * 2,
                "usage_percent": 60.0,
                "auto_extensible": True,
                "max_size_mb": 1024 * 20,
                "data_files": 1,
            },
            {
                "tablespace_name": "UNDO_TBS",
                "status": "ONLINE",
                "total_size_mb": 1024 * 8,
                "used_size_mb": 1024 * 4,
                "free_size_mb": 1024 * 4,
                "usage_percent": 50.0,
                "auto_extensible": True,
                "max_size_mb": 1024 * 16,
                "data_files": 1,
            },
            {
                "tablespace_name": "TEMP_TBS",
                "status": "ONLINE",
                "total_size_mb": 1024 * 4,
                "used_size_mb": 1024 * 0.5,
                "free_size_mb": 1024 * 3.5,
                "usage_percent": 12.5,
                "auto_extensible": True,
                "max_size_mb": 1024 * 16,
                "data_files": 1,
            },
        ]
        
        if tablespace_name:
            tablespaces = [t for t in tablespaces if t["tablespace_name"] == tablespace_name]
        
        data = {
            "instance_id": instance_id,
            "tablespaces": tablespaces,
            "total_count": len(tablespaces),
            "timestamp": time.time(),
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 查询工具：进程列表
# ============================================================================
class QueryProcesslistTool(BaseTool):
    """查询数据库进程列表"""
    
    definition = ToolDefinition(
        name="query_processlist",
        description="查询数据库当前运行的进程和连接信息",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="limit", type="int", description="返回条数限制", required=False, default=20, constraints={"min": 1, "max": 100}),
            ToolParam(name="filter", type="string", description="过滤条件，如 'command=Sleep'", required=False),
        ],
        pre_check="确认实例ID有效",
        post_check="确认返回数据合理",
        example="query_processlist(instance_id='INS-001', limit=50)"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        limit = params.get("limit", 20)
        
        # 模拟进程数据
        processes = [
            {
                "pid": 10001 + i,
                "user": "app_user",
                "host": f"192.168.1.{10+i%5}",
                "db": "orders_db",
                "command": "Sleep" if i % 4 == 0 else "Query",
                "time": i * 10,
                "state": "starting" if i % 5 == 0 else "executing",
                "sql_text": f"SELECT * FROM orders WHERE id = {i}" if i % 4 != 0 else None,
                "info": f"SQL_{i}" if i % 4 != 0 else "Binlog dump",
            }
            for i in range(min(limit, 30))
        ]
        
        data = {
            "instance_id": instance_id,
            "processes": processes,
            "total": len(processes),
            "connection_count": len(processes),
            "active_count": sum(1 for p in processes if p["command"] == "Query"),
            "timestamp": time.time(),
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 查询工具：审计日志
# ============================================================================
class QueryAuditLogTool(BaseTool):
    """查询审计日志"""
    
    definition = ToolDefinition(
        name="query_audit_log",
        description="查询数据库审计日志，记录特权操作和安全事件",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="start_time", type="string", description="开始时间 (ISO格式)", required=False),
            ToolParam(name="end_time", type="string", description="结束时间 (ISO格式)", required=False),
            ToolParam(name="limit", type="int", description="返回条数", required=False, default=50, constraints={"min": 1, "max": 200}),
            ToolParam(name="operation_type", type="string", description="操作类型: LOGON/LOGOFF/SELECT/INSERT/UPDATE/DELETE/DDL", required=False),
        ],
        pre_check="确认实例ID有效",
        post_check="确认返回数据合规",
        example="query_audit_log(instance_id='INS-001', operation_type='DELETE', limit=100)"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        limit = params.get("limit", 50)
        operation_type = params.get("operation_type")
        
        # 模拟审计日志
        operations = ["LOGON", "LOGOFF", "SELECT", "INSERT", "UPDATE", "DELETE", "DDL", "CREATE", "DROP"]
        logs = [
            {
                "audit_id": f"AUD-{int(time.time()) - i*60}",
                "timestamp": time.time() - i * 300,
                "user": f"app_user_{i%3}" if i % 5 != 0 else "dba_admin",
                "user_host": f"192.168.1.{20+i%10}",
                "operation": operations[i % len(operations)],
                "object_owner": "app_schema" if i % 3 == 0 else "public",
                "object_name": f"table_{i%10}" if i % 4 != 0 else None,
                "sql_text": f"DELETE FROM orders WHERE id = {i}" if operations[i % len(operations)] == "DELETE" else None,
                "status": "SUCCESS" if i % 10 != 0 else "FAILED",
                "error_code": None if i % 10 != 0 else 1045,
                "client_ip": f"10.0.0.{i%20}",
            }
            for i in range(min(limit, 50))
        ]
        
        if operation_type:
            logs = [log for log in logs if log["operation"] == operation_type]
        
        data = {
            "instance_id": instance_id,
            "logs": logs,
            "total": len(logs),
            "timestamp": time.time(),
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 查询工具：备份状态
# ============================================================================
class QueryBackupStatusTool(BaseTool):
    """查询数据库备份状态"""
    
    definition = ToolDefinition(
        name="query_backup_status",
        description="查询数据库备份状态和历史",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="backup_type", type="string", description="备份类型: full/incremental/archive_log", required=False),
        ],
        pre_check="确认实例ID有效",
        post_check="确认备份状态合理",
        example="query_backup_status(instance_id='INS-001', backup_type='full')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        backup_type = params.get("backup_type")
        
        # 模拟备份数据
        backups = [
            {
                "backup_id": f"BK-{int(time.time()) - 86400}",
                "backup_type": "full",
                "status": "completed",
                "start_time": time.time() - 86400,
                "end_time": time.time() - 86400 + 3600,
                "duration_seconds": 3600,
                "size_mb": 1024 * 15,
                "backupset_location": "/backup/full_20260327",
                "device_type": "disk",
            },
            {
                "backup_id": f"BK-{int(time.time()) - 172800}",
                "backup_type": "full",
                "status": "completed",
                "start_time": time.time() - 172800,
                "end_time": time.time() - 172800 + 4000,
                "duration_seconds": 4000,
                "size_mb": 1024 * 14,
                "backupset_location": "/backup/full_20260326",
                "device_type": "disk",
            },
        ]
        
        # 添加增量备份
        for i in range(5):
            backups.append({
                "backup_id": f"BK-{int(time.time()) - 86400*3 - i*86400}",
                "backup_type": "incremental",
                "status": "completed",
                "start_time": time.time() - 86400 * 3 - i * 86400,
                "end_time": time.time() - 86400 * 3 - i * 86400 + 600,
                "duration_seconds": 600,
                "size_mb": 1024 * 2,
                "backupset_location": f"/backup/incr_202603{24-i}_",
                "device_type": "disk",
            })
        
        if backup_type:
            backups = [b for b in backups if b["backup_type"] == backup_type]
        
        data = {
            "instance_id": instance_id,
            "backups": backups,
            "total": len(backups),
            "latest_full_backup": backups[0] if any(b["backup_type"] == "full" for b in backups) else None,
            "backup_policy": {
                "full_backup_schedule": "daily 02:00",
                "incremental_backup_schedule": "every 6 hours",
                "archive_log_backup": "every 15 minutes",
                "retention_days": 7,
            },
            "timestamp": time.time(),
        }
        
        return ToolResult(success=True, data=data)


# 注册所有补充查询工具
def register_additional_query_tools(registry):
    """注册补充查询工具到工具注册中心"""
    tools = [
        QueryTablespaceTool(),
        QueryProcesslistTool(),
        QueryAuditLogTool(),
        QueryBackupStatusTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return tools
