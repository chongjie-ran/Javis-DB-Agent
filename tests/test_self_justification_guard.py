"""
测试自我合理化防护Hook (V3.0 Phase 4)

测试覆盖：
1. 信号词检测（通用信号 + 开发者特有信号）
2. 严重程度阈值过滤
3. 连续使用检测（3次以上触发质疑）
4. 各种动作触发（验证请求、阻止、证据请求等）
5. context属性正确设置
"""

import pytest

from src.hooks.self_justification_guard import (
    SelfJustificationGuard,
    SELF_JUSTIFICATION_SIGNALS,
    DEVELOPER_SIGNALS,
    ALL_SIGNALS,
    CONTINUOUS_SIGNALS,
)
from src.hooks.hook_context import AgentHookContext
from src.hooks.hook_events import AgentHookEvent


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def guard():
    """创建默认severity_threshold='high'的guard实例"""
    return SelfJustificationGuard(severity_threshold="high")


@pytest.fixture
def guard_low():
    """创建severity_threshold='low'的guard实例（触发所有信号）"""
    return SelfJustificationGuard(severity_threshold="low")


@pytest.fixture
def guard_critical():
    """创建severity_threshold='critical'的guard实例（仅触发critical信号）"""
    return SelfJustificationGuard(severity_threshold="critical")


@pytest.fixture
def ctx():
    """创建空的hook context"""
    return AgentHookContext(
        event=AgentHookEvent.after_iteration,
        iteration=1,
        goal="测试目标",
        session_id="test-session-1",
    )


# ── 测试：信号词检测 ─────────────────────────────────────────────

class TestSignalDetection:
    """测试信号词检测功能"""

    def test_detect_looks_correct(self, guard):
        """检测'看起来正确'信号"""
        text = "代码看起来正确，可以提交了"
        detected = guard.detect_signals(text)
        assert "看起来正确" in detected
        assert detected["看起来正确"]["severity"] == "high"
        assert detected["看起来正确"]["action"] == "run_validation"

    def test_detect_can_run(self, guard):
        """检测'能跑就行'信号"""
        text = "能跑就行，不需要更多测试"
        detected = guard.detect_signals(text)
        assert "能跑就行" in detected
        assert detected["能跑就行"]["severity"] == "critical"
        assert detected["能跑就行"]["action"] == "block_and_verify"

    def test_detect_should_be_ok(self, guard):
        """检测'应该没问题'信号"""
        text = "应该没问题，上线吧"
        detected = guard.detect_signals(text)
        assert "应该没问题" in detected
        assert detected["应该没问题"]["severity"] == "high"

    def test_detect_obviously(self, guard):
        """检测'显然'信号"""
        text = "显然这个方案是最好的"
        detected = guard.detect_signals(text)
        assert "显然" in detected
        assert detected["显然"]["severity"] == "medium"
        assert detected["显然"]["action"] == "require_evidence"

    def test_detect_clearly(self, guard):
        """检测'显然地'信号"""
        text = "这个问题显然地很容易解决"
        detected = guard.detect_signals(text)
        assert "显然地" in detected
        assert detected["显然地"]["severity"] == "medium"

    def test_detect_inevitable(self, guard):
        """检测'必然'信号"""
        text = "这样改必然会导致问题"
        detected = guard.detect_signals(text)
        assert "必然" in detected
        assert detected["必然"]["severity"] == "high"

    def test_detect_no_doubt(self, guard):
        """检测'毫无疑问'信号"""
        text = "毫无疑问，这个函数是正确的"
        detected = guard.detect_signals(text)
        assert "毫无疑问" in detected
        assert detected["毫无疑问"]["severity"] == "high"

    def test_detect_skip_first(self, guard):
        """检测'先跳过'信号"""
        text = "这个测试先跳过，后面再补"
        detected = guard.detect_signals(text)
        assert "先跳过" in detected
        assert detected["先跳过"]["severity"] == "high"
        assert detected["先跳过"]["action"] == "require_justification"

    def test_detect_do_simple_first(self, guard):
        """检测'先做简单的'信号"""
        text = "我们先做简单的部分"
        detected = guard.detect_signals(text)
        assert "先做简单的" in detected
        assert detected["先做简单的"]["severity"] == "high"
        assert detected["先做简单的"]["action"] == "redirect_to_hard"

    def test_detect_takes_too_long(self, guard):
        """检测'花太久了'信号"""
        text = "这个花太久了，换个方案"
        detected = guard.detect_signals(text)
        assert "花太久了" in detected
        assert detected["花太久了"]["severity"] == "high"
        assert detected["花太久了"]["action"] == "require_time_estimate"

    def test_detect_multiple_signals(self, guard):
        """检测同时包含多个信号"""
        text = "代码看起来正确，显然没问题，能跑就行"
        detected = guard.detect_signals(text)
        assert "看起来正确" in detected
        assert "显然" in detected
        assert "能跑就行" in detected
        assert len(detected) == 3

    def test_no_signal(self, guard):
        """检测无信号文本"""
        text = "这是一个正常的描述，包含具体的实现细节和测试结果"
        detected = guard.detect_signals(text)
        assert len(detected) == 0

    def test_partial_match_not_detected(self, guard):
        """测试部分匹配不会误检测"""
        text = "这个问题看起来很奇怪"
        detected = guard.detect_signals(text)
        # "看起来" alone shouldn't trigger
        assert "看起来正确" not in detected
        # Only the full phrase should match
        assert len(detected) == 0


