"""查询类工具集"""
import time
from typing import Any
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


# ============================================================================
# 查询工具：实例状态
# ============================================================================
class QueryInstanceStatusTool(BaseTool):
    """查询实例状态"""
    
    definition = ToolDefinition(
        name="query_instance_status",
        description="查询数据库实例的状态信息，包括CPU、内存、IO、连接数等",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="metrics", type="array", description="要查询的指标列表，如 ['cpu', 'memory', 'io']", required=False, default=[]),
        ],
        pre_check="确认实例ID有效",
        post_check="确认返回数据完整",
        example="query_instance_status(instance_id='INS-001', metrics=['cpu', 'memory'])"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        metrics = params.get("metrics", ["cpu", "memory", "io", "connections"])
        
        # 模拟数据（实际应从Javis API获取）
        data = {
            "instance_id": instance_id,
            "status": "running",
            "uptime_seconds": 864000,
            "cpu_usage_percent": 45.2,
            "memory_usage_percent": 68.5,
            "io_usage_percent": 30.1,
            "active_connections": 156,
            "max_connections": 500,
            "timestamp": time.time(),
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 查询工具：会话信息
# ============================================================================
class QuerySessionTool(BaseTool):
    """查询会话信息"""
    
    definition = ToolDefinition(
        name="query_session",
        description="查询数据库会话信息，包括活跃会话、等待事件等",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="limit", type="int", description="返回条数限制", required=False, default=10, constraints={"min": 1, "max": 100}),
            ToolParam(name="filter", type="string", description="过滤条件，如 'state=active'", required=False),
        ],
        example="query_session(instance_id='INS-001', limit=20)"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        limit = params.get("limit", 10)
        
        # 模拟数据
        sessions = [
            {
                "sid": 1001 + i,
                "serial#": 2001 + i,
                "username": f"APP_USER_{i}" if i % 3 else "SYS",
                "status": "ACTIVE" if i % 2 else "INACTIVE",
                "program": f"python_{i}.exe",
                "sql_id": f"sql_{'a'*8}_{i}",
                "wait_event": "db file sequential read" if i % 3 == 0 else None,
                "seconds_in_wait": 5 if i % 3 == 0 else 0,
                "machine": f"app-server-{i % 3 + 1}",
                "logon_time": time.time() - 3600 * (i + 1),
            }
            for i in range(min(limit, 10))
        ]
        
        return ToolResult(success=True, data={"sessions": sessions, "total": len(sessions)})


# ============================================================================
# 查询工具：锁信息
# ============================================================================
class QueryLockTool(BaseTool):
    """查询锁等待信息"""
    
    definition = ToolDefinition(
        name="query_lock",
        description="查询数据库锁等待和阻塞链信息",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="include_blocker", type="bool", description="是否包含阻塞者信息", required=False, default=True),
        ],
        example="query_lock(instance_id='INS-001')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        
        # 模拟锁等待数据
        locks = [
            {
                "wait_sid": 1001,
                "wait_serial": 2001,
                "wait_sql_id": "sql_aaaaaaaa",
                "lock_type": "TX",
                "mode_held": "Exclusive",
                "mode_requested": "Share",
                "lock_id1": "12345",
                "lock_id2": "67890",
                "blocker_sid": 1002,
                "blocker_serial": 2002,
                "blocker_sql_id": "sql_bbbbbbbb",
                "wait_seconds": 120,
                "chain_length": 2,
            }
        ]
        
        return ToolResult(success=True, data={"locks": locks, "total_blocked": 1})


# ============================================================================
# 查询工具：慢SQL
# ============================================================================
class QuerySlowSQLTool(BaseTool):
    """查询慢SQL"""
    
    definition = ToolDefinition(
        name="query_slow_sql",
        description="查询慢SQL和Top SQL执行统计",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="limit", type="int", description="返回条数", required=False, default=10, constraints={"min": 1, "max": 50}),
            ToolParam(name="order_by", type="string", description="排序字段: elapsed_time/executions/disk_reads", required=False, default="elapsed_time"),
        ],
        example="query_slow_sql(instance_id='INS-001', limit=5, order_by='elapsed_time')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        limit = params.get("limit", 10)
        
        queries = [
            {
                "sql_id": f"sql_{'a'*(8-i)}",
                "sql_text": f"SELECT * FROM orders WHERE status = 'pending' AND created_at > SYSDATE - {i}...",
                "executions": 1000 - i * 100,
                "execution_time_ms": int((30.5 - i * 3) * 1000),
                "avg_execution_time_ms": int((30.5 - i * 3) / max(1000 - i * 100, 1) * 1000),
                "disk_reads": 50000 - i * 5000,
                "buffer_gets": 100000 - i * 10000,
                "rows_processed": 10000 - i * 1000,
                "first_load_time": time.time() - 86400 * (i + 1),
                "last_active_time": time.time() - 3600 * (i + 1),
            }
            for i in range(min(limit, 5))
        ]
        
        return ToolResult(success=True, data={"queries": queries, "count": len(queries)})


