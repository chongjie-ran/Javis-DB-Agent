"""
tests/unit/test_validation.py - V3.0 Phase 3 对抗性验证系统测试

测试内容：
1. ValidationMode - 验证模式切换
2. ValidationResult/BreakResult/ValidatorResult/MultiValidationResult - 结果数据结构
3. ValidatorRegistry - 验证器注册、调度、聚合
4. BreakingValidator.break_claim() - 打破声明逻辑
5. CompletionBreakingValidator - 完成声明打破器
6. SQLBoundaryValidator - SQL边界条件测试
7. TokenOverBudgetValidator - Token预算检查
8. CodeQualityValidator - 代码质量验证器
9. AdversarialValidationHook - 对抗性验证Hook
"""

import pytest
import asyncio
from typing import Optional

# Ensure src is in path
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..', 'src'))

from src.validation import (
    ValidatorRegistry,
    Validator,
    BreakingValidator,
    ValidationResult,
    ValidationMode,
    BreakResult,
    ValidatorResult,
    MultiValidationResult,
    CompletionBreakingValidator,
    SQLBoundaryValidator,
    TokenOverBudgetValidator,
    CodeQualityValidator,
    AdversarialValidationHook,
    AdversarialChallengeError,
    create_adversarial_hook,
    get_validator_registry,
    reset_validator_registry,
)
from src.hooks.hook_context import AgentHookContext
from src.hooks.hook_events import AgentHookEvent


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def clean_registry():
    """每个测试前重置全局注册表"""
    reset_validator_registry()
    yield
    reset_validator_registry()


def _make_context(
    goal: str = "分析数据库性能问题并提供优化建议",
    llm_response: str = "任务完成，已分析完成",
    token_count: int = 5000,
    token_budget: int = 100000,
    iteration: int = 1,
    max_iterations: int = 10,
    tool_results: Optional[list] = None,
    tools_to_execute: Optional[list] = None,
) -> AgentHookContext:
    """创建真实的AgentHookContext"""
    return AgentHookContext(
        event=AgentHookEvent.after_iteration,
        goal=goal,
        session_id="test-session-001",
        user_id="test-user",
        token_count=token_count,
        token_budget=token_budget,
        iteration=iteration,
        max_iterations=max_iterations,
        llm_response=llm_response,
        tool_results=tool_results or [],
        tools_to_execute=tools_to_execute or [],
    )


@pytest.fixture
def mock_context() -> AgentHookContext:
    """创建一个模拟的AgentHookContext"""
    return _make_context()


@pytest.fixture
def completion_claim_context() -> AgentHookContext:
    """创建一个包含完成声明的上下文"""
    return _make_context(
        goal="1. 修复bug  2. 添加测试  3. 提交代码",
        llm_response="任务完成了。第一步修复完成，第二步还在进行中。已解决。",
        token_count=3000,
    )


@pytest.fixture
def sql_context() -> AgentHookContext:
    """创建一个SQL相关的上下文"""
    return _make_context(
        goal="执行SQL查询：SELECT * FROM users WHERE id=1",
        llm_response="SELECT * FROM users WHERE id=1 OR 1=1",
        token_count=2000,
        tools_to_execute=[{"name": "execute_sql", "params": {"sql": "SELECT 1"}}],
    )


