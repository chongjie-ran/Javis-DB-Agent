"""RuleEngine - 规则评估引擎"""
import logging
from typing import Optional

from .hook_event import HookEvent
from .hook_context import HookContext
from .hook_rule import HookRule, HookAction
from .hook_registry import HookRegistry

logger = logging.getLogger(__name__)


class RuleEngine:
    """
    规则评估引擎

    负责：
    1. 加载匹配规则
    2. 按优先级评估条件
    3. 执行对应的动作
    """

    def __init__(self, registry: Optional[HookRegistry] = None):
        self._registry = registry

    @property
    def registry(self) -> HookRegistry:
        if self._registry is None:
            from .hook_registry import get_hook_registry
            self._registry = get_hook_registry()
        return self._registry

    async def evaluate(
        self,
        context: HookContext,
        event: Optional[HookEvent] = None
    ) -> HookContext:
        """
        评估所有匹配的规则

        按优先级顺序执行所有匹配的规则，
        BLOCK 动作会立即设置 context.blocked 并停止执行。
        """
        event = event or context.event
        rules = self.registry.list_hooks(event)
        context_dict = context.to_dict()

        for rule in rules:
            if not rule.matches(context_dict):
                continue

            logger.debug(f"Rule matched: {rule.name} for event {event.value}")

            # 如果已被更高级别规则阻止，跳过
            if context.blocked and rule.action != HookAction.MODIFY:
                continue

            # 执行规则处理器（如果存在）
            if rule.handler:
                try:
                    context = await rule.handler(context)
                    if context.blocked:
                        break
                except Exception as e:
                    logger.error(f"Hook handler error in rule {rule.name}: {e}")
                    continue

            # 执行动作
            context = self._execute_action(context, rule)

            # BLOCK 动作立即停止
            if context.blocked:
                logger.info(f"Hook blocked by rule: {rule.name} - {context.blocked_reason}")
                break

        return context

    def _execute_action(
        self,
        context: HookContext,
        rule: HookRule
    ) -> HookContext:
        """执行规则动作"""
        action = rule.action

        if action == HookAction.BLOCK:
            context.set_blocked(rule.message or f"Blocked by rule: {rule.name}")

        elif action == HookAction.WARN:
            warning_msg = rule.message or f"Warning from rule: {rule.name}"
            context.add_warning(warning_msg)
            logger.warning(f"Hook warning: {warning_msg}")

        elif action == HookAction.LOG:
            logger.info(f"Hook log [{rule.name}]: event={context.event.value}, "
                       f"user={context.user_id}, session={context.session_id}")

        elif action == HookAction.MODIFY:
            # MODIFY 动作由 handler 处理，这里仅记录
            logger.debug(f"Hook modify: {rule.name}")

        return context

    def check_blocked(
        self,
        event: HookEvent,
        context_dict: dict
    ) -> tuple[bool, str]:
        """
        快速检查是否会被阻止（同步版本，用于 Gate 层）
        """
        rules = self.registry.list_hooks(event)

        for rule in rules:
            if not rule.enabled:
                continue
            if not rule.matches(context_dict):
                continue

            if rule.action == HookAction.BLOCK:
                return True, rule.message or f"Blocked by rule: {rule.name}"

        return False, ""
