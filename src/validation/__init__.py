"""src/validation - ValidatorRegistry (V3.0 Phase 3)

提供"打破假设"的对抗性验证能力。
与普通单元测试不同，Validator的目标是"打破"而非"确认"。

核心概念：
- Validator: 验证器基类
- BreakingValidator: 主动构造边界条件来打破假设
- ValidatorRegistry: 验证器注册与管理中心
- ValidationResult: 验证结果数据结构
- ValidationMode: 验证模式（CONFIRM/BREAK/BOTH）
- AdversarialValidationHook: 对抗性验证Hook

使用示例：
    from src.validation import (
        ValidatorRegistry,
        ValidationMode,
        get_validator_registry,
        AdversarialValidationHook,
    )

    # 方式1：使用全局单例
    registry = get_validator_registry()
    registry.register("completion_claim", CompletionBreakingValidator())

    # 方式2：创建Hook
    hook = create_adversarial_hook()

    # 在AgentRunner.after_iteration中：
    result = await registry.validate(context)
    if result.has_broken_claims():
        raise AdversarialChallengeError(result.get_broken_claims())
"""

from .validator_registry import (
    ValidatorRegistry,
    Validator,
    BreakingValidator,
    ValidationResult,
    ValidationMode,
    BreakResult,
    ValidatorResult,
    MultiValidationResult,
    get_validator_registry,
    reset_validator_registry,
)
from .validators import (
    CompletionBreakingValidator,
    SQLBoundaryValidator,
    TokenOverBudgetValidator,
    CodeQualityValidator,
)
from .adversarial_hook import (
    AdversarialValidationHook,
    AdversarialChallengeError,
    create_adversarial_hook,
)

__all__ = [
    # 核心注册表
    "ValidatorRegistry",
    "Validator",
    "BreakingValidator",
    "ValidationResult",
    "ValidationMode",
    "BreakResult",
    "ValidatorResult",
    "MultiValidationResult",
    "get_validator_registry",
    "reset_validator_registry",
    # 预置验证器
    "CompletionBreakingValidator",
    "SQLBoundaryValidator",
    "TokenOverBudgetValidator",
    "CodeQualityValidator",
    # Hook
    "AdversarialValidationHook",
    "AdversarialChallengeError",
    "create_adversarial_hook",
]
