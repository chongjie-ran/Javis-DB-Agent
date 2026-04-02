"""src/validation - ValidatorRegistry (V3.0 Phase 3)

提供"打破假设"的对抗性验证能力。
与普通单元测试不同，Validator的目标是"打破"而非"确认"。

核心概念：
- Validator: 验证器基类
- BreakingValidator: 主动构造边界条件来打破假设
- ValidatorRegistry: 验证器注册与管理中心
- ValidationResult: 验证结果数据结构

使用示例：
    registry = ValidatorRegistry()

    # 注册对抗性验证器
    registry.register("completion_claim", CompletionClaimValidator())
    registry.register("sql_boundary", SQLBoundaryValidator())

    # 在AgentRunner的after_iteration中调用
    result = registry.validate(context)
    if result.broken:
        ctx.set_blocked(f"假设被打破: {result.reason}")
"""

from .validator_registry import (
    ValidatorRegistry,
    Validator,
    BreakingValidator,
    ValidationResult,
    get_validator_registry,
)
from .validators import (
    CompletionClaimValidator,
    SQLBoundaryValidator,
    TokenOverBudgetValidator,
)

__all__ = [
    "ValidatorRegistry",
    "Validator",
    "BreakingValidator",
    "ValidationResult",
    "get_validator_registry",
    "CompletionClaimValidator",
    "SQLBoundaryValidator",
    "TokenOverBudgetValidator",
]
