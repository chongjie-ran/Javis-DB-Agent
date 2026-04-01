"""gateway.hooks - 事件驱动 Hook 系统"""
from .hook_event import HookEvent
from .hook_context import HookContext
from .hook_rule import HookRule, HookAction, ConditionOperator, HookCondition
from .hook_registry import HookRegistry, get_hook_registry
from .rule_engine import RuleEngine
from .hook_engine import HookEngine, HookResult, get_hook_engine, emit_hook

__all__ = [
    "HookEvent",
    "HookContext",
    "HookRule",
    "HookAction",
    "ConditionOperator",
    "HookCondition",
    "HookRegistry",
    "get_hook_registry",
    "RuleEngine",
    "HookEngine",
    "HookResult",
    "get_hook_engine",
    "emit_hook",
]
