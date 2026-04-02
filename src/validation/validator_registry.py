"""
ValidatorRegistry - 对抗性验证注册中心 (V3.0 Phase 3)

核心设计：
1. Validator: 验证器接口（validate方法返回ValidationResult）
2. BreakingValidator: 主动构造边界条件来"打破"假设，而非"确认"假设
3. ValidatorRegistry: 验证器注册、调度、聚合结果

与普通测试的区别：
- 普通测试：验证系统"能做什么"（happy path）
- BreakingValidator：验证系统"不能做什么"（adversarial path）
  → 主动构造：空值、超长输入、特殊字符、并发冲突等

设计原则：
- break()方法命名强调"打破"而非"验证"
- BreakingValidator主动构造边界条件，不只是检查
- 验证结果含broken标志和reason，用于决策
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ValidationResult - 验证结果
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """
    验证结果

    Attributes:
        broken: 是否打破了假设（True = 发现问题）
        validator_name: 哪个验证器发现的问题
        reason: 问题描述
        suggestion: 修复建议（可选）
        evidence: 证据/测试用例（可选）
        severity: 严重程度 (info/warning/critical)
    """
    broken: bool = False
    validator_name: str = ""
    reason: str = ""
    suggestion: str = ""
    evidence: str = ""
    severity: str = "warning"  # info | warning | critical

    def __bool__(self) -> bool:
        """返回True表示"打破假设"（发现问题）"""
        return self.broken


# ─────────────────────────────────────────────────────────────────────────────
# Validator 基类
# ─────────────────────────────────────────────────────────────────────────────

class Validator(ABC):
    """
    验证器抽象基类

    所有验证器继承此类。
    与BreakingValidator的区别：
    - Validator: 检查已知条件是否满足
    - BreakingValidator: 主动构造边界条件来打破假设

    Attributes:
        name: 验证器名称
        enabled: 是否启用
    """

    name: str = ""
    enabled: bool = True

    @abstractmethod
    def validate(self, context: dict) -> ValidationResult:
        """
        执行验证

        Args:
            context: AgentHookContext.to_dict() 或类似的字典

        Returns:
            ValidationResult: broken=True表示打破了假设（发现问题）
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# BreakingValidator - 主动打破假设的验证器
# ─────────────────────────────────────────────────────────────────────────────

class BreakingValidator(ABC):
    """
    主动打破假设的验证器基类

    与Validator的区别：
    - Validator: 被动检查（输入→检查→结果）
    - BreakingValidator: 主动构造边界条件来测试系统韧性

    设计原则：
    1. break()方法命名强调"打破"意图
    2. 主动构造：空值、超长、特殊字符、并发等边界条件
    3. 返回的ValidationResult.broken=True表示"成功打破了假设"

    使用场景：
    - SQLBreakingValidator: 构造各种恶意SQL，看是否被正确拦截
    - ConcurrencyBreaker: 构造并发冲突，看是否有数据损坏
    - OverflowBreaker: 构造超大输入，看是否触发OOM

    Example:
        class SQLBreakingValidator(BreakingValidator):
            def break(self, context: dict) -> ValidationResult:
                # 构造边界SQL
                dangerous_sqls = [
                    "'; DROP TABLE users; --",  # 注入
                    "SELECT * FROM users WHERE id=999999999999",  # 超出范围
                    "SELECT * FROM users WHERE name='{}'".format("A" * 10000),  # 超长
                ]
                for sql in dangerous_sqls:
                    result = self._try_execute(sql)
                    if not result.blocked:
                        return ValidationResult(
                            broken=True,
                            validator_name=self.name,
                            reason=f"Dangerous SQL not blocked: {sql[:50]}",
                            evidence=sql,
                            severity="critical",
                        )
                return ValidationResult(broken=False)
    """

    name: str = ""
    enabled: bool = True

    @abstractmethod
    def break_assumption(self, context: dict) -> ValidationResult:
        """
        主动构造边界条件来打破假设

        Args:
            context: 执行上下文（含goal/llm_response/tool_results等）

        Returns:
            ValidationResult: broken=True表示"成功打破了假设"
        """
        pass

    # 兼容性别名
    def validate(self, context: dict) -> ValidationResult:
        return self.break_assumption(context)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# ValidatorRegistry - 验证器注册与管理中心
# ─────────────────────────────────────────────────────────────────────────────