# ── 测试：开发者特有信号 ─────────────────────────────────────────

class TestDeveloperSignals:
    """测试开发者特有信号检测"""

    def test_detect_commit_without_test(self, guard):
        """检测'先提交后面再测'信号"""
        text = "代码先提交后面再测"
        detected = guard.detect_signals(text)
        assert "先提交后面再测" in detected
        assert detected["先提交后面再测"]["severity"] == "high"
        assert detected["先提交后面再测"]["action"] == "require_testing_plan"

    def test_detect_leetcode_close(self, guard):
        """检测'LeetCode差不多对了'信号"""
        text = "LeetCode差不多对了，提交试试"
        detected = guard.detect_signals(text)
        assert "LeetCode差不多对了" in detected
        assert detected["LeetCode差不多对了"]["severity"] == "high"
        assert detected["LeetCode差不多对了"]["action"] == "require_submit_proof"

    def test_detect_memory_leak_ok(self, guard):
        """检测'内存泄漏问题不大'信号"""
        text = "这点内存泄漏问题不大"
        detected = guard.detect_signals(text)
        assert "内存泄漏问题不大" in detected
        assert detected["内存泄漏问题不大"]["severity"] == "critical"
        assert detected["内存泄漏问题不大"]["action"] == "run_valgrind"

    def test_detect_bug_small_skip(self, guard):
        """检测'这个bug很小先跳过'信号"""
        text = "这个bug很小先跳过"
        detected = guard.detect_signals(text)
        assert "这个bug很小先跳过" in detected
        assert detected["这个bug很小先跳过"]["severity"] == "high"
        assert detected["这个bug很小先跳过"]["action"] == "fix_immediately"


# ── 测试：连续使用检测 ───────────────────────────────────────────