# ============================================================================
# 查询工具：复制状态
# ============================================================================
class QueryReplicationTool(BaseTool):
    """查询主从复制状态"""
    
    definition = ToolDefinition(
        name="query_replication",
        description="查询主从复制状态和延迟",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
        ],
        example="query_replication(instance_id='INS-001')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        
        data = {
            "instance_id": instance_id,
            "role": "primary",
            "replication_enabled": True,
            "replicas": [
                {
                    "replica_id": "REP-001",
                    "host": "192.168.1.101",
                    "port": 3306,
                    "role": "read_replica",
                    "status": "streaming",
                    "lag_seconds": 2.5,
                    "lag_bytes": 102400,
                    "last_heartbeat": time.time() - 2.5,
                }
            ],
            "ha_enabled": True,
            "ha_role": "primary",
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 查询工具：告警详情
# ============================================================================
class QueryAlertDetailTool(BaseTool):
    """查询告警详情"""
    
    definition = ToolDefinition(
        name="query_alert_detail",
        description="查询指定告警的详细信息",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="alert_id", type="string", description="告警ID", required=True),
        ],
        example="query_alert_detail(alert_id='ALT-20260328-001')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        alert_id = params["alert_id"]
        
        # 模拟告警数据
        data = {
            "alert_id": alert_id,
            "alert_name": "锁等待超时",
            "alert_type": "LOCK_WAIT_TIMEOUT",
            "severity": "warning",
            "instance_id": "INS-001",
            "instance_name": "PROD-ORDER-DB",
            "occurred_at": time.time() - 300,
            "metric_value": 120.5,
            "threshold": 60.0,
            "message": "实例发生锁等待超时，当前等待时间120秒",
            "附加信息": {
                "blocked_sessions": 3,
                "blocking_session": 1002,
                "lock_mode": "TX-X",
            },
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 查询工具：SQL执行计划
# ============================================================================
class QuerySQLPlanTool(BaseTool):
    """查询SQL执行计划"""
    
    definition = ToolDefinition(
        name="query_sql_plan",
        description="获取指定SQL的执行计划",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="sql_id", type="string", description="SQL ID", required=True),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False),
        ],
        example="query_sql_plan(sql_id='sql_aaaaaaaa')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        sql_id = params["sql_id"]
        
        plan = [
            {"operation": "SELECT", "object_name": None, "cost": 100, "cardinality": 1000},
            {"operation": "  └─TABLE ACCESS FULL", "object_name": "ORDERS", "cost": 100, "cardinality": 1000, "filter": "STATUS='pending'"},
            {"operation": "    └─TABLE ACCESS FULL", "object_name": "CUSTOMERS", "cost": 50, "cardinality": 10000},
        ]
        
        return ToolResult(success=True, data={"sql_id": sql_id, "plan": plan})


# ============================================================================
# 查询工具：磁盘/表空间使用率
# ============================================================================
class QueryDiskUsageTool(BaseTool):
    """查询磁盘/表空间使用率"""
    
    definition = ToolDefinition(
        name="query_disk_usage",
        description="查询数据库磁盘使用率和表空间详情",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
        ],
        example="query_disk_usage(instance_id='INS-001')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        
        data = {
            "instance_id": instance_id,
            "disk_total_gb": 500.0,
            "disk_used_gb": 350.0,
            "disk_free_gb": 150.0,
            "disk_used_percent": 70.0,
            "tablespaces": [
                {"name": "pg_default", "used_percent": 70.0, "total_mb": 102400, "used_mb": 71680},
                {"name": "pg_global", "used_percent": 50.0, "total_mb": 8192, "used_mb": 4096},
                {"name": "orders_tbs", "used_percent": 90.0, "total_mb": 512000, "used_mb": 460800},
            ]
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 查询工具：数据库参数
# ============================================================================
class QueryParametersTool(BaseTool):
    """查询数据库参数配置"""
    
    definition = ToolDefinition(
        name="query_parameters",
        description="查询数据库实例的参数配置",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="filter", type="string", description="参数名过滤关键词", required=False),
        ],
        example="query_parameters(instance_id='INS-001', filter='connection')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        filter_keyword = params.get("filter", "")
        
        all_params = [
            {"name": "max_connections", "value": "500", "default_value": "100", "is_modified": True},
            {"name": "shared_buffers", "value": "256MB", "default_value": "128MB", "is_modified": True},
            {"name": "work_mem", "value": "4MB", "default_value": "4MB", "is_modified": False},
            {"name": "effective_cache_size", "value": "4GB", "default_value": "4GB", "is_modified": False},
            {"name": "maintenance_work_mem", "value": "64MB", "default_value": "64MB", "is_modified": False},
            {"name": "checkpoint_timeout", "value": "15min", "default_value": "5min", "is_modified": True},
        ]
        
        if filter_keyword:
            all_params = [p for p in all_params if filter_keyword.lower() in p["name"].lower()]
        
        return ToolResult(success=True, data={"parameters": all_params, "count": len(all_params)})


