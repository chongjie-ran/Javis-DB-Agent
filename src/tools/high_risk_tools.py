"""高风险工具集 - 第二轮迭代新增"""
import time
from typing import Any
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


# ============================================================================
# 高风险操作工具：终止会话
# ============================================================================
class KillSessionTool(BaseTool):
    """终止数据库会话（高风险操作）"""
    
    definition = ToolDefinition(
        name="kill_session",
        description="强制终止指定的数据库会话，用于解除锁等待或处理异常会话",
        category="action",
        risk_level=RiskLevel.L5_HIGH,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="session_id", type="string", description="会话ID (sid:serial#)", required=True),
            ToolParam(name="reason", type="string", description="终止原因", required=True),
            ToolParam(name="confirm", type="bool", description="确认执行（必须为true）", required=True, default=False),
        ],
        pre_check="确认会话ID正确、已评估影响范围、获得必要审批",
        post_check="确认会话已终止、验证业务影响",
        example="kill_session(instance_id='INS-001', session_id='1001:2001', reason='锁等待超时', confirm=True)"
    )
    
    async def pre_execute(self, params: dict, context: dict) -> tuple[bool, Optional[str]]:
        """执行前检查"""
        if not params.get("confirm"):
            return False, "终止会话是高风险操作，需要显式确认 (confirm=true)"
        if not params.get("reason"):
            return False, "必须提供终止原因"
        return True, None
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        session_id = params["session_id"]
        reason = params["reason"]
        
        # 模拟终止会话
        sid, serial = session_id.split(":") if ":" in session_id else (session_id, "0")
        
        data = {
            "task_id": f"KILL-{int(time.time())}",
            "instance_id": instance_id,
            "session_id": session_id,
            "sid": int(sid),
            "serial": int(serial),
            "reason": reason,
            "status": "completed",
            "executed_at": time.time(),
            "affected_connections": 1,
            "note": "会话已强制终止，请确认业务影响",
        }
        
        return ToolResult(success=True, data=data)


# ============================================================================
# 分析工具：执行计划分析
# ============================================================================
class AnalyzeExplainPlanTool(BaseTool):
    """SQL执行计划分析"""
    
    definition = ToolDefinition(
        name="analyze_explain_plan",
        description="获取并分析SQL执行计划，识别性能问题",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(name="sql_text", type="string", description="SQL文本", required=True),
            ToolParam(name="instance_id", type="string", description="实例ID", required=False),
            ToolParam(name="format", type="string", description="输出格式: text/json", required=False, default="text"),
        ],
        pre_check="确认SQL文本正确",
        post_check="确认执行计划完整",
        example="analyze_explain_plan(sql_text='SELECT * FROM orders WHERE status = \"pending\"')"
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        sql_text = params["sql_text"]
        output_format = params.get("format", "text")
        
        # 模拟执行计划分析
        plan = [
            {
                "id": 0,
                "operation": "SELECT",
                "object_name": None,
                "optimizer": "ALL_ROWS",
                "cost": 150,
                "cardinality": 1000,
                "bytes": 50000,
                "time": "00:00:01.50",
                "parent_id": None,
                "children": [1],
            },
            {
                "id": 1,
                "operation": "TABLE ACCESS FULL",
                "object_name": "ORDERS",
                "optimizer": "ALL_ROWS",
                "cost": 150,
                "cardinality": 1000,
                "bytes": 50000,
                "time": "00:00:01.50",
                "parent_id": 0,
                "filter_predicate": "STATUS='pending'",
                "access_predicate": None,
            },
            {
                "id": 2,
                "operation": "TABLE ACCESS FULL",
                "object_name": "CUSTOMERS",
                "optimizer": "ALL_ROWS",
                "cost": 50,
                "cardinality": 10000,
                "bytes": 300000,
                "time": "00:00:00.30",
                "parent_id": 1,
                "filter_predicate": None,
                "access_predicate": "CUSTOMER_ID=ORDERS.CUSTOMER_ID",
            },
        ]
        
        # 分析结果
        issues = []
        warnings = []
        
        # 检查是否有全表扫描
        for step in plan:
            if step.get("operation") == "TABLE ACCESS FULL":
                issues.append({
                    "severity": "high",
                    "type": "FULL_TABLE_SCAN",
                    "message": f"检测到全表扫描: {step.get('object_name')}",
                    "recommendation": "考虑添加索引或优化WHERE条件",
                    "estimated_cost": step.get("cost", 0),
                })
        
        # 检查cost
        total_cost = sum(step.get("cost", 0) for step in plan)
        if total_cost > 1000:
            warnings.append({
                "severity": "medium",
                "type": "HIGH_TOTAL_COST",
                "message": f"执行计划总cost较高: {total_cost}",
                "recommendation": "考虑优化SQL或添加合适索引",
            })
        
        data = {
            "sql_text": sql_text[:100] + "..." if len(sql_text) > 100 else sql_text,
            "plan": plan,
            "total_cost": total_cost,
            "estimated_time": "00:00:01.80",
            "issues": issues,
            "warnings": warnings,
            "recommendations": [
                "在ORDERS表的STATUS列上创建索引",
                "考虑添加复合索引 (STATUS, CREATED_AT)",
                "如果ORDERS表数据量大，可考虑分区",
            ],
            "format": output_format,
            "timestamp": time.time(),
        }
        
        return ToolResult(success=True, data=data)


# 注册高风险工具
def register_high_risk_tools(registry):
    """注册高风险工具"""
    tools = [
        KillSessionTool(),
        AnalyzeExplainPlanTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return tools
