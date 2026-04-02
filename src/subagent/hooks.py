"""
Subagent模式切换Hook
在before_iteration中根据模式调整行为
"""

from src.hooks.hook import AgentHook
from src.hooks.hook_context import AgentHookContext


class SubagentModeHook(AgentHook):
    """Subagent模式切换Hook"""

    async def before_iteration(self, context: AgentHookContext) -> None:
        """根据subagent模式调整行为"""
        # 检查是否是subagent任务
        if not context.spec.get("is_subagent"):
            return

        # 根据模式调整行为
        mode = context.spec.get("subagent_mode")

        if mode == "explore":
            context.metadata["explore_mode"] = True
            context.metadata["max_time"] = 300  # 5分钟
            context.metadata["read_only"] = True
            # 限制工具集
            context.metadata["tools_restricted"] = True
        else:  # execute
            context.metadata["explore_mode"] = False
            context.metadata["max_time"] = 3600  # 60分钟
            context.metadata["read_only"] = False
            context.metadata["tools_restricted"] = False