# ============================================================================
# 查询工具：Top SQL
# ============================================================================
class QueryTopSQLTool(BaseTool):
    """查询Top SQL（按CPU/IO/逻辑读排序）"""
    
    definition = ToolDefinition(
        name="query_top_sql",
        description="查询执行最频繁或资源消耗最高的SQL",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="sort_by", type="string", description="排序类型: cpu/buffer_gets/disk_reads", required=False, default="cpu"),
            ToolParam(name="limit", type="int", description="返回条数", required=False, default=10, constraints={"min": 1, "max": 50}),
        ],
        example="query_top_sql(instance_id='INS-001', sort_by='cpu', limit=10)"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        sort_by = params.get("sort_by", "cpu")
        limit = params.get("limit", 10)
        
        top_sqls = [
            {"sql_id": "sql_aaaa1111", "sql_text": "SELECT * FROM orders WHERE status='pending'...", "sort_type": sort_by, "value": 500.5, "executions": 100},
            {"sql_id": "sql_bbbb2222", "sql_text": "SELECT count(*) FROM sales GROUP BY region...", "sort_type": sort_by, "value": 300.2, "executions": 200},
            {"sql_id": "sql_cccc3333", "sql_text": "UPDATE inventory SET quantity=quantity-1...", "sort_type": sort_by, "value": 200.1, "executions": 50},
        ]
        
        return ToolResult(success=True, data={"top_sqls": top_sqls[:limit], "sort_by": sort_by})


