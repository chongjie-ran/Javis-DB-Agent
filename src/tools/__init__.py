# Tools 模块
# 提供数据库运维相关的工具集

from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult
from src.tools.query_tools import (
    register_query_tools,
    QueryInstanceStatusTool,
    QuerySessionTool,
    QueryLockTool,
    QuerySlowSQLTool,
    QueryReplicationTool,
    QueryAlertDetailTool,
    QuerySQLPlanTool,
    QueryRelatedAlertsTool,
)
from src.tools.action_tools import (
    register_action_tools,
    TriggerInspectionTool,
    SendNotificationTool,
    RefreshSamplingTool,
    CreateWorkOrderTool,
)
from src.tools.analysis_tools import (
    register_analysis_tools,
    AnalyzeImpactTool,
    AnalyzeSQLPatternTool,
    DiagnoseAlertTool,
)
from src.tools.additional_query_tools import (
    register_additional_query_tools,
    QueryTablespaceTool,
    QueryProcesslistTool,
    QueryAuditLogTool,
    QueryBackupStatusTool,
)
from src.tools.high_risk_tools import (
    register_high_risk_tools,
    KillSessionTool,
    AnalyzeExplainPlanTool,
)
from src.tools.session_tools import (
    register_session_tools,
    SessionListTool,
    SessionDetailTool,
    ConnectionPoolTool,
    DeadlockDetectionTool,
)
from src.tools.capacity_tools import (
    register_capacity_tools,
    StorageAnalysisTool,
    GrowthPredictionTool,
    CapacityReportTool,
    CapacityAlertTool,
)


def register_all_tools(registry):
    """注册所有工具到注册中心"""
    register_query_tools(registry)
    register_action_tools(registry)
    register_analysis_tools(registry)
    register_additional_query_tools(registry)
    register_high_risk_tools(registry)
    register_session_tools(registry)
    register_capacity_tools(registry)
    return registry


__all__ = [
    # 基类
    "BaseTool",
    "ToolDefinition",
    "ToolParam",
    "RiskLevel",
    "ToolResult",
    # 查询工具
    "register_query_tools",
    "QueryInstanceStatusTool",
    "QuerySessionTool",
    "QueryLockTool",
    "QuerySlowSQLTool",
    "QueryReplicationTool",
    "QueryAlertDetailTool",
    "QuerySQLPlanTool",
    # 执行工具
    "register_action_tools",
    "TriggerInspectionTool",
    "SendNotificationTool",
    "RefreshSamplingTool",
    "CreateWorkOrderTool",
    # 分析工具
    "register_analysis_tools",
    "AnalyzeImpactTool",
    "AnalyzeSQLPatternTool",
    "DiagnoseAlertTool",
    # 补充查询工具
    "register_additional_query_tools",
    "QueryTablespaceTool",
    "QueryProcesslistTool",
    "QueryAuditLogTool",
    "QueryBackupStatusTool",
    # 高风险工具
    "register_high_risk_tools",
    "KillSessionTool",
    "AnalyzeExplainPlanTool",
    # 会话分析工具
    "register_session_tools",
    "SessionListTool",
    "SessionDetailTool",
    "ConnectionPoolTool",
    "DeadlockDetectionTool",
    # 容量管理工具
    "register_capacity_tools",
    "StorageAnalysisTool",
    "GrowthPredictionTool",
    "CapacityReportTool",
    "CapacityAlertTool",
    # 全量注册
    "register_all_tools",
]