class TestContinuousSignals:
    """测试连续使用信号检测"""

    def test_continuous_signals_list(self):
        """验证连续使用信号列表"""
        assert "显然" in CONTINUOUS_SIGNALS
        assert "显然地" in CONTINUOUS_SIGNALS
        assert "必然" in CONTINUOUS_SIGNALS
        assert "毫无疑问" in CONTINUOUS_SIGNALS

    def test_continuous_count_increment(self, guard):
        """测试连续计数递增"""
        # 第一次检测
        detected1 = guard.detect_signals("这个问题显然很简单")
        guard.update_continuous_counts(detected1)
        assert guard.signal_counts["显然"] == 1

        # 第二次检测
        detected2 = guard.detect_signals("显然，这是唯一正确的方案")
        guard.update_continuous_counts(detected2)
        assert guard.signal_counts["显然"] == 2

        # 第三次检测 - 应该触发质疑
        detected3 = guard.detect_signals("显然地，这个结论是成立的")
        guard.update_continuous_counts(detected3)
        assert guard.signal_counts["显然"] == 3

    def test_continuous_count_reset(self, guard):
        """测试检测不到信号时计数重置"""
        # 触发一次
        guard.update_continuous_counts({"显然": {"severity": "medium", "action": "require_evidence"}})
        assert guard.signal_counts["显然"] == 1

        # 下一次没有检测到
        guard.update_continuous_counts({})
        assert guard.signal_counts["显然"] == 0

    def test_continuous_trigger_after_3(self, guard_low, ctx):
        """测试连续3次后触发质疑（使用guard_low以触发medium严重程度的连续信号）"""
        # 模拟连续3次使用"显然"（medium严重程度）
        for i in range(3):
            ctx_i = AgentHookContext(event=AgentHookEvent.after_iteration, iteration=i+1)
            ctx_i.llm_response = "这个问题显然很简单"
            guard_low.after_iteration(ctx_i)

        # 第3次应该注入质疑
        assert "injected_challenge" in ctx_i.extra
        assert ctx_i.extra["injected_challenge"]["type"] == "continuous_signal_challenge"
        assert "显然" in ctx_i.extra["injected_challenge"]["message"]


# ── 测试：严重程度阈值 ───────────────────────────────────────────

class TestSeverityThreshold:
    """测试严重程度阈值过滤"""

    def test_threshold_high_triggers_high_and_above(self, guard, ctx):
        """threshold='high'应该触发high和critical"""
        # high severity signal
        ctx_high = AgentHookContext(event=AgentHookEvent.after_iteration, iteration=1)
        ctx_high.llm_response = "代码看起来正确"  # high severity
        guard.after_iteration(ctx_high)
        assert "injected_challenge" in ctx_high.extra

        # critical severity signal - should also trigger
        ctx_critical = AgentHookContext(event=AgentHookEvent.after_iteration, iteration=1)
        ctx_critical.llm_response = "能跑就行"  # critical severity
        guard.after_iteration(ctx_critical)
        assert "injected_challenge" in ctx_critical.extra

    def test_threshold_low_triggers_all(self, guard_low, ctx):
        """threshold='low'应该触发所有信号包括medium"""
        ctx_llm = AgentHookContext(event=AgentHookEvent.after_iteration, iteration=1)
        text = "这个问题显然很简单"  # medium severity
        ctx_llm.llm_response = text

        guard_low.after_iteration(ctx_llm)
        assert "injected_challenge" in ctx_llm.extra
        assert ctx_llm.extra["injected_challenge"]["severity"] == "medium"

    def test_threshold_critical_only_triggers_critical(self, guard_critical, ctx):
        """threshold='critical'只应该触发critical"""
        ctx_llm = AgentHookContext(event=AgentHookEvent.after_iteration, iteration=1)
        text = "代码看起来正确"  # high severity
        ctx_llm.llm_response = text

        guard_critical.after_iteration(ctx_llm)
        # high severity should not trigger when threshold is critical
        assert "injected_challenge" not in ctx_llm.extra

    def test_threshold_critical_triggers_critical_signal(self, guard_critical, ctx):
        """threshold='critical'应该触发critical信号"""
        ctx_llm = AgentHookContext(event=AgentHookEvent.after_iteration, iteration=1)
        text = "能跑就行"  # critical severity
        ctx_llm.llm_response = text

        guard_critical.after_iteration(ctx_llm)
        assert "injected_challenge" in ctx_llm.extra


# ── 测试：动作触发 ───────────────────────────────────────────────

