"""
V3.0 Phase 0 - Agent层Hook系统测试
====================================
测试范围：V3.0 Phase 0 AgentHook生命周期系统
- AgentHookEvent 枚举
- AgentHook 基类可继承性
- CompositeHook 错误隔离
- AgentHookContext 上下文

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/test_agent_hooks.py -v --tb=short
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.hooks import (
    AgentHook,
    AgentHookEvent,
    AgentHookContext,
    CompositeHook,
    get_composite_hook,
    reset_composite_hook,
)


# ============================================================================
# SECTION 1: AgentHookEvent 枚举测试
# ============================================================================

class TestAgentHookEvent:
    """AgentHookEvent 枚举测试"""

    def test_all_events_present(self):
        """AE-01: 所有9个Hook点都已定义"""
        expected = {
            "before_iteration",
            "after_iteration",
            "before_llm",
            "after_llm",
            "on_stream",
            "before_execute_tools",
            "after_execute_tools",
            "on_error",
            "on_complete",
        }
        actual = {e.name.lower() for e in AgentHookEvent}
        assert expected.issubset(actual), f"Missing: {expected - actual}"

    def test_event_values_prefix(self):
        """AE-02: 所有事件值都有agent:前缀"""
        for event in AgentHookEvent:
            assert event.value.startswith("agent:"), f"{event.name} missing agent: prefix"

    def test_event_category(self):
        """AE-03: category属性正确"""
        assert AgentHookEvent.before_iteration.category == "agent"
        assert AgentHookEvent.before_llm.category == "agent"
        assert AgentHookEvent.on_error.category == "agent"

    def test_event_str(self):
        """AE-04: str(event) 返回value"""
        assert str(AgentHookEvent.before_iteration) == "agent:before_iteration"


# ============================================================================
# SECTION 2: AgentHook 基类测试
# ============================================================================

class TestAgentHookBase:
    """AgentHook 基类可继承性测试"""

    def test_can_inherit(self):
        """AH-01: AgentHook可被继承"""
        class MyHook(AgentHook):
            name = "my_hook"
            priority = 50

        hook = MyHook()
        assert hook.name == "my_hook"
        assert hook.priority == 50
        assert hook.enabled is True

    def test_default_priority(self):
        """AH-02: 默认priority为100"""
        class NoPriorityHook(AgentHook):
            name = "no_priority"

        hook = NoPriorityHook()
        assert hook.priority == 100

    def test_all_hook_methods_exist(self):
        """AH-03: 所有8个Hook点方法都存在"""
        hook = AgentHook()
        methods = [
            "before_iteration", "after_iteration",
            "before_llm", "after_llm", "on_stream",
            "before_execute_tools", "after_execute_tools",
            "on_error", "on_complete",
        ]
        for m in methods:
            assert hasattr(hook, m), f"Missing method: {m}"
            assert callable(getattr(hook, m)), f"Not callable: {m}"

    def test_methods_return_context(self):
        """AH-04: 所有Hook方法默认返回ctx"""
        class DummyHook(AgentHook):
            name = "dummy"

        ctx = AgentHookContext(event=AgentHookEvent.before_iteration)
        hook = DummyHook()

        for method_name in ["before_iteration", "after_iteration", "before_llm",
                            "after_llm", "before_execute_tools", "after_execute_tools",
                            "on_complete"]:
            method = getattr(hook, method_name)
            result = method(ctx)
            assert result is ctx, f"{method_name} should return ctx"

    def test_on_error_returns_context(self):
        """AH-05: on_error方法接收error参数并返回ctx"""
        class DummyHook(AgentHook):
            name = "dummy"

        ctx = AgentHookContext(event=AgentHookEvent.on_error)
        hook = DummyHook()
        result = hook.on_error(ctx, ValueError("test error"))
        assert result is ctx
        assert ctx.error is not None

    def test_on_stream_returns_context(self):
        """AH-06: on_stream方法接收chunk参数并累积"""
        class DummyHook(AgentHook):
            name = "dummy"

        ctx = AgentHookContext(event=AgentHookEvent.on_stream, stream_chunk="")
        hook = DummyHook()

        result = hook.on_stream(ctx, "Hello")
        result = hook.on_stream(result, " World")
        assert result.stream_chunk == "Hello World"


# ============================================================================
# SECTION 3: AgentHookContext 测试
# ============================================================================

class TestAgentHookContext:
    """AgentHookContext 上下文测试"""

    def test_context_creation(self):
        """AHC-01: 基本创建"""
        ctx = AgentHookContext(event=AgentHookEvent.before_iteration)
        assert ctx.event == AgentHookEvent.before_iteration
        assert ctx.iteration == 1
        assert ctx.max_iterations == 10
        assert ctx.blocked is False

    def test_context_iteration_fields(self):
        """AHC-02: 迭代相关字段"""
        ctx = AgentHookContext(
            event=AgentHookEvent.before_iteration,
            iteration=3,
            max_iterations=10,
            goal="查询用户表",
            session_id="sess-001",
            user_id="user-001",
        )
        assert ctx.iteration == 3
        assert ctx.goal == "查询用户表"
        assert ctx.session_id == "sess-001"

    def test_context_token_fields(self):
        """AHC-03: Token管理字段"""
        ctx = AgentHookContext(
            event=AgentHookEvent.after_llm,
            token_count=5000,
            token_budget=10000,
        )
        assert ctx.is_token_over_budget() is False
        ctx.token_count = 10000
        assert ctx.is_token_over_budget() is True

    def test_context_iteration_exhausted(self):
        """AHC-04: 迭代耗尽检查"""
        ctx = AgentHookContext(
            event=AgentHookEvent.after_iteration,
            iteration=10,
            max_iterations=10,
        )
        assert ctx.is_iteration_exhausted() is True
        ctx.iteration = 9
        assert ctx.is_iteration_exhausted() is False

    def test_context_set_blocked(self):
        """AHC-05: set_blocked设置阻止状态"""
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx.set_blocked("Too many iterations")
        assert ctx.blocked is True
        assert ctx.block_reason == "Too many iterations"
        assert ctx.stop_reason == "hook_blocked"

    def test_context_add_warning(self):
        """AHC-06: add_warning添加警告"""
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx.add_warning("Slow query detected")
        ctx.add_warning("High token usage")
        assert len(ctx.warnings) == 2
        assert "Slow query" in ctx.warnings[0]

    def test_context_tools(self):
        """AHC-07: 工具相关字段"""
        ctx = AgentHookContext(event=AgentHookEvent.before_execute_tools)
        ctx.tools_to_execute = [
            {"name": "execute_sql", "params": {"sql": "SELECT 1"}}
        ]
        assert len(ctx.tools_to_execute) == 1

        ctx2 = AgentHookContext(event=AgentHookEvent.after_execute_tools)
        ctx2.tool_results = [
            {"name": "execute_sql", "result": {"rows": 1}}
        ]
        assert len(ctx2.tool_results) == 1

    def test_context_llm_response(self):
        """AHC-08: LLM响应字段"""
        ctx = AgentHookContext(event=AgentHookEvent.after_llm)
        ctx.llm_response = "SELECT * FROM users LIMIT 10"
        assert "users" in ctx.llm_response

    def test_context_stream_chunk(self):
        """AHC-09: 流式chunk累积"""
        ctx = AgentHookContext(event=AgentHookEvent.on_stream, stream_chunk="")
        ctx.stream_chunk = "Hello "
        ctx.stream_chunk += "World"
        assert ctx.get_stream_buffer() == "Hello World"

    def test_context_extra(self):
        """AHC-10: extra字段可存储任意数据"""
        ctx = AgentHookContext(event=AgentHookEvent.before_llm)
        ctx.extra["custom_field"] = {"nested": "value"}
        assert ctx.extra["custom_field"]["nested"] == "value"

    def test_context_to_dict(self):
        """AHC-11: to_dict序列化"""
        ctx = AgentHookContext(
            event=AgentHookEvent.after_iteration,
            iteration=2,
            goal="Test goal",
            blocked=False,
        )
        d = ctx.to_dict()
        assert d["event"] == "agent:after_iteration"
        assert d["iteration"] == 2
        assert d["goal"] == "Test goal"
        assert d["blocked"] is False


# ============================================================================
# SECTION 4: CompositeHook 错误隔离测试
# ============================================================================

class TestCompositeHookErrorIsolation:
    """CompositeHook 错误隔离测试 - 核心验收测试"""

    def test_hook_failure_does_not_crash_other_hooks(self):
        """CIE-01: 单个Hook抛异常不影响其他Hook执行"""
        execution_order = []

        class FailingHook(AgentHook):
            name = "failing"
            priority = 10

            def after_iteration(self, ctx):
                execution_order.append("failing")
                raise RuntimeError("Intentional failure")

        class SucceedingHook(AgentHook):
            name = "succeeding"
            priority = 20

            def after_iteration(self, ctx):
                execution_order.append("succeeding")
                return ctx

        class AnotherSucceedingHook(AgentHook):
            name = "another"
            priority = 30

            def after_iteration(self, ctx):
                execution_order.append("another")
                return ctx

        composite = CompositeHook([
            FailingHook(),
            SucceedingHook(),
            AnotherSucceedingHook(),
        ])

        ctx = AgentHookContext(event=AgentHookEvent.after_iteration, iteration=1)
        result_ctx = composite.after_iteration(ctx)

        # 关键断言：所有Hook都应该被调用，即使前面的失败了
        assert "failing" in execution_order, "FailingHook should have been called"
        assert "succeeding" in execution_order, "SucceedingHook should have been called"
        assert "another" in execution_order, "AnotherSucceedingHook should have been called"
        assert result_ctx is not None, "Should return context even after failures"

    def test_hook_failure_isolated_in_all_lifecycle_points(self):
        """CIE-02: 所有Hook点都支持错误隔离"""
        hook_points = [
            "before_iteration",
            "after_iteration",
            "before_llm",
            "after_llm",
            "before_execute_tools",
            "after_execute_tools",
            "on_complete",
        ]

        class AlwaysFailsHook(AgentHook):
            name = "always_fails"
            priority = 1

            def __getattr__(self, name):
                if name in hook_points:
                    def fail_method(ctx, *args, **kwargs):
                        raise ValueError(f"Failed in {name}")
                    return fail_method
                raise AttributeError(name)

        composite = CompositeHook([AlwaysFailsHook()])

        for event_name, hook_method_name in [
            ("before_iteration", "before_iteration"),
            ("after_iteration", "after_iteration"),
            ("before_llm", "before_llm"),
            ("after_llm", "after_llm"),
            ("before_execute_tools", "before_execute_tools"),
            ("after_execute_tools", "after_execute_tools"),
            ("on_complete", "on_complete"),
        ]:
            event = getattr(AgentHookEvent, event_name.replace("_", "_"))
            ctx = AgentHookContext(event=event)
            method = getattr(composite, hook_method_name)
            # 不应抛异常
            result = method(ctx)
            assert result is not None

    def test_on_error_error_isolation(self):
        """CIE-03: on_error Hook点的错误隔离"""
        call_count = [0]

        class FailingOnErrorHook(AgentHook):
            name = "fail_on_error"
            priority = 10

            def on_error(self, ctx, error):
                call_count[0] += 1
                raise RuntimeError("Nested error")

        class SucceedingOnErrorHook(AgentHook):
            name = "succeed_on_error"
            priority = 20

            def on_error(self, ctx, error):
                call_count[0] += 1
                return ctx

        composite = CompositeHook([
            FailingOnErrorHook(),
            SucceedingOnErrorHook(),
        ])

        ctx = AgentHookContext(event=AgentHookEvent.on_error)
        result = composite.on_error(ctx, ValueError("Original error"))

        # 两个on_error hook都应该被调用
        assert call_count[0] == 2, "Both on_error hooks should be called"


# ============================================================================
# SECTION 5: CompositeHook 优先级排序测试
# ============================================================================

class TestCompositeHookPriority:
    """CompositeHook 优先级排序测试"""

    def test_hooks_sorted_by_priority_ascending(self):
        """CP-01: Hook按priority从小到大排序（数字小=优先级高）"""
        execution_order = []

        class HookA(AgentHook):
            name = "hook_a"
            priority = 100

            def before_iteration(self, ctx):
                execution_order.append("a")
                return ctx

        class HookB(AgentHook):
            name = "hook_b"
            priority = 10

            def before_iteration(self, ctx):
                execution_order.append("b")
                return ctx

        class HookC(AgentHook):
            name = "hook_c"
            priority = 50

            def before_iteration(self, ctx):
                execution_order.append("c")
                return ctx

        # 按随机顺序注册
        composite = CompositeHook([HookA(), HookC(), HookB()])

        ctx = AgentHookContext(event=AgentHookEvent.before_iteration)
        composite.before_iteration(ctx)

        # 期望顺序：priority 10(b) < 50(c) < 100(a)
        assert execution_order == ["b", "c", "a"], f"Expected [b,c,a], got {execution_order}"

    def test_register_after_init_sorts_automatically(self):
        """CP-02: init之后register也自动排序"""
        execution_order = []

        class LowPriority(AgentHook):
            name = "low"
            priority = 100
            def before_iteration(self, ctx):
                execution_order.append("low")
                return ctx

        class HighPriority(AgentHook):
            name = "high"
            priority = 1
            def before_iteration(self, ctx):
                execution_order.append("high")
                return ctx

        composite = CompositeHook([LowPriority()])
        composite.register(HighPriority())

        ctx = AgentHookContext(event=AgentHookEvent.before_iteration)
        composite.before_iteration(ctx)

        assert execution_order == ["high", "low"], f"Expected [high,low], got {execution_order}"

    def test_disabled_hook_not_called(self):
        """CP-03: enabled=False的Hook不会被调用"""
        call_count = [0]

        class DisabledHook(AgentHook):
            name = "disabled"
            priority = 10
            enabled = False

            def before_iteration(self, ctx):
                call_count[0] += 1
                return ctx

        class EnabledHook(AgentHook):
            name = "enabled"
            priority = 20

            def before_iteration(self, ctx):
                call_count[0] += 1
                return ctx

        composite = CompositeHook([DisabledHook(), EnabledHook()])

        ctx = AgentHookContext(event=AgentHookEvent.before_iteration)
        composite.before_iteration(ctx)

        assert call_count[0] == 1, "Only enabled hook should be called"


# ============================================================================
# SECTION 6: CompositeHook 链式修改测试
# ============================================================================

class TestCompositeHookChainModification:
    """CompositeHook 链式修改测试"""

    def test_later_hook_sees_earlier_modifications(self):
        """CCM-01: 后执行的Hook能看到前Hook的修改"""
        class FirstHook(AgentHook):
            name = "first"
            priority = 10

            def after_iteration(self, ctx):
                ctx.extra["seen_by_first"] = True
                ctx.extra["first_extra"] = "added by first"
                return ctx

        class SecondHook(AgentHook):
            name = "second"
            priority = 20

            def after_iteration(self, ctx):
                # 验证能看到first的修改
                assert ctx.extra.get("seen_by_first") is True
                assert ctx.extra.get("first_extra") == "added by first"
                ctx.extra["seen_by_second"] = True
                return ctx

        class ThirdHook(AgentHook):
            name = "third"
            priority = 30

            def after_iteration(self, ctx):
                # 验证能看到前两个hook的修改
                assert ctx.extra.get("seen_by_first") is True
                assert ctx.extra.get("seen_by_second") is True
                ctx.extra["seen_by_third"] = True
                return ctx

        composite = CompositeHook([ThirdHook(), FirstHook(), SecondHook()])

        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        result = composite.after_iteration(ctx)

        assert result.extra.get("seen_by_first") is True
        assert result.extra.get("seen_by_second") is True
        assert result.extra.get("seen_by_third") is True


# ============================================================================
# SECTION 7: get_composite_hook 全局单例测试
# ============================================================================

class TestGlobalCompositeHook:
    """全局CompositeHook单例测试"""

    def test_get_composite_hook_returns_same_instance(self):
        """GCG-01: get_composite_hook返回同一实例"""
        reset_composite_hook()
        instance1 = get_composite_hook()
        instance2 = get_composite_hook()
        assert instance1 is instance2

    def test_reset_clears_singleton(self):
        """GCG-02: reset_composite_hook清空单例"""
        reset_composite_hook()
        instance1 = get_composite_hook()
        reset_composite_hook()
        instance2 = get_composite_hook()
        assert instance1 is not instance2


# ============================================================================
# SECTION 8: 所有Hook点可调用测试
# ============================================================================

class TestAllHookPointsCallable:
    """所有8个Hook点可调用测试"""

    @pytest.fixture
    def composite(self):
        class LoggingHook(AgentHook):
            name = "logging"
            priority = 999

        return CompositeHook([LoggingHook()])

    def test_all_8_hook_points_callable(self, composite):
        """AHP-01: 所有8个Hook点方法都可调用"""
        ctx = AgentHookContext(event=AgentHookEvent.before_iteration)

        # 这些都不应抛异常
        composite.before_iteration(ctx)
        composite.after_iteration(ctx)
        composite.before_llm(ctx)
        composite.after_llm(ctx)
        composite.on_stream(ctx, "chunk")
        composite.before_execute_tools(ctx)
        composite.after_execute_tools(ctx)
        composite.on_complete(ctx)

    def test_on_error_with_exception(self, composite):
        """AHP-02: on_error接收Exception参数"""
        ctx = AgentHookContext(event=AgentHookEvent.on_error)
        result = composite.on_error(ctx, ValueError("test"))
        assert result is not None
