"""HookEngine - Hook 主引擎"""
import logging
from typing import Optional
from dataclasses import dataclass

from .hook_event import HookEvent
from .hook_context import HookContext
from .hook_rule import HookRule, HookAction
from .hook_registry import HookRegistry, get_hook_registry
from .rule_engine import RuleEngine

logger = logging.getLogger(__name__)


@dataclass
class HookResult:
    """
    Hook 执行结果

    Attributes:
        blocked: 是否被阻止
        message: 阻止/警告消息
        warnings: 警告列表
        event: 触发的事件
        matched_rules: 匹配的规则名称列表
    """
    blocked: bool = False
    message: str = ""
    warnings: list[str] = None
    event: HookEvent = None
    matched_rules: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.matched_rules is None:
            self.matched_rules = []

    @classmethod
    def from_context(cls, context: HookContext, matched_rules: list[str] = None) -> "HookResult":
        return cls(
            blocked=context.blocked,
            message=context.blocked_reason,
            warnings=list(context.warnings),
            event=context.event,
            matched_rules=matched_rules or [],
        )


class HookEngine:
    """
    Hook 主引擎

    提供事件驱动的 Hook 执行能力。
    是整个 Hook 系统的核心接口。

    使用方式：
        # 触发事件
        result = await HookEngine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool_name": "execute_sql", "params": {...}},
            session_id="sess_123",
            user_id="user_456",
        )

        if result.blocked:
            raise PermissionError(result.message)
    """

    def __init__(
        self,
        registry: Optional[HookRegistry] = None,
        rule_engine: Optional[RuleEngine] = None,
    ):
        self._registry = registry or get_hook_registry()
        self._rule_engine = rule_engine or RuleEngine(self._registry)

    @property
    def registry(self) -> HookRegistry:
        return self._registry

    async def emit(
        self,
        event: HookEvent,
        payload: Optional[dict] = None,
        session_id: str = "",
        user_id: str = "",
        user_role: str = "",
        **extra,
    ) -> HookResult:
        """
        触发 Hook 事件

        Args:
            event: 事件类型
            payload: 事件负载数据
            session_id: 会话 ID
            user_id: 用户 ID
            user_role: 用户角色
            **extra: 额外数据

        Returns:
            HookResult: 执行结果
        """
        # 创建上下文
        context = HookContext(
            event=event,
            payload=payload or {},
            session_id=session_id,
            user_id=user_id,
            user_role=user_role,
            extra=extra,
        )

        # 获取匹配的规则（用于记录）
        matched_rules = [
            rule.name for rule in self.registry.list_hooks(event)
            if rule.enabled and rule.matches(context.to_dict())
        ]

        # 评估规则
        context = await self._rule_engine.evaluate(context, event)

        result = HookResult.from_context(context, matched_rules)

        if result.blocked:
            logger.warning(
                f"Hook blocked: event={event.value}, "
                f"user={user_id}, reason={result.message}, "
                f"matched_rules={matched_rules}"
            )
        elif result.warnings:
            logger.info(
                f"Hook warnings: event={event.value}, "
                f"warnings={result.warnings}, matched_rules={matched_rules}"
            )

        return result

    # 同步版本，用于 Gate 层（不能 await）
    def emit_sync(
        self,
        event: HookEvent,
        payload: Optional[dict] = None,
        session_id: str = "",
        user_id: str = "",
        user_role: str = "",
        **extra,
    ) -> HookResult:
        """
        同步触发 Hook 事件（用于无法 await 的场景）

        注意：同步版本只执行 BLOCK 检查，不调用异步 handler。
        """
        context = HookContext(
            event=event,
            payload=payload or {},
            session_id=session_id,
            user_id=user_id,
            user_role=user_role,
            extra=extra,
        )

        matched_rules = [
            rule.name for rule in self.registry.list_hooks(event)
            if rule.enabled and rule.matches(context.to_dict())
        ]

        # 快速检查是否有 BLOCK 规则
        blocked, message = self._rule_engine.check_blocked(event, context.to_dict())
        if blocked:
            context.set_blocked(message)

        return HookResult.from_context(context, matched_rules)

    def register_rule(self, rule: HookRule) -> None:
        """注册规则"""
        self._registry.register(rule)

    def unregister_rule(self, name: str) -> bool:
        """注销规则"""
        return self._registry.unregister(name)

    def load_yaml_config(self, config_path: str) -> int:
        """
        从 YAML 文件加载规则配置

        Args:
            config_path: YAML 配置文件路径

        Returns:
            加载的规则数量
        """
        import yaml
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load YAML config from {config_path}: {e}")
            return 0

        count = 0
        rules = config if isinstance(config, list) else [config]
        for rule_data in rules:
            try:
                rule = self._registry.from_dict(rule_data)
                self._registry.register(rule)
                count += 1
            except Exception as e:
                logger.error(f"Failed to parse rule {rule_data.get('name', '?')}: {e}")

        logger.info(f"Loaded {count} hook rules from {config_path}")
        return count


# 全局单例
_engine: Optional[HookEngine] = None


def get_hook_engine() -> HookEngine:
    global _engine
    if _engine is None:
        _engine = HookEngine()
    return _engine


async def emit_hook(
    event: HookEvent,
    payload: Optional[dict] = None,
    **kwargs,
) -> HookResult:
    """便捷函数：触发 Hook 事件"""
    return await get_hook_engine().emit(event, payload, **kwargs)
