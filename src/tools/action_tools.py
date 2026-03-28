"""执行类工具集"""
import time
from src.tools.base import BaseTool, ToolDefinition, ToolParam, RiskLevel, ToolResult


class TriggerInspectionTool(BaseTool):
    """触发巡检工具"""
    
    definition = ToolDefinition(
        name="trigger_inspection",
        description="触发一次指定类型的健康巡检",
        category="action",
        risk_level=RiskLevel.L3_LOW_RISK,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="inspection_type", type="string", description="巡检类型: quick/full/security", required=False, default="quick"),
        ],
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        instance_id = params["instance_id"]
        inspection_type = params.get("inspection_type", "quick")
        
        # 模拟触发巡检
        data = {
            "task_id": f"INS-{int(time.time())}",
            "instance_id": instance_id,
            "inspection_type": inspection_type,
            "status": "pending",
            "started_at": time.time(),
            "estimated_duration_seconds": 60 if inspection_type == "quick" else 300,
        }
        
        return ToolResult(success=True, data=data)


class SendNotificationTool(BaseTool):
    """发送通知工具"""
    
    definition = ToolDefinition(
        name="send_notification",
        description="发送通知消息（邮件/企微/飞书）",
        category="action",
        risk_level=RiskLevel.L3_LOW_RISK,
        params=[
            ToolParam(name="channel", type="string", description="通知渠道: email/wecom/feishu", required=True),
            ToolParam(name="recipient", type="string", description="接收人", required=True),
            ToolParam(name="title", type="string", description="通知标题", required=True),
            ToolParam(name="content", type="string", description="通知内容", required=True),
        ],
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        channel = params["channel"]
        recipient = params["recipient"]
        title = params["title"]
        
        data = {
            "notification_id": f"NOTIF-{int(time.time())}",
            "channel": channel,
            "recipient": recipient,
            "title": title,
            "status": "sent",
            "sent_at": time.time(),
        }
        
        return ToolResult(success=True, data=data)


class RefreshSamplingTool(BaseTool):
    """刷新采样工具"""
    
    definition = ToolDefinition(
        name="refresh_sampling",
        description="刷新性能采样数据",
        category="action",
        risk_level=RiskLevel.L3_LOW_RISK,
        params=[
            ToolParam(name="instance_id", type="string", description="实例ID", required=True),
            ToolParam(name="sampling_type", type="string", description="采样类型: session/sql/performance", required=False, default="session"),
        ],
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        data = {
            "status": "refreshed",
            "refreshed_at": time.time(),
        }
        return ToolResult(success=True, data=data)


class CreateWorkOrderTool(BaseTool):
    """创建工单工具"""
    
    definition = ToolDefinition(
        name="create_work_order",
        description="创建运维工单",
        category="action",
        risk_level=RiskLevel.L4_MEDIUM,
        params=[
            ToolParam(name="title", type="string", description="工单标题", required=True),
            ToolParam(name="description", type="string", description="工单描述", required=True),
            ToolParam(name="priority", type="string", description="优先级: low/medium/high/critical", required=False, default="medium"),
            ToolParam(name="instance_id", type="string", description="关联实例ID", required=False),
        ],
    )
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        data = {
            "work_order_id": f"WO-{int(time.time())}",
            "title": params["title"],
            "status": "created",
            "created_at": time.time(),
        }
        return ToolResult(success=True, data=data)


# 注册所有执行工具
def register_action_tools(registry):
    """注册所有执行工具"""
    tools = [
        TriggerInspectionTool(),
        SendNotificationTool(),
        RefreshSamplingTool(),
        CreateWorkOrderTool(),
    ]
    for tool in tools:
        registry.register(tool)
    return tools
