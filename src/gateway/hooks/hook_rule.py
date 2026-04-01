"""HookRule - Hook 规则结构"""
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, Optional
from enum import Enum
import re

from .hook_event import HookEvent


# 全局正则编译缓存（线程安全，LRU淘汰）
@lru_cache(maxsize=256)
def _compile_regex(pattern: str):
    """线程安全地缓存编译后的正则表达式"""
    return re.compile(pattern)


class HookAction(str, Enum):
    """Hook 动作类型"""
    BLOCK = "block"      # 阻止执行
    WARN = "warn"        # 警告但不阻止
    LOG = "log"          # 仅记录
    MODIFY = "modify"    # 修改 payload


class ModifyOperationType(str, Enum):
    """MODIFY 动作的操作类型"""
    REPLACE = "replace"   # 替换字段值
    REDACT = "redact"     # 脱敏（替换为占位符）
    ADD = "add"          # 添加字段
    REMOVE = "remove"    # 删除字段
    CLAMP = "clamp"      # 限制数值范围


class ConditionOperator(str, Enum):
    """条件操作符"""
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    REGEX_MATCH = "regex_match"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    HAS_KEY = "has_key"


@dataclass
class HookCondition:
    """Hook 条件"""
    field: str                    # 字段路径，如 "sql_statement" 或 "risk_level"
    operator: ConditionOperator   # 操作符
    value: Any = None            # 比较值

    def evaluate(self, context: dict) -> bool:
        """评估条件是否满足"""
        # 支持嵌套字段，如 "payload.sql_statement"
        parts = self.field.split(".")
        current: Any = context

        for i, part in enumerate(parts):
            if isinstance(current, dict):
                next_val = current.get(part)
                if next_val is None:
                    # 尝试从 payload 中查找（兼容 sql_statement -> payload.sql_statement）
                    if i == 0 and "payload" in context:
                        current = context["payload"].get(part)
                        if current is not None:
                            continue
                    return False
                current = next_val
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return False

        return self._compare(current)

    def _compare(self, actual: Any) -> bool:
        """执行比较"""
        op = self.operator

        if op == ConditionOperator.EQ:
            return actual == self.value
        elif op == ConditionOperator.NE:
            return actual != self.value
        elif op == ConditionOperator.GT:
            return actual > self.value
        elif op == ConditionOperator.GTE:
            return actual >= self.value
        elif op == ConditionOperator.LT:
            return actual < self.value
        elif op == ConditionOperator.LTE:
            return actual <= self.value
        elif op == ConditionOperator.IN:
            return actual in self.value if isinstance(self.value, (list, tuple, set)) else False
        elif op == ConditionOperator.NOT_IN:
            return actual not in self.value if isinstance(self.value, (list, tuple, set)) else True
        elif op == ConditionOperator.CONTAINS:
            return self.value in actual if hasattr(actual, "__contains__") else False
        elif op == ConditionOperator.REGEX_MATCH:
            compiled = _compile_regex(self.value)
            return compiled.search(str(actual)) is not None
        elif op == ConditionOperator.STARTS_WITH:
            return str(actual).startswith(self.value)
        elif op == ConditionOperator.ENDS_WITH:
            return str(actual).endswith(self.value)
        elif op == ConditionOperator.HAS_KEY:
            return self.value in (actual.keys() if isinstance(actual, dict) else [])

        return False


@dataclass
class ModifyOperation:
    """
    MODIFY 动作的单个操作定义

    支持 5 种操作类型：
    - REPLACE: 替换字段值
    - REDACT: 脱敏（替换为占位符）
    - ADD: 添加字段
    - REMOVE: 移除字段
    - CLAMP: 限制数值范围
    """
    operation: ModifyOperationType  # 操作类型
    field: str                     # 字段路径，如 "params.limit" 或 "payload.statement"
    value: Any = None             # REPLACE / ADD 的值
    redact_with: str = "****"     # REDACT 替换值
    min_val: int = None           # CLAMP 下限
    max_val: int = None           # CLAMP 上限
    default_val: Any = None       # CLAMP 默认值（字段不存在时）


@dataclass
class HookRule:
    """
    Hook 规则定义

    一个规则由以下部分组成：
    - name: 规则名称
    - enabled: 是否启用
    - event: 监听的事件类型
    - conditions: 触发条件列表（AND 关系）
    - action: 触发后的动作
    - handler: 可选的处理器函数
    - priority: 优先级（数字越小越高）
    - message: 拦截/警告消息
    """

    name: str
    event: HookEvent
    enabled: bool = True
    conditions: list[HookCondition] = field(default_factory=list)
    action: HookAction = HookAction.LOG
    handler: Optional[Callable] = None  # async def(context: HookContext) -> HookContext
    priority: int = 100  # 默认优先级
    message: str = ""
    modify_ops: list[ModifyOperation] = field(default_factory=list)  # MODIFY 动作的操作列表

    def matches(self, context_dict: dict) -> bool:
        """检查规则是否匹配当前上下文"""
        if not self.enabled:
            return False

        # 所有条件都满足才算匹配
        for condition in self.conditions:
            if not condition.evaluate(context_dict):
                return False

        return True

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "event": self.event.value,
            "enabled": self.enabled,
            "conditions": [
                {"field": c.field, "operator": c.operator.value, "value": c.value}
                for c in self.conditions
            ],
            "action": self.action.value,
            "priority": self.priority,
            "message": self.message,
            "modify_ops": [
                {
                    "operation": op.operation.value,
                    "field": op.field,
                    "value": op.value,
                    "redact_with": op.redact_with,
                    "min_val": op.min_val,
                    "max_val": op.max_val,
                    "default_val": op.default_val,
                }
                for op in self.modify_ops
            ],
        }
