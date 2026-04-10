"""SubagentTool - 将SubagentFactory作为Tool注册到AgentRunner (V3.2 P0)"""
from typing import Optional
from src.tools.base import BaseTool, ToolDefinition, ToolResult, RiskLevel, ToolParam
from src.subagent import SubagentFactory, quick_explore, quick_execute, PlanSpec


class SubagentTool(BaseTool):
    """Subagent工厂Tool - AgentRunner中通过此Tool调用Subagent"""

    definition = ToolDefinition(
        name="subagent",
        description="创建子Agent任务，支持探索/规划/执行三种模式",
        category="action",
        risk_level=RiskLevel.L3_LOW_RISK,
        params=[
            ToolParam(name="task", type="string", description="子任务描述", required=True),
            ToolParam(name="mode", type="string", description="模式: explore/plan/execute", required=False, default="explore"),
            ToolParam(name="timeout", type="int", description="超时秒数", required=False, default=300),
        ],
    )

    async def execute(self, params: dict, context: dict) -> ToolResult:
        """执行Subagent创建"""
        import time
        start = time.time()

        task = params.get("task", "")
        mode = params.get("mode", "explore")
        timeout = params.get("timeout", 300)

        if not task:
            return ToolResult(success=False, error="task参数不能为空", tool_name="subagent")

        # 创建Spec
        if mode == "explore":
            spec = quick_explore(task)
        elif mode == "plan":
            spec = PlanSpec(task=task)
        elif mode == "execute":
            spec = quick_execute(task)
        else:
            return ToolResult(success=False, error=f"无效模式: {mode}", tool_name="subagent")

        spec.timeout = timeout

        # 使用SubagentFactory生成配置
        config = SubagentFactory.create(spec)

        elapsed_ms = int((time.time() - start) * 1000)

        return ToolResult(
            success=True,
            data={
                "config": config,
                "session_id": context.get("session_id", ""),
                "mode": mode,
            },
            tool_name="subagent",
            execution_time_ms=elapsed_ms,
        )
