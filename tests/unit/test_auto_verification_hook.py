"""
AutoVerificationHook 测试
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.hooks.auto_verification_hook import AutoVerificationHook
from src.hooks.hook_context import AgentHookContext
from src.hooks.hook_events import AgentHookEvent


class TestAutoVerificationHook:
    """AutoVerificationHook测试"""

    def test_hook_initialization(self):
        hook = AutoVerificationHook()
        assert hook.name == "auto_verification"
        assert hook.require_evidence is True

    def test_no_verification_needed(self):
        """无验证请求时不做处理"""
        hook = AutoVerificationHook()
        ctx = AgentHookContext(
            event=AgentHookEvent.after_iteration,
            goal="test",
        )
        result = hook.after_iteration(ctx)
        assert result is ctx
        assert not result.blocked

    def test_verification_needed_without_evidence(self):
        """需要验证但无证据时被阻止"""
        hook = AutoVerificationHook(require_evidence=True)
        ctx = AgentHookContext(
            event=AgentHookEvent.after_iteration,
            goal="test",
        )
        ctx.extra["verification_request"] = True

        result = hook.after_iteration(ctx)
        assert result.blocked is True
        assert "injected_challenge" in result.extra

    def test_verification_needed_with_proof(self):
        """需要验证且有证据时通过"""
        hook = AutoVerificationHook(require_evidence=True)
        ctx = AgentHookContext(
            event=AgentHookEvent.after_iteration,
            goal="test",
        )
        ctx.extra["verification_request"] = True
        ctx.extra["verification_proof"] = "pytest tests/ -v -> 10 passed"

        result = hook.after_iteration(ctx)
        assert not result.blocked

    def test_verification_needed_with_passed_flag(self):
        """需要验证且有passed标记时通过"""
        hook = AutoVerificationHook(require_evidence=True)
        ctx = AgentHookContext(
            event=AgentHookEvent.after_iteration,
            goal="test",
        )
        ctx.extra["verification_request"] = True
        ctx.extra["verification_passed"] = True

        result = hook.after_iteration(ctx)
        assert not result.blocked

    def test_stats_tracking(self):
        """统计信息跟踪"""
        hook = AutoVerificationHook()

        # 验证请求但无证据
        ctx1 = AgentHookContext(event=AgentHookEvent.after_iteration, goal="test1")
        ctx1.extra["verification_request"] = True
        hook.after_iteration(ctx1)

        # 验证请求且有证据
        ctx2 = AgentHookContext(event=AgentHookEvent.after_iteration, goal="test2")
        ctx2.extra["verification_request"] = True
        ctx2.extra["verification_passed"] = True
        hook.after_iteration(ctx2)

        stats = hook.get_stats()
        assert stats["stats"]["requested"] == 2
        assert stats["stats"]["verified"] == 1
        assert stats["stats"]["blocked"] == 1

    def test_get_stats(self):
        """get_stats返回正确格式"""
        hook = AutoVerificationHook(require_evidence=False)
        stats = hook.get_stats()

        assert stats["name"] == "auto_verification"
        assert stats["require_evidence"] is False
        assert "stats" in stats