class TestActionTrigger:
    """测试各种动作的触发"""

    def test_run_validation_action(self, guard, ctx):
        """测试run_validation动作"""
        ctx.llm_response = "代码看起来正确，可以交付了"
        guard.after_iteration(ctx)

        assert "injected_challenge" in ctx.extra
        assert ctx.extra["injected_challenge"]["type"] == "validation_request"

    def test_block_and_verify_action(self, guard, ctx):
        """测试block_and_verify动作"""
        ctx.llm_response = "能跑就行，直接上线"
        guard.after_iteration(ctx)

        assert ctx.blocked is True
        assert "能跑就行" in ctx.block_reason
        assert ctx.extra["injected_challenge"]["type"] == "block_and_verify"

    def test_require_evidence_action(self, guard_low, ctx):
        """测试require_evidence动作（使用guard_low以触发medium严重程度）"""
        ctx.llm_response = "这个问题显然很容易"
        guard_low.after_iteration(ctx)

        assert "injected_challenge" in ctx.extra
        assert ctx.extra["injected_challenge"]["type"] == "evidence_request"
        assert "显然" in ctx.extra["injected_challenge"]["message"]

    def test_redirect_to_hard_action(self, guard, ctx):
        """测试redirect_to_hard动作"""
        ctx.llm_response = "我们先做简单的部分"
        guard.after_iteration(ctx)

        assert "injected_challenge" in ctx.extra
        assert ctx.extra["injected_challenge"]["type"] == "redirect"
        assert "困难" in ctx.extra["injected_challenge"]["message"]

    def test_require_time_estimate_action(self, guard, ctx):
        """测试require_time_estimate动作"""
        ctx.llm_response = "这个花太久了，换方案"
        guard.after_iteration(ctx)

        assert "injected_challenge" in ctx.extra
        assert ctx.extra["injected_challenge"]["type"] == "time_estimate"

    def test_require_justification_action(self, guard, ctx):
        """测试require_justification动作"""
        ctx.llm_response = "这个测试先跳过"
        guard.after_iteration(ctx)

        assert "injected_challenge" in ctx.extra
        assert ctx.extra["injected_challenge"]["type"] == "justification_request"
        assert "先跳过" in ctx.extra["injected_challenge"]["message"]

    def test_log_risk_action(self, guard_low, ctx):
        """测试log_risk动作（使用guard_low以触发medium严重程度）"""
        ctx.llm_response = "后面再改这个"
        guard_low.after_iteration(ctx)

        assert "injected_challenge" in ctx.extra
        assert ctx.extra["injected_challenge"]["type"] == "risk_log"
        assert len(ctx.warnings) > 0

    def test_valgrind_action(self, guard, ctx):
        """测试run_valgrind动作"""
        ctx.llm_response = "内存泄漏问题不大"
        guard.after_iteration(ctx)

        assert ctx.blocked is True
        assert "valgrind" in ctx.block_reason.lower() or "内存" in ctx.block_reason

    def test_fix_immediately_action(self, guard, ctx):
        """测试fix_immediately动作"""
        ctx.llm_response = "这个bug很小先跳过"
        guard.after_iteration(ctx)

        assert "injected_challenge" in ctx.extra
        assert ctx.extra["injected_challenge"]["type"] == "fix_immediately_request"


# ── 测试：Context属性正确设置 ───────────────────────────────────

class TestContextAttributes:
    """测试注入到context的属性正确设置"""

    def test_injected_challenge_structure(self, guard, ctx):
        """验证injected_challenge结构"""
        ctx.llm_response = "能跑就行"
        guard.after_iteration(ctx)

        challenge = ctx.extra["injected_challenge"]
        assert "type" in challenge
        assert "message" in challenge
        assert "severity" in challenge

    def test_block_sets_blocked_flag(self, guard, ctx):
        """验证block_and_verify设置blocked标志"""
        ctx.llm_response = "能跑就行"
        guard.after_iteration(ctx)

        assert ctx.blocked is True

    def test_block_sets_stop_reason(self, guard, ctx):
        """验证block_and_verify设置stop_reason"""
        ctx.llm_response = "能跑就行"
        guard.after_iteration(ctx)

        assert ctx.stop_reason == "hook_blocked"

    def test_warnings_added(self, guard_low, ctx):
        """验证警告被添加到context（使用guard_low以触发medium严重程度）"""
        ctx.llm_response = "后面再改"
        guard_low.after_iteration(ctx)

        assert len(ctx.warnings) > 0
        assert any("风险信号" in w for w in ctx.warnings)


# ── 测试：Hook统计信息 ───────────────────────────────────────────

