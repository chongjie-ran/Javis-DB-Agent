"""
AdversarialValidationHook - 对抗性验证Hook (V3.0 Phase 3)

集成到AgentRunner的after_iteration中，实现"打破而非确认"的对抗性验证循环。

工作流程：
1. after_iteration被调用
2. 提取context中的声明
3. 用BreakingValidator尝试打破每个声明
4. 如果有声明被打破，发出警告/阻止

使用示例：
    from src.validation import get_validator_registry, AdversarialValidationHook

    registry = get_validator_registry()
    registry.register("completion_claim", CompletionBreakingValidator())

    # 注册到AgentRunner
    hook = AdversarialValidationHook(registry)
    runner.add_hook(hook)

    # after_iteration中：
    # hook.after_iteration(ctx)
    # if ctx.blocked:
    #     raise AdversarialChallengeError(ctx.block_reason)
"""

from typing import Optional
import logging

from ..hooks.hook import AgentHook
from ..hooks.hook_context import AgentHookContext

from .validator_registry import (
    ValidatorRegistry,
    MultiValidationResult,
    ValidationMode,
)

logger = logging.getLogger(__name__)


class AdversarialChallengeError(Exception):
    """
    对抗性挑战异常

    当ValidatorRegistry检测到声明被打破时抛出此异常。
    由AgentRunner捕获并决定是否停止迭代。
    """

    def __init__(self, broken_claims: list):
        self.broken_claims = broken_claims
        super().__init__(f"声明被打破: {[b.claim for b in broken_claims]}")


class AdversarialValidationHook(AgentHook):
    """
    对抗性验证Hook

    在after_iteration中执行，检测LLM输出中的声明，
    并尝试用BreakingValidator来"打破"这些声明。

    设计原则：
    - 目标是"打破"而非"确认"
    - 检测到声明后，尝试构造失败用例
    - 如果声明被打破，设置ctx.blocked=True

    与普通Hook的区别：
    - 主动质疑而非被动确认
    - 关注"系统不能做什么"而非"能做什么"
    """

    name = "adversarial_validation"
    priority = 50  # 在其他after_iteration之后执行

    def __init__(
        self,
        registry: Optional[ValidatorRegistry] = None,
        mode: ValidationMode = ValidationMode.BREAK,
        raise_on_critical: bool = True,
    ):
        """
        Args:
            registry: ValidatorRegistry实例（传入None则使用全局单例）
            mode: 验证模式（默认BREAK）
            raise_on_critical: 是否在检测到critical break时抛出异常
        """
        self.registry = registry
        self.mode = mode
        self.raise_on_critical = raise_on_critical

    def _get_registry(self) -> ValidatorRegistry:
        if self.registry is not None:
            return self.registry
        from .validator_registry import get_validator_registry
        return get_validator_registry()

    async def after_iteration(self, ctx: AgentHookContext) -> AgentHookContext:
        """
        每次迭代结束后执行对抗性验证

        工作流程：
        1. 设置验证模式
        2. 执行所有验证器
        3. 检查是否有声明被打破
        4. 如果有critical break，抛出AdversarialChallengeError
        5. 如果有warning break，发出警告

        Args:
            ctx: AgentHookContext

        Returns:
            修改后的ctx（可能设置blocked=True）
        """
        registry = self._get_registry()
        registry.set_mode(self.mode)

        # 执行验证
        result = await registry.validate(ctx)

        # 记录结果
        if result.has_broken_claims():
            broken = result.get_broken_claims()
            logger.warning(
                f"[AdversarialValidation] 声明被打破 ({len(broken)}个): "
                f"{[b.claim[:50] for b in broken]}"
            )

            # 检查critical break
            critical = result.get_critical_breaks()
            if critical and self.raise_on_critical:
                ctx.set_blocked(
                    f"Critical break detected: {critical[0].breaker} "
                    f"- {critical[0].claim[:100]}"
                )
                # 注意：不抛出异常，让AgentRunner决定如何处理
                # 如果需要抛出，外部可以检查ctx.blocked并raise
            else:
                # Warning级别，只记录警告
                ctx.add_warning(
                    f"Breaking claims detected: {[b.claim[:50] for b in broken]}"
                )
        else:
            logger.debug(f"[AdversarialValidation] 验证通过: {result.summary()}")

        return ctx

    def after_llm(self, ctx: AgentHookContext) -> AgentHookContext:
        """
        LLM调用后验证响应

        在LLM返回后立即进行初步验证，快速发现明显问题。

        Args:
            ctx: AgentHookContext（含llm_response）

        Returns:
            修改后的ctx
        """
        # 这里只做轻量级检查，不调用完整的validate
        llm = ctx.llm_response

        if not llm:
            return ctx

        # 检查是否包含阻断词（低质量响应特征）
        low_quality_patterns = [
            r"^我不知道",
            r"^抱歉，我",
            r"作为AI",
            r"无法完成",
        ]

        for pattern in low_quality_patterns:
            if ctx.llm_response and re.match(pattern, ctx.llm_response.strip()):
                ctx.add_warning(f"Low-quality LLM response detected: matched {pattern}")

        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def create_adversarial_hook(
    validators: Optional[list] = None,
    mode: ValidationMode = ValidationMode.BREAK,
) -> AdversarialValidationHook:
    """
    创建对抗性验证Hook的工厂函数

    Args:
        validators: 验证器实例列表（不传则使用内置验证器）
        mode: 验证模式

    Returns:
        AdversarialValidationHook
    """
    from .validator_registry import get_validator_registry
    from .validators import CompletionBreakingValidator, SQLBoundaryValidator, TokenOverBudgetValidator

    registry = get_validator_registry()

    if validators is None:
        # 使用内置验证器
        registry.register("completion_claim", CompletionBreakingValidator(), priority=10)
        registry.register("sql_boundary", SQLBoundaryValidator(), priority=20)
        registry.register("token_over_budget", TokenOverBudgetValidator(), priority=5)

    return AdversarialValidationHook(registry=registry, mode=mode)


# 需要re模块
import re
