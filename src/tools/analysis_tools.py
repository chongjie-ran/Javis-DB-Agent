"""分析类工具集"""
import time
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


class AnalyzeImpactTool(BaseTool):
    """影响范围分析工具"""
    
    definition = ToolDefinition(
        name="analyze_impact",
        description="分析操作或故障的影响范围",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="scope", type="string", description="影响范围类型: session/instance/database/all", required=False, default="instance"),
        ],
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        scope = params.get("scope", "instance")
        
        data = {
            "instance_id": instance_id,
            "scope": scope,
            "affected_sessions": 3 if scope in ["session", "all"] else 0,
            "affected_connections": 15 if scope in ["instance", "all"] else 0,
            "estimated_users_impact": 150 if scope in ["instance", "all"] else 0,
            "business_impact": "中等 - 部分订单处理可能延迟" if scope in ["instance", "all"] else "低",
            "recovery_time_estimate": "5-15分钟",
        }
        
        return ToolResult(success=True, data=data)


class AnalyzeSQLPatternTool(BaseTool):
    """SQL模式分析工具"""
    
    definition = ToolDefinition(
        name="analyze_sql_pattern",
        description="分析SQL语句的模式和特征",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(name="sql_text", type="string", description="SQL文本", required=True),
            ToolParam(name="pattern_type", type="string", description="分析类型: structure/performance/security", required=False, default="structure"),
        ],
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        sql_text = params["sql_text"]
        pattern_type = params.get("pattern_type", "structure")
        
        # 简单模式分析
        data = {
            "sql_text": sql_text[:100] + "..." if len(sql_text) > 100 else sql_text,
            "pattern_type": pattern_type,
            "statement_type": "SELECT" if sql_text.strip().upper().startswith("SELECT") else "UNKNOWN",
            "table_count": sql_text.upper().count("FROM") + sql_text.upper().count("JOIN"),
            "join_detected": "JOIN" in sql_text.upper(),
            "subquery_detected": "SELECT" in sql_text.upper()[7:] if len(sql_text) > 7 else False,
            "has_limit": "LIMIT" in sql_text.upper() or "ROWNUM" in sql_text.upper(),
            "has_order_by": "ORDER BY" in sql_text.upper(),
            "estimated_complexity": "high" if sql_text.upper().count("SELECT") > 1 else "medium" if "JOIN" in sql_text.upper() else "low",
        }
        
        return ToolResult(success=True, data=data)


class DiagnoseAlertTool(BaseTool):
    """告警诊断工具（辅助）"""
    
    definition = ToolDefinition(
        name="diagnose_alert",
        description="对告警进行自动诊断，匹配知识库规则",
        category="analysis",
        risk_level=RiskLevel.L2_DIAGNOSE,
        params=[
            ToolParam(name="alert_type", type="string", description="告警类型", required=True),
            ToolParam(name="severity", type="string", description="严重程度", required=False),
        ],
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        alert_type = params["alert_type"]
        severity = params.get("severity", "unknown")
        
        # 模拟诊断规则
        rules = {
            "LOCK_WAIT_TIMEOUT": {
                "root_cause": "长事务持有锁或未提交事务",
                "confidence": 0.85,
                "check_steps": ["查看会话详情", "分析阻塞链", "识别持有者"],
                "resolution": "确认后可kill阻塞会话",
            },
            "SLOW_QUERY": {
                "root_cause": "SQL缺少索引或执行计划不当",
                "confidence": 0.80,
                "check_steps": ["查看执行计划", "检查索引", "分析统计信息"],
                "resolution": "添加索引或优化SQL",
            },
            "REPLICATION_LAG": {
                "root_cause": "从库延迟过大，网络或负载问题",
                "confidence": 0.75,
                "check_steps": ["检查从库负载", "查看网络延迟", "分析binlog应用"],
                "resolution": "优化从库性能或调整复制架构",
            },
        }
        
        rule = rules.get(alert_type, {
            "root_cause": "未知原因，需进一步分析",
            "confidence": 0.3,
            "check_steps": ["收集更多信息"],
            "resolution": "人工介入",
        })
        
        return ToolResult(success=True, data=rule)


# 注册所有分析工具
def register_analysis_tools(registry):
    """注册所有分析工具"""
    tools = [
        AnalyzeImpactTool(),
        AnalyzeSQLPatternTool(),
        DiagnoseAlertTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return tools
