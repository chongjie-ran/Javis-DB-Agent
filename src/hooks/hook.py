"""AgentHook - Agent层Hook基类 (V3.0 Phase 0)"""

from abc import ABC
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hook_context import AgentHookContext

import logging

logger = logging.getLogger(__name__)


class AgentHook(ABC):
    """
    Agent层Hook抽象基类

    所有Agent层Hook的基类。子类选择性地override感兴趣的Hook点。

    Attributes:
        name: Hook名称（用于日志和调试）
        priority: 优先级（数字越小越高，默认100）
        enabled: 是否启用（默认True）

    Hook方法返回值：
        返回修改后的AgentHookContext。
        如果返回None，视为保持原上下文不变。
        如果设置ctx.blocked=True，AgentRunner会停止迭代。

    注意：
        - 所有Hook方法都是同步的，如有异步需求在方法内部创建task
        - 一个Hook失败（抛异常）不影响其他Hook（错误隔离）
    """

    name: str = ""
    priority: int = 100
    enabled: bool = True

    def before_iteration(self, ctx: "AgentHookContext") -> "AgentHookContext":
        """
        每次迭代开始前调用

        用途：
        - Phase 6: 探索/执行模式切换
        - Phase 5: 任务分类
        - 迭代计数检查

        Args:
            ctx: 迭代上下文（含iteration/max_iterations）

        Returns:
            修改后的ctx（可设置blocked停止迭代）
        """
        return ctx

    def after_iteration(self, ctx: "AgentHookContext") -> "AgentHookContext":
        """
        每次迭代结束后调用

        用途：
        - Phase 3: 对抗性验证（检测完成声明）
        - Phase 4: 自我合理化防护（检测信号词）
        - Phase 2: Token监控（记忆整合触发）
        - 迭代结果分析

        Args:
            ctx: 含llm_response/tool_results/iteration信息

        Returns:
            修改后的ctx
        """
        return ctx

    def before_llm(self, ctx: "AgentHookContext") -> "AgentHookContext":
        """
        LLM调用前调用

        用途：
        - Prompt增强
        - 上下文注入
        - 指令完整性检查

        Returns:
            修改后的ctx（可修改goal）
        """
        return ctx

    def after_llm(self, ctx: "AgentHookContext") -> "AgentHookContext":
        """
        LLM调用后调用（非流式）

        用途：
        - 响应分析
        - 结果记录
        - 安全检查

        Args:
            ctx: 含llm_response

        Returns:
            修改后的ctx
        """
        return ctx

    def on_stream(self, ctx: "AgentHookContext", chunk: str) -> "AgentHookContext":
        """
        LLM流式输出时的每个chunk回调

        用途：
        - 流式日志
        - 实时监控
        - 累积stream_buffer

        注意：
        - 此方法会被高频调用，忌做重操作
        - ctx.stream_chunk会累积所有chunks

        Args:
            ctx: 含累积的stream_chunk
            chunk: 当前chunk字符串

        Returns:
            修改后的ctx
        """
        ctx.stream_chunk += chunk
        return ctx

    def before_execute_tools(self, ctx: "AgentHookContext") -> "AgentHookContext":
        """
        工具执行前调用

        用途：
        - Phase 5: 任务分类（READ_ONLY/WRITE_SAME_FILE/WRITE_DIFF_FILE/VERIFY）
        - Phase 1: 指令完整性验证
        - 工具参数检查

        Args:
            ctx: 含tools_to_execute列表

        Returns:
            修改后的ctx（可修改tools_to_execute）
        """
        return ctx

    def after_execute_tools(self, ctx: "AgentHookContext") -> "AgentHookContext":
        """
        工具执行后调用

        用途：
        - 工具结果分析
        - 错误处理
        - 结果记录

        Args:
            ctx: 含tool_results列表

        Returns:
            修改后的ctx
        """
        return ctx

    def on_error(self, ctx: "AgentHookContext", error: Exception) -> "AgentHookContext":
        """
        任何步骤发生异常时调用

        用途：
        - 错误日志
        - 错误恢复
        - 告警触发

        Args:
            ctx: 当前上下文
            error: 异常对象

        Returns:
            修改后的ctx（可设置blocked停止迭代）
        """
        ctx.error = error
        ctx.add_warning(f"Hook on_error: {type(error).__name__}: {str(error)}")
        return ctx

    def on_complete(self, ctx: "AgentHookContext") -> "AgentHookContext":
        """
        迭代正常完成时调用（is_complete()返回True）

        用途：
        - Phase 2: 长期记忆归档
        - 结果总结
        - 审计日志

        Returns:
            修改后的ctx
        """
        return ctx
