"""ContextBudgetHook - before_iteration预算检查 + 压缩触发 (V3.2 P2)

Hook点: before_iteration
- 检查token使用是否触发阈值
- 触发AutoMemory联动（超预算时）
- 评估是否需要压缩
"""
import logging
from src.hooks.hook import AgentHook
from src.hooks.hook_context import AgentHookContext
from src.context.budget_manager import get_budget_manager
from src.context.compression import ContextCompressor

logger = logging.getLogger(__name__)


class ContextBudgetHook(AgentHook):
    """
    上下文预算Hook

    before_iteration时:
    1. 更新token计数到BudgetManager
    2. 检查阈值，触发AutoMemory联动
    3. 如果需要压缩，在context.extra中标记
    4. 当stop_reason==context_overflow时阻止执行
    """

    name: str = "context_budget"
    priority: int = 30  # 在before_iteration中较早执行

    def __init__(
        self,
        max_messages: int = 40,
        auto_memory联动_threshold: float = 100.0,
    ):
        self.budget_manager = get_budget_manager()
        self.compressor = ContextCompressor(max_messages=max_messages)
        self._联动_threshold = auto_memory联动_threshold

    def before_iteration(self, ctx: AgentHookContext) -> AgentHookContext:
        """before_iteration钩子：预算检查"""
        session_id = ctx.session_id or "default"

        # 更新token计数
        triggered = self.budget_manager.update_token_count(
            session_id, ctx.token_count
        )

        if triggered:
            logger.info(
                f"[ContextBudgetHook] Thresholds triggered: {triggered} "
                f"(session={session_id}, tokens={ctx.token_count})"
            )
            ctx.add_warning(f"token_thresholds: {', '.join(triggered)}")

        # 超预算 → 触发AutoMemory联动
        if "100.0" in triggered and self.budget_manager._auto_memory_callback:
            try:
                logger.info(f"[ContextBudgetHook] Triggering AutoMemory for session {session_id}")
                self.budget_manager._auto_memory_callback(session_id)
            except Exception as e:
                logger.error(f"[ContextBudgetHook] AutoMemory联动 failed: {e}")

        # 检查是否需要压缩
        should_compress, reason = self.budget_manager.should_compress(session_id)
        if should_compress:
            ctx.extra["_compress_needed"] = True
            ctx.extra["_compress_reason"] = reason
            logger.info(
                f"[ContextBudgetHook] Compression recommended: {reason} "
                f"(session={session_id})"
            )

        return ctx

    def after_iteration(self, ctx: AgentHookContext) -> AgentHookContext:
        """
        after_iteration钩子：执行压缩
        如果before_iteration标记了_compress_needed，执行实际压缩
        """
        session_id = ctx.session_id or "default"
        messages = ctx.extra.get("_messages")

        if ctx.extra.get("_compress_needed") and messages:
            try:
                compressed, stats = self.compressor.compress(messages)
                ctx.extra["_compressed_messages"] = compressed
                ctx.extra["_compression_stats"] = stats

                # 记录到BudgetManager
                tokens_before = ctx.token_count
                tokens_after = int(tokens_before * (1 - stats.get("reduction_percent", 30) / 100))
                self.budget_manager.record_compression(
                    session_id=session_id,
                    tokens_before=tokens_before,
                    tokens_after=tokens_after,
                    messages_removed=stats.get("removed", 0),
                    reason="threshold",
                )

                logger.info(
                    f"[ContextBudgetHook] Compression done: "
                    f"{stats.get('removed', 0)} msgs removed, "
                    f"kept={stats.get('kept_messages', len(compressed))}"
                )
            except Exception as e:
                logger.error(f"[ContextBudgetHook] Compression failed: {e}")

        return ctx
