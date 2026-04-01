"""HookRegistry - Hook 规则注册表"""
import logging
from typing import Optional
from collections import defaultdict

from .hook_event import HookEvent
from .hook_rule import HookRule, HookAction, HookCondition, ConditionOperator

logger = logging.getLogger(__name__)


class HookRegistry:
    """
    Hook 规则注册表

    管理所有 Hook 规则的注册、注销、查询。
    """

    def __init__(self):
        # event -> list[HookRule]
        self._hooks: dict[HookEvent, list[HookRule]] = defaultdict(list)
        # name -> HookRule (快速查找)
        self._by_name: dict[str, HookRule] = {}

    def register(self, rule: HookRule) -> None:
        """注册一个 Hook 规则"""
        self._hooks[rule.event].append(rule)
        self._by_name[rule.name] = rule
        # 按优先级排序
        self._hooks[rule.event].sort(key=lambda r: r.priority)
        logger.debug(f"Registered hook rule: {rule.name} for event {rule.event.value}")

    def unregister(self, name: str) -> bool:
        """注销指定名称的规则"""
        rule = self._by_name.get(name)
        if not rule:
            return False

        self._hooks[rule.event].remove(rule)
        del self._by_name[name]
        logger.debug(f"Unregistered hook rule: {name}")
        return True

    def get(self, name: str) -> Optional[HookRule]:
        """按名称获取规则"""
        return self._by_name.get(name)

    def list_hooks(self, event: HookEvent) -> list[HookRule]:
        """列出指定事件的所有规则"""
        return list(self._hooks.get(event, []))

    def list_all(self) -> list[HookRule]:
        """列出所有规则"""
        return list(self._by_name.values())

    def enable(self, name: str) -> bool:
        """启用规则"""
        rule = self._by_name.get(name)
        if rule:
            rule.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """禁用规则"""
        rule = self._by_name.get(name)
        if rule:
            rule.enabled = False
            return True
        return False

    def clear(self) -> None:
        """清空所有规则"""
        self._hooks.clear()
        self._by_name.clear()

    def from_dict(self, data: dict) -> HookRule:
        """
        从字典创建 HookRule（用于 YAML 配置加载）

        期望格式：
        {
            "name": "ddl-block-hook",
            "event": "sql:ddl_detected",
            "enabled": true,
            "action": "block",
            "priority": 10,
            "message": "DDL 操作被拦截",
            "conditions": [
                {"field": "sql_statement", "operator": "regex_match", "value": "(DROP|TRUNCATE)"},
            ]
        }
        """
        event = HookEvent(data.get("event", ""))
        conditions = []
        for c in data.get("conditions", []):
            conditions.append(HookCondition(
                field=c["field"],
                operator=ConditionOperator(c["operator"]),
                value=c["value"],
            ))

        return HookRule(
            name=data["name"],
            event=event,
            enabled=data.get("enabled", True),
            conditions=conditions,
            action=HookAction(data.get("action", "log")),
            priority=data.get("priority", 100),
            message=data.get("message", ""),
        )


# 全局注册表单例
_registry: Optional[HookRegistry] = None


def get_hook_registry() -> HookRegistry:
    global _registry
    if _registry is None:
        _registry = HookRegistry()
    return _registry