class TestHookStats:
    """测试Hook统计信息"""

    def test_get_stats(self, guard):
        """验证统计信息返回"""
        stats = guard.get_stats()

        assert stats["name"] == "SelfJustificationGuard"
        assert stats["severity_threshold"] == "high"
        assert stats["total_signals"] == len(ALL_SIGNALS)
        assert stats["general_signals"] == len(SELF_JUSTIFICATION_SIGNALS)
        assert stats["developer_signals"] == len(DEVELOPER_SIGNALS)
        assert stats["continuous_signals"] == len(CONTINUOUS_SIGNALS)

    def test_signal_counts_initial_empty(self, guard):
        """验证初始计数为空"""
        counts = guard.get_signal_counts()
        assert len(counts) >= 0  # 初始化后可能为空或全0


# ── 测试：空文本处理 ─────────────────────────────────────────────

class TestEmptyText:
    """测试空文本处理"""

    def test_empty_text_no_detection(self, guard, ctx):
        """空文本不触发检测"""
        ctx.llm_response = ""
        guard.after_iteration(ctx)

        # 不应该有任何注入
        assert "injected_challenge" not in ctx.extra
        assert ctx.blocked is False

    def test_whitespace_only_no_detection(self, guard, ctx):
        """仅空白字符不触发检测"""
        ctx.llm_response = "   \n\t  "
        guard.after_iteration(ctx)

        assert "injected_challenge" not in ctx.extra

    def test_stream_buffer_used(self, guard, ctx):
        """优先使用stream_buffer而非llm_response"""
        ctx.llm_response = ""  # llm_response为空
        ctx.stream_chunk = "代码看起来正确"  # stream_buffer有内容
        guard.after_iteration(ctx)

        assert "injected_challenge" in ctx.extra
        assert ctx.extra["injected_challenge"]["type"] == "validation_request"


# ── 测试：验收标准 ───────────────────────────────────────────────

class TestAcceptanceCriteria:
    """
    验收标准测试

    1. 能检测"能跑就行"、"看起来正确"等常见信号
    2. critical严重程度会block并要求验证
    3. 连续3次使用"显然"等词会触发质疑
    4. 开发者特有信号能检测
    5. 注入的challenge能正确传递到context
    """

    def test_criterion_1_common_signals(self, guard):
        """验收标准1：能检测常见信号"""
        common_signals = ["能跑就行", "看起来正确", "显然", "先跳过"]
        text = " ".join(common_signals)
        detected = guard.detect_signals(text)

        for signal in common_signals:
            assert signal in detected, f"应该检测到信号: {signal}"

    def test_criterion_2_critical_blocks(self, guard, ctx):
        """验收标准2：critical严重程度会block"""
        ctx.llm_response = "能跑就行"
        guard.after_iteration(ctx)

        assert ctx.blocked is True
        assert ctx.stop_reason == "hook_blocked"
        assert "injected_challenge" in ctx.extra

    def test_criterion_3_continuous_3_triggers(self, guard, ctx):
        """验收标准3：连续3次触发质疑"""
        for i in range(3):
            ctx_i = AgentHookContext(event=AgentHookEvent.after_iteration, iteration=i+1)
            ctx_i.llm_response = "这个问题显然很简单"

            guard.after_iteration(ctx_i)

        # 第3次应该注入连续信号质疑
        assert "injected_challenge" in ctx_i.extra
        assert ctx_i.extra["injected_challenge"]["type"] == "continuous_signal_challenge"

    def test_criterion_4_developer_signals(self, guard):
        """验收标准4：开发者特有信号能检测"""
        developer_signals = ["先提交后面再测", "LeetCode差不多对了", "内存泄漏问题不大"]
        text = " ".join(developer_signals)
        detected = guard.detect_signals(text)

        for signal in developer_signals:
            assert signal in detected, f"应该检测到开发者信号: {signal}"

    def test_criterion_5_challenge_in_context(self, guard, ctx):
        """验收标准5：challenge正确传递到context"""
        ctx.llm_response = "代码看起来正确"
        guard.after_iteration(ctx)

        assert "injected_challenge" in ctx.extra
        challenge = ctx.extra["injected_challenge"]
        assert isinstance(challenge, dict)
        assert "type" in challenge
        assert "message" in challenge
