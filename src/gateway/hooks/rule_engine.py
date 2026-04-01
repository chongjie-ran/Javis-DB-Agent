"""RuleEngine - 规则评估引擎"""
import logging
from typing import Any, Optional

from .hook_event import HookEvent
from .hook_context import HookContext
from .hook_rule import HookRule, HookAction, ModifyOperation, ModifyOperationType
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
            # 执行 payload 修改
            if rule.modify_ops:
                for op in rule.modify_ops:
                    context = self._apply_modify(context, op)
            logger.debug(f"Hook modify applied: {rule.name}")

        return context

    def _apply_modify(
        self,
        context: HookContext,
        op: ModifyOperation,
    ) -> HookContext:
        """
        应用单个修改操作到 context.payload

        Args:
            context: Hook 上下文
            op: 修改操作定义

        Returns:
            修改后的 context（就地修改 payload）
        """
        field = op.field
        payload = context.payload

        if op.operation == ModifyOperationType.REPLACE:
            self._set_nested(payload, field, op.value)
            logger.debug(f"MODIFY REPLACE: {field} = {op.value}")

        elif op.operation == ModifyOperationType.REDACT:
            self._set_nested(payload, field, op.redact_with)
            logger.debug(f"MODIFY REDACT: {field} = {op.redact_with}")

        elif op.operation == ModifyOperationType.ADD:
            if self._get_nested(payload, field) is None:
                self._set_nested(payload, field, op.value)
                logger.debug(f"MODIFY ADD: {field} = {op.value}")
            else:
                logger.debug(f"MODIFY ADD skipped: {field} already exists")

        elif op.operation == ModifyOperationType.REMOVE:
            if self._remove_nested(payload, field):
                logger.debug(f"MODIFY REMOVE: {field}")
            else:
                logger.debug(f"MODIFY REMOVE skipped: {field} not found")

        elif op.operation == ModifyOperationType.CLAMP:
            current = self._get_nested(payload, field)
            if current is None:
                current = op.default_val
                self._set_nested(payload, field, current)
                logger.debug(f"MODIFY CLAMP: {field} = {current} (default, field was missing)")
            else:
                try:
                    clamped = max(op.min_val, min(int(current), op.max_val))
                    self._set_nested(payload, field, clamped)
                    logger.debug(f"MODIFY CLAMP: {field} = {clamped} (from {current})")
                except (ValueError, TypeError) as e:
                    logger.warning(f"MODIFY CLAMP skipped: cannot clamp {field} = {current}: {e}")

        return context

    def _get_nested(self, data: dict, field: str) -> Any:
        """获取嵌套字段值，如 'params.limit' 从 payload 中获取"""
        parts = field.split(".")
        current = data
        for i, part in enumerate(parts):
            if isinstance(current, dict):
                current = current.get(part)
                if current is None and i < len(parts) - 1:
                    return None
            else:
                return None
        return current

    def _set_nested(self, data: dict, field: str, value: Any) -> None:
        """设置嵌套字段值，如 'params.limit' 到 payload 中"""
        parts = field.split(".")
        current = data
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # 最后一节，直接设置
                current[part] = value
            else:
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]

    def _remove_nested(self, data: dict, field: str) -> bool:
        """删除嵌套字段，如 'params.limit' 从 payload 中删除"""
        parts = field.split(".")
        current = data
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                if part in current:
                    del current[part]
                    return True
                return False
            else:
                if part not in current or not isinstance(current[part], dict):
                    return False
                current = current[part]
        return False

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