# ============================================================================
# 查询工具：HA/主备状态
# ============================================================================
class QueryHAStatusTool(BaseTool):
    """查询HA/主备状态"""
    
    definition = ToolDefinition(
        name="query_ha_status",
        description="查询数据库HA状态和主备切换信息",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
        ],
        example="query_ha_status(instance_id='INS-001')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        
        data = {
            "instance_id": instance_id,
            "ha_enabled": True,
            "ha_role": "primary",
            "primary_instance": None,
            "standby_instances": ["INS-002"],
            "last_switch_time": time.time() - 86400 * 7,
            "switch_reason": "计划切换-维护",
            "health_status": "healthy",
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 查询工具：巡检结果
# ============================================================================
class GetInspectionResultTool(BaseTool):
    """获取巡检结果"""
    
    definition = ToolDefinition(
        name="get_inspection_result",
        description="获取指定巡检任务的执行结果",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="task_id", type="string", description="巡检任务ID", required=True),
        ],
        example="get_inspection_result(task_id='INS-1709000000')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        task_id = params["task_id"]
        
        findings = [
            {"type": "性能", "severity": "warning", "description": "过去1小时有5条慢SQL", "item": "slow_sql_count"},
            {"type": "容量", "severity": "info", "description": "表空间使用率78%，建议关注", "item": "tablespace_usage"},
            {"type": "连接", "severity": "info", "description": "当前连接数156/500，正常", "item": "connection_usage"},
        ]
        
        data = {
            "task_id": task_id,
            "instance_id": "INS-001",
            "inspection_type": "quick",
            "status": "completed",
            "health_score": 85,
            "started_at": time.time() - 60,
            "completed_at": time.time(),
            "findings": findings,
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 查询工具：配置偏差
# ============================================================================
class QueryConfigDeviationTool(BaseTool):
    """查询配置与标准配置的偏差"""
    
    definition = ToolDefinition(
        name="query_config_deviation",
        description="查询实例参数配置与标准配置的偏差",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
        ],
        example="query_config_deviation(instance_id='INS-001')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        
        deviations = [
            {
                "instance_id": instance_id,
                "parameter_name": "max_connections",
                "current_value": "500",
                "standard_value": "300",
                "deviation_type": "higher",
                "severity": "low",
                "description": "当前值高于标准配置30%"
            },
            {
                "instance_id": instance_id,
                "parameter_name": "checkpoint_timeout",
                "current_value": "15min",
                "standard_value": "10min",
                "deviation_type": "higher",
                "severity": "medium",
                "description": "检查点超时设置过长，可能影响恢复时间"
            }
        ]
        
        return ToolResult(success=True, data={"deviations": deviations, "count": len(deviations)})


# ============================================================================
# 查询工具：关联告警查询
# ============================================================================
class QueryRelatedAlertsTool(BaseTool):
    """
    查询关联告警
    
    这是一个关键工具，用于告警关联推理链。
    当诊断Agent发现一个告警后，可以调用此工具查找关联告警。
    """
    
    definition = ToolDefinition(
        name="query_related_alerts",
        description="查询与指定告警关联的其他告警，构建告警关联推理链",
        category="query",
        risk_level=RiskLevel.L1_READ,
        params=[
            ToolParam(name="alert_id", type="string", description="告警ID", required=True),
            ToolParam(name="instance_id", type="string", description="实例ID（可选，用于过滤）", required=False),
            ToolParam(name="time_range_seconds", type="int", description="时间范围（秒），默认600秒（10分钟）", required=False, default=600),
        ],
        example="query_related_alerts(alert_id='ALT-001', instance_id='INS-001', time_range_seconds=600)"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        """
        执行关联告警查询
        
        注意：这个工具实际调用告警关联引擎进行分析
        """
        alert_id = params["alert_id"]
        instance_id = params.get("instance_id")
        time_range_seconds = params.get("time_range_seconds", 600)
        
        # 获取Mock客户端和关联器
        mock_client = context.get("mock_client")
        correlator = context.get("alert_correlator")
        
        if not mock_client or not correlator:
            # 如果没有Mock客户端，返回模拟数据
            data = {
                "alert_id": alert_id,
                "related_alerts": [],
                "correlation_found": False,
                "message": "Mock客户端不可用，无法进行关联分析",
            }
            return ToolResult(success=True, data=data)
        
        try:
            # 获取该实例的所有活跃告警
            all_alerts = await mock_client.get_alerts(
                instance_id=instance_id,
                status="active",
            )
            
            # 执行关联分析
            correlation_result = await correlator.correlate_alerts(
                primary_alert_id=alert_id,
                all_alerts=all_alerts,
                mock_client=mock_client,
            )
            
            # 提取关联告警
            related_alerts = []
            for node in correlation_result.correlation_chain:
                if node.alert_id != alert_id:
                    related_alerts.append({
                        "alert_id": node.alert_id,
                        "alert_name": node.alert_name,
                        "alert_type": node.alert_type,
                        "severity": node.severity,
                        "instance_id": node.instance_id,
                        "instance_name": node.instance_name,
                        "role": node.role.value,
                        "confidence": node.confidence,
                        "message": node.message,
                    })
            
            data = {
                "alert_id": alert_id,
                "primary_alert": alert_id,
                "related_alerts": related_alerts,
                "correlation_found": len(related_alerts) > 0,
                "correlation_chain_length": len(correlation_result.correlation_chain),
                "diagnostic_path": correlation_result.diagnostic_path,
                "root_cause": correlation_result.root_cause,
                "confidence": correlation_result.confidence,
                "summary": correlation_result.summary,
            }
            
            return ToolResult(success=True, data=data)
            
        except Exception as e:
            return ToolResult(
                success=False,
                data={
                    "alert_id": alert_id,
                    "error": str(e),
                    "related_alerts": [],
                    "correlation_found": False,
                }
            )


# 注册所有查询工具
def register_query_tools(registry):
    """注册所有查询工具到工具注册中心"""
    tools = [
        QueryInstanceStatusTool(),
        QuerySessionTool(),
        QueryLockTool(),
        QuerySlowSQLTool(),
        QueryReplicationTool(),
        QueryAlertDetailTool(),
        QuerySQLPlanTool(),
        QueryDiskUsageTool(),
        QueryParametersTool(),
        QueryTopSQLTool(),
        QueryHAStatusTool(),
        GetInspectionResultTool(),
        QueryConfigDeviationTool(),
        QueryRelatedAlertsTool(),  # 新增：关联告警查询
    ]
    for tool in tools:
        registry.register(tool)
    return tools