class ValidatorRegistry:
    """
    验证器注册与管理中心

    核心功能：
    1. 注册/注销验证器
    2. 批量执行验证
    3. 聚合验证结果
    4. 支持优先级

    使用示例：
        registry = ValidatorRegistry()
        registry.register("completion_claim", CompletionClaimValidator(), priority=10)
        registry.register("sql_boundary", SQLBreakingValidator(), priority=20)

        results = registry.validate_all(context)
        critical_breaks = [r for r in results if r.severity == "critical" and r.broken]

        if critical_breaks:
            ctx.set_blocked(f"Critical break: {critical_breaks[0].reason}")

    与Hook系统的关系：
    - ValidatorRegistry在AgentRunner.after_iteration中调用
    - 每个Validator/BreakingValidator检查一个维度
    - 结果聚合后决定是否继续迭代
    """

    def __init__(self):
        # name -> (validator, priority)
        self._validators: dict[str, tuple[Validator | BreakingValidator, int]] = {}
        # event -> list[validator_name]（按优先级排序）
        self._by_event: dict[str, list[str]] = {}

    def register(
        self,
        name: str,
        validator: Validator | BreakingValidator,
        priority: int = 100,
        event: str = "default",
    ) -> None:
        """
        注册验证器

        Args:
            name: 验证器名称（唯一标识）
            validator: Validator或BreakingValidator实例
            priority: 优先级（数字越小越高）
            event: 事件类型（用于分类，default表示所有事件）
        """
        if not validator.enabled:
            return
        self._validators[name] = (validator, priority)
        if event not in self._by_event:
            self._by_event[event] = []
        if name not in self._by_event[event]:
            self._by_event[event].append(name)
        # 按优先级排序
        self._by_event[event].sort(
            key=lambda n: self._validators[n][1]
        )
        logger.debug(f"Registered validator: {name} (priority={priority}, event={event})")

    def unregister(self, name: str) -> bool:
        """注销验证器"""
        if name not in self._validators:
            return False
        del self._validators[name]
        for event_names in self._by_event.values():
            if name in event_names:
                event_names.remove(name)
        logger.debug(f"Unregistered validator: {name}")
        return True

    def get(self, name: str) -> Optional[Validator | BreakingValidator]:
        """按名称获取验证器"""
        entry = self._validators.get(name)
        return entry[0] if entry else None

    def list_validators(self) -> list[str]:
        """列出所有验证器名称"""
        return list(self._validators.keys())

    def validate(self, context: dict, name: str) -> ValidationResult:
        """
        执行单个验证器

        Args:
            context: 执行上下文
            name: 验证器名称

        Returns:
            ValidationResult
        """
        entry = self._validators.get(name)
        if not entry:
            return ValidationResult(broken=False, validator_name=name, reason="Validator not found")
        validator, _ = entry
        try:
            return validator.validate(context)
        except Exception as e:
            logger.warning(f"Validator {name} failed: {e}")
            return ValidationResult(
                broken=False,
                validator_name=name,
                reason=f"Validator error: {e}",
                severity="info",
            )

    def validate_all(self, context: dict, event: str = "default") -> list[ValidationResult]:
        """
        执行所有验证器

        Args:
            context: 执行上下文
            event: 事件类型（default表示所有）

        Returns:
            ValidationResult列表（按优先级排序）
        """
        results = []
        names = self._by_event.get(event, []) + self._by_event.get("default", [])
        seen = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            result = self.validate(context, name)
            results.append(result)
        return results

    def validate_any(
        self,
        context: dict,
        event: str = "default",
        severity: str = "critical",
    ) -> Optional[ValidationResult]:
        """
        执行验证，返回第一个指定严重程度的break

        用于快速决策（如遇到critical就立即停止）

        Args:
            context: 执行上下文
            event: 事件类型
            severity: 最小严重程度 (info/warning/critical)

        Returns:
            第一个匹配严重程度的ValidationResult，或None
        """
        severity_order = {"info": 0, "warning": 1, "critical": 2}
        min_level = severity_order.get(severity, 2)
        for result in self.validate_all(context, event):
            if result.broken and severity_order.get(result.severity, 0) >= min_level:
                return result
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────────────────────────

_registry: Optional[ValidatorRegistry] = None


def get_validator_registry() -> ValidatorRegistry:
    global _registry
    if _registry is None:
        _registry = ValidatorRegistry()
    return _registry


def reset_validator_registry() -> None:
    """重置全局验证器注册表（测试用）"""
    global _registry
    _registry = None