@pytest.fixture
def token_over_budget_context() -> AgentHookContext:
    """创建一个Token超预算的上下文"""
    return _make_context(
        goal="复杂的多步分析任务",
        llm_response="继续分析中...",
        token_count=98000,  # 98% of 100000
        token_budget=100000,
        iteration=8,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test ValidationMode
# ─────────────────────────────────────────────────────────────────────────────

class TestValidationMode:
    def test_validation_mode_values(self):
        assert ValidationMode.CONFIRM.value == "confirm"
        assert ValidationMode.BREAK.value == "break"
        assert ValidationMode.BOTH.value == "both"

    def test_validation_mode_is_enum(self):
        assert isinstance(ValidationMode.CONFIRM, ValidationMode)


# ─────────────────────────────────────────────────────────────────────────────
# Test ValidationResult
# ─────────────────────────────────────────────────────────────────────────────

class TestValidationResult:
    def test_validation_result_defaults(self):
        result = ValidationResult()
        assert result.broken is False
        assert result.validator_name == ""
        assert result.severity == "warning"

    def test_validation_result_bool(self):
        assert bool(ValidationResult(broken=True)) is True
        assert bool(ValidationResult(broken=False)) is False

    def test_validation_result_fields(self):
        result = ValidationResult(
            broken=True,
            validator_name="test_validator",
            reason="Test failed",
            suggestion="Fix the test",
            evidence="test evidence",
            severity="critical",
        )
        assert result.broken is True
        assert result.validator_name == "test_validator"
        assert result.reason == "Test failed"
        assert result.suggestion == "Fix the test"
        assert result.evidence == "test evidence"
        assert result.severity == "critical"


# ─────────────────────────────────────────────────────────────────────────────
# Test BreakResult
# ─────────────────────────────────────────────────────────────────────────────

class TestBreakResult:
    def test_break_result_fields(self):
        result = BreakResult(
            claim="任务完成了",
            breaker="completion_claim: CompletionBreakingValidator",
            evidence="token_count=5000",
        )
        assert result.claim == "任务完成了"
        assert result.breaker == "completion_claim: CompletionBreakingValidator"
        assert result.evidence == "token_count=5000"


# ─────────────────────────────────────────────────────────────────────────────
# Test ValidatorResult
# ─────────────────────────────────────────────────────────────────────────────

class TestValidatorResult:
    def test_validator_result_no_broken(self):
        confirm = ValidationResult(broken=False, validator_name="test")
        result = ValidatorResult(name="test", confirm=confirm)
        assert result.has_broken() is False

    def test_validator_result_with_broken(self):
        confirm = ValidationResult(broken=True, validator_name="test")
        broken = BreakResult(claim="任务完成了", breaker="test: TestValidator")
        result = ValidatorResult(name="test", confirm=confirm, broken=broken)
        assert result.has_broken() is True


# ─────────────────────────────────────────────────────────────────────────────
# Test MultiValidationResult
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiValidationResult:
    def test_no_broken_claims(self):
        results = [
            ValidatorResult(
                name="v1",
                confirm=ValidationResult(broken=False),
            ),
            ValidatorResult(
                name="v2",
                confirm=ValidationResult(broken=False),
            ),
        ]
        multi = MultiValidationResult(results=results)
        assert multi.has_broken_claims() is False
        assert multi.get_broken_claims() == []

    def test_with_broken_claims(self):
        results = [
            ValidatorResult(
                name="v1",
                confirm=ValidationResult(broken=False),
            ),
            ValidatorResult(
                name="v2",
                confirm=ValidationResult(broken=True, severity="critical"),
                broken=BreakResult(claim="测试通过", breaker="v2: TestValidator"),
            ),
        ]
        multi = MultiValidationResult(results=results)
        assert multi.has_broken_claims() is True
        assert len(multi.get_broken_claims()) == 1

    def test_get_critical_breaks(self):
        results = [
            ValidatorResult(
                name="v1",
                confirm=ValidationResult(broken=True, severity="info"),
            ),
            ValidatorResult(
                name="v2",
                confirm=ValidationResult(broken=True, severity="critical"),
                broken=BreakResult(claim="Critical claim", breaker="v2: TestValidator"),
            ),
        ]
        multi = MultiValidationResult(results=results)
        critical = multi.get_critical_breaks()
        assert len(critical) == 1
        assert critical[0].claim == "Critical claim"

    def test_summary_all_pass(self):
        results = [
            ValidatorResult(name="v1", confirm=ValidationResult(broken=False)),
            ValidatorResult(name="v2", confirm=ValidationResult(broken=False)),
        ]
        multi = MultiValidationResult(results=results)
        assert "✅" in multi.summary()

    def test_summary_with_breaks(self):
        results = [
            ValidatorResult(
                name="v1",
                confirm=ValidationResult(broken=True),
                broken=BreakResult(claim="claim1", breaker="v1: Test"),
            ),
        ]
        multi = MultiValidationResult(results=results)
        assert "⚠️" in multi.summary()


# ─────────────────────────────────────────────────────────────────────────────
# Test BreakingValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestBreakingValidator:
    def test_classify_claim_completion(self):
        """测试声明类型分类 - 完成类"""
        validator = CompletionBreakingValidator()

        assert validator.classify_claim("任务完成了") == BreakingValidator.CLAIM_TYPE_COMPLETION
        assert validator.classify_claim("已经完成了分析") == BreakingValidator.CLAIM_TYPE_COMPLETION
        assert validator.classify_claim("搞定") == BreakingValidator.CLAIM_TYPE_COMPLETION

    def test_classify_claim_fix(self):
        """测试声明类型分类 - 修复类"""
        validator = CompletionBreakingValidator()

        assert validator.classify_claim("修复了这个bug") == BreakingValidator.CLAIM_TYPE_FIX
        assert validator.classify_claim("解决了问题") == BreakingValidator.CLAIM_TYPE_FIX
        assert validator.classify_claim("bug已修复") == BreakingValidator.CLAIM_TYPE_FIX

    def test_classify_claim_test_pass(self):
        """测试声明类型分类 - 测试通过类"""
        validator = CompletionBreakingValidator()

        assert validator.classify_claim("测试通过了") == BreakingValidator.CLAIM_TYPE_TEST_PASS
        assert validator.classify_claim("验证成功") == BreakingValidator.CLAIM_TYPE_TEST_PASS
        assert validator.classify_claim("All tests passed") == BreakingValidator.CLAIM_TYPE_TEST_PASS

    def test_classify_claim_quality(self):
        """测试声明类型分类 - 质量类"""
        validator = CompletionBreakingValidator()

        assert validator.classify_claim("无问题") == BreakingValidator.CLAIM_TYPE_QUALITY
        assert validator.classify_claim("代码正确") == BreakingValidator.CLAIM_TYPE_QUALITY
        assert validator.classify_claim("符合规范") == BreakingValidator.CLAIM_TYPE_QUALITY

    def test_classify_claim_unknown(self):
        """测试声明类型分类 - 未知类"""
        validator = CompletionBreakingValidator()

        assert validator.classify_claim("今天天气不错") == BreakingValidator.CLAIM_TYPE_UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# Test ValidatorRegistry
# ─────────────────────────────────────────────────────────────────────────────

class TestValidatorRegistry:
    def test_register_and_get(self, clean_registry):
        registry = ValidatorRegistry()
        validator = CompletionBreakingValidator()
        registry.register("test_validator", validator, priority=10)

        assert registry.get("test_validator") is validator
        assert "test_validator" in registry.list_validators()

    def test_register_with_priority(self, clean_registry):
        registry = ValidatorRegistry()
        v1 = CompletionBreakingValidator()
        v2 = SQLBoundaryValidator()
        v1.name = "v1"
        v2.name = "v2"

        registry.register("v1", v1, priority=100)
        registry.register("v2", v2, priority=10)

        names = registry.list_validators()
        # v2有更高的优先级（数字更小），应该排在前面
        assert names == ["v2", "v1"]

    def test_unregister(self, clean_registry):
        registry = ValidatorRegistry()
        validator = CompletionBreakingValidator()
        registry.register("test_validator", validator)
        assert registry.unregister("test_validator") is True
        assert registry.get("test_validator") is None
        assert registry.unregister("nonexistent") is False

    def test_set_mode(self, clean_registry):
        registry = ValidatorRegistry()
        registry.set_mode(ValidationMode.CONFIRM)
        assert registry.get_mode() == ValidationMode.CONFIRM

        registry.set_mode(ValidationMode.BREAK)
        assert registry.get_mode() == ValidationMode.BREAK

    def test_extract_claims(self, completion_claim_context):
        registry = ValidatorRegistry()
        claims = registry.extract_claims(completion_claim_context)
        assert len(claims) > 0
        # 应该包含"完成"或"解决"等声明
        claims_text = " ".join(claims)
        assert "完成" in claims_text or "解决" in claims_text

    @pytest.mark.asyncio
    async def test_validate_confirm_mode(self, clean_registry, mock_context):
        """测试确认模式验证"""
        registry = ValidatorRegistry()
        registry.set_mode(ValidationMode.CONFIRM)
        validator = TokenOverBudgetValidator()
        registry.register("token", validator)

        result = await registry.validate(mock_context)

        assert isinstance(result, MultiValidationResult)
        # 确认模式下也应该执行确认验证
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_validate_break_mode(self, clean_registry, completion_claim_context):
        """测试对抗模式验证"""
        registry = ValidatorRegistry()
        registry.set_mode(ValidationMode.BREAK)
        validator = CompletionBreakingValidator()
        registry.register("completion", validator)

        result = await registry.validate(completion_claim_context)

        assert isinstance(result, MultiValidationResult)
        # 对抗模式下应该有声明被检测

    def test_global_singleton(self, clean_registry):
        r1 = get_validator_registry()
        r2 = get_validator_registry()
        assert r1 is r2


# ─────────────────────────────────────────────────────────────────────────────
# Test CompletionBreakingValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestCompletionBreakingValidator:
    @pytest.mark.asyncio
    async def test_validate_normal(self, mock_context):
        validator = CompletionBreakingValidator()
        result = await validator.validate(mock_context)
        # 正常上下文应该不broken
        assert isinstance(result, ValidationResult)

    @pytest.mark.asyncio
    async def test_validate_with_empty_response(self, mock_context):
        """空LLM响应场景 - 应该不是broken（因为有tool_results可用）"""
        ctx = _make_context(llm_response="", tool_results=[{"name": "execute_sql", "result": {"rows": [], "count": 0}}])
        validator = CompletionBreakingValidator()
        result = await validator.validate(ctx)
        # 有工具结果，空响应不算问题
        assert result.broken is False

    def test_break_claim_completion(self, completion_claim_context):
        """测试打破完成声明"""
        validator = CompletionBreakingValidator()
        claims = validator.extract_claims(completion_claim_context)
        assert len(claims) > 0

    def test_break_claim_unknown(self, mock_context):
        """测试未知类型声明不会被打破"""
        validator = CompletionBreakingValidator()
        broken = validator.break_claim("今天天气不错", mock_context)
        assert broken is False


# ─────────────────────────────────────────────────────────────────────────────
# Test SQLBoundaryValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestSQLBoundaryValidator:
    @pytest.mark.asyncio
    async def test_validate_non_sql_context(self, mock_context):
        ctx = _make_context(goal="帮我写一首诗", tools_to_execute=[])
        validator = SQLBoundaryValidator()
        result = await validator.validate(ctx)
        assert result.broken is False

    @pytest.mark.asyncio
    async def test_validate_with_dangerous_sql(self, sql_context):
        validator = SQLBoundaryValidator()
        result = await validator.validate(sql_context)
        # 包含OR 1=1的SQL应该被检测
        assert result.broken is True

    def test_extract_sql_claims(self):
        validator = SQLBoundaryValidator()
        # 测试UNION查询，可以提取为完整SQL
        text = "SELECT * FROM users WHERE id=1 UNION SELECT name FROM admin"
        claims = validator._extract_sql_claims(text)
        # 匹配整条SQL作为一个claim
        assert len(claims) >= 1

    def test_test_sql_boundaries(self):
        validator = SQLBoundaryValidator()
        # DROP TABLE应该被检测
        result = validator._test_sql_boundaries("DROP TABLE users")
        assert result.broken is True
        assert result.severity == "critical"

        # OR 1=1应该被检测
        result = validator._test_sql_boundaries("SELECT * FROM users WHERE id=1 OR 1=1")
        assert result.broken is True

        # 正常SQL应该通过
        result = validator._test_sql_boundaries("SELECT * FROM users WHERE id=1")
        assert result.broken is False


# ─────────────────────────────────────────────────────────────────────────────
# Test TokenOverBudgetValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenOverBudgetValidator:
    @pytest.mark.asyncio
    async def test_validate_normal(self, mock_context):
        validator = TokenOverBudgetValidator()
        result = await validator.validate(mock_context)
        assert result.broken is False

    @pytest.mark.asyncio
    async def test_validate_warning_threshold(self, token_over_budget_context):
        ctx = _make_context(
            goal="复杂的多步分析任务",
            llm_response="继续分析中...",
            token_count=85000,  # 85%
            token_budget=100000,
            iteration=8,
        )
        validator = TokenOverBudgetValidator()
        result = await validator.validate(ctx)
        assert result.broken is True
        assert result.severity == "warning"

    @pytest.mark.asyncio
    async def test_validate_critical_threshold(self, token_over_budget_context):
        validator = TokenOverBudgetValidator()
        result = await validator.validate(token_over_budget_context)
        assert result.broken is True
        assert result.severity == "critical"


# ─────────────────────────────────────────────────────────────────────────────
# Test CodeQualityValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestCodeQualityValidator:
    @pytest.mark.asyncio
    async def test_validate_no_code_change(self, mock_context):
        ctx = _make_context(llm_response="我来分析一下这个问题", tool_results=[])
        validator = CodeQualityValidator()
        result = await validator.validate(ctx)
        assert result.broken is False

    def test_break_claim_with_code_but_no_error_handling(self, mock_context):
        """测试有代码但没有错误处理的情况"""
        ctx = _make_context(llm_response="def process():\n    file = open('data.txt')\n    return file.read()")
        validator = CodeQualityValidator()
        # 质量声明 + 打开文件但没有close
        broken = validator.break_claim("代码正确，无问题", ctx)
        assert broken is True  # 应该打破：文件未关闭

    def test_break_claim_without_quality_claim(self, mock_context):
        """没有质量声明时不应该打破"""
        ctx = _make_context(llm_response="def process(): pass")
        validator = CodeQualityValidator()
        broken = validator.break_claim("今天天气不错", ctx)
        assert broken is False


# ─────────────────────────────────────────────────────────────────────────────
# Test AdversarialValidationHook
# ─────────────────────────────────────────────────────────────────────────────

class TestAdversarialValidationHook:
    @pytest.mark.asyncio
    async def test_after_iteration_no_break(self, mock_context):
        registry = ValidatorRegistry()
        registry.set_mode(ValidationMode.BREAK)
        registry.register("token", TokenOverBudgetValidator())

        hook = AdversarialValidationHook(registry=registry)
        ctx = await hook.after_iteration(mock_context)

        assert ctx.blocked is False

    @pytest.mark.asyncio
    async def test_after_iteration_with_critical_break(self, token_over_budget_context):
        """Token超预算应该触发blocked"""
        registry = ValidatorRegistry()
        registry.set_mode(ValidationMode.BREAK)
        registry.register("token", TokenOverBudgetValidator())

        hook = AdversarialValidationHook(registry=registry, raise_on_critical=True)
        ctx = await hook.after_iteration(token_over_budget_context)

        # 98% token应该触发critical break并blocked
        assert ctx.blocked is True
        assert "Critical break" in ctx.block_reason

    def test_create_adversarial_hook(self):
        """测试工厂函数"""
        hook = create_adversarial_hook(mode=ValidationMode.BREAK)
        assert isinstance(hook, AdversarialValidationHook)
        assert hook.mode == ValidationMode.BREAK


# ─────────────────────────────────────────────────────────────────────────────
# Test Integration - 全流程
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_validation_flow(self, clean_registry, completion_claim_context):
        """测试完整的验证流程"""
        registry = get_validator_registry()
        registry.set_mode(ValidationMode.BOTH)
        registry.register("completion", CompletionBreakingValidator(), priority=10)
        registry.register("token", TokenOverBudgetValidator(), priority=5)

        result = await registry.validate(completion_claim_context)

        assert isinstance(result, MultiValidationResult)
        assert len(result.results) == 2
        # token验证器应该在前面（优先级更高）
        assert result.results[0].name == "token"
        assert result.results[1].name == "completion"

    @pytest.mark.asyncio
    async def test_mode_switching(self, clean_registry, mock_context):
        """测试模式切换"""
        registry = ValidatorRegistry()
        v = TokenOverBudgetValidator()
        registry.register("token", v)

        # CONFIRM模式
        registry.set_mode(ValidationMode.CONFIRM)
        r1 = await registry.validate(mock_context)
        assert len(r1.results) == 1

        # BREAK模式
        registry.set_mode(ValidationMode.BREAK)
        r2 = await registry.validate(mock_context)
        assert len(r2.results) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
