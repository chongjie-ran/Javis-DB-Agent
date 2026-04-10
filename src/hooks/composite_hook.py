"""CompositeHook - 组合多个Hook，错误隔离 (V3.0 Phase 0)"""

from typing import Optional
import logging
import time

from .hook import AgentHook
from .hook_context import AgentHookContext

logger = logging.getLogger(__name__)


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

    def on_start(self, ctx: AgentHookContext) -> AgentHookContext:
        return self._call("on_start", ctx)


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
