"""
AgentHook生命周期系统 (V3.0 Phase 0)

参考nanobot的Hook设计，提供Agent层的生命周期钩子。
是Phase 1-6所有机制的基座。

设计原则：
1. 错误隔离：一个Hook失败不影响其他Hook
2. 优先级排序：数字越小优先级越高
3. 最小接口：AgentHook的8个方法都有默认空实现
4. 分层清晰：与gateway/hooks互补（Tool层 vs Agent层）

Hook调用顺序（单次迭代）：
    before_iteration
        ↓
    before_execute_tools → tools() → after_execute_tools
        ↓
    before_llm → [on_stream × N] → after_llm
        ↓
    after_iteration  ← (loop)

异常路径：
    on_error (任何步骤的异常都会触发)

完成路径：
    on_complete (is_complete()为True时触发)

使用示例：
    class MyHook(AgentHook):
        priority = 50  # 默认优先级

        def after_iteration(self, ctx: AgentHookContext) -> AgentHookContext:
            if ctx.iteration > 3:
                ctx.set_blocked("超过3次迭代，强制停止")
            return ctx

    hooks = CompositeHook([MyHook()])
    runner = AgentRunner(hooks=hooks)
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable
import logging
import asyncio
from dataclasses import dataclass, field

from .events import AgentHookEvent
from .context import AgentHookContext

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# AgentHook 基类
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# 工具Hook实现示例（Phase 1-6会用到，放在这里作为参考）
# ─────────────────────────────────────────────────────────────────────────────

class LoggingHook(AgentHook):
    """日志Hook（调试用）"""

    name = "logging_hook"
    priority = 999  # 最后执行

    def before_iteration(self, ctx):
        logger.info(f"[Hook] before_iteration iter={ctx.iteration}")
        return ctx

    def after_iteration(self, ctx):
        logger.info(f"[Hook] after_iteration iter={ctx.iteration} stop={ctx.stop_reason}")
        return ctx

    def on_error(self, ctx, error):
        logger.error(f"[Hook] on_error: {error}")
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# CompositeHook - 组合多个Hook，错误隔离
# ─────────────────────────────────────────────────────────────────────────────

class CompositeHook:
    """
    组合多个Hook，支持错误隔离和优先级排序

    设计原则：
    1. 错误隔离：单个Hook抛异常不影响其他Hook
    2. 优先级：priority数字小的先执行
    3. 链式修改：后执行的Hook看到前一个Hook的修改结果

    使用示例：
        composite = CompositeHook([
            TokenMonitorHook(),      # priority=10
            SelfJustificationGuard(), # priority=20
            LoggingHook(),            # priority=999
        ])
        ctx = composite.after_iteration(ctx)
    """

    def __init__(self, hooks: list[AgentHook] | None = None):
        self._hooks: list[AgentHook] = []
        if hooks:
            for h in hooks:
                self.register(h)

    def register(self, hook: AgentHook) -> None:
        """注册Hook（按优先级自动排序）"""
        if not hook.enabled:
            return
        self._hooks.append(hook)
        self._hooks.sort(key=lambda h: h.priority)
        logger.debug(f"Registered hook: {hook.name} (priority={hook.priority})")

    def unregister(self, name: str) -> bool:
        """按名称注销Hook"""
        for i, h in enumerate(self._hooks):
            if h.name == name:
                self._hooks.pop(i)
                logger.debug(f"Unregistered hook: {name}")
                return True
        return False

    def get(self, name: str) -> Optional[AgentHook]:
        for h in self._hooks:
            if h.name == name:
                return h
        return None

    def list_hooks(self) -> list[AgentHook]:
        return list(self._hooks)

    def clear(self) -> None:
        self._hooks.clear()

    # ── Hook点调用方法 ────────────────────────────────────────

    def _call(self, method_name: str, ctx: AgentHookContext, *args, **kwargs) -> AgentHookContext:
        """统一调用逻辑：错误隔离 + 优先级排序"""
        for hook in self._hooks:
            if not hook.enabled:
                continue
            try:
                method = getattr(hook, method_name, None)
                if method and callable(method):
                    result = method(ctx, *args, **kwargs)
                    if result is not None:
                        ctx = result
            except Exception as e:
                logger.warning(
                    f"[CompositeHook] Hook {hook.name}.{method_name} failed: "
                    f"{type(e).__name__}: {str(e)}",
                    exc_info=True,
                )
                # 错误隔离：继续执行下一个Hook
        return ctx

    def before_iteration(self, ctx: AgentHookContext) -> AgentHookContext:
        return self._call("before_iteration", ctx)

    def after_iteration(self, ctx: AgentHookContext) -> AgentHookContext:
        return self._call("after_iteration", ctx)

    def before_llm(self, ctx: AgentHookContext) -> AgentHookContext:
        return self._call("before_llm", ctx)

    def after_llm(self, ctx: AgentHookContext) -> AgentHookContext:
        return self._call("after_llm", ctx)

    def on_stream(self, ctx: AgentHookContext, chunk: str) -> AgentHookContext:
        return self._call("on_stream", ctx, chunk)

    def before_execute_tools(self, ctx: AgentHookContext) -> AgentHookContext:
        return self._call("before_execute_tools", ctx)

    def after_execute_tools(self, ctx: AgentHookContext) -> AgentHookContext:
        return self._call("after_execute_tools", ctx)

    def on_error(self, ctx: AgentHookContext, error: Exception) -> AgentHookContext:
        return self._call("on_error", ctx, error)

    def on_complete(self, ctx: AgentHookContext) -> AgentHookContext:
        return self._call("on_complete", ctx)


# ─────────────────────────────────────────────────────────────────────────────
# 全局CompositeHook单例
# ─────────────────────────────────────────────────────────────────────────────

_composite_hook: Optional[CompositeHook] = None


def get_composite_hook() -> CompositeHook:
    """获取全局CompositeHook单例"""
    global _composite_hook
    if _composite_hook is None:
        _composite_hook = CompositeHook()
    return _composite_hook


def reset_composite_hook() -> None:
    """重置全局Hook单例（测试用）"""
    global _composite_hook
    _composite_hook = None
