"""
AutoVerificationHook 集成测试 - V3.1 P0 功能
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.hooks.auto_verification_hook import AutoVerificationHook
from src.hooks.hook_context import AgentHookContext
from src.hooks.hook_events import AgentHookEvent


class TestAutoVerificationHookCore:
    def test_hook_initialization_defaults(self):
        hook = AutoVerificationHook()
        assert hook.name == "auto_verification"
        assert hook.priority == 40
        assert hook.require_evidence is True

    def test_no_verification_needed_passthrough(self):
        hook = AutoVerificationHook()
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration, goal="test")
        result = hook.after_iteration(ctx)
        assert result is ctx
        assert not result.blocked

    def test_verification_request_no_evidence_blocked(self):
        hook = AutoVerificationHook(require_evidence=True)
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx.extra["verification_request"] = True
        result = hook.after_iteration(ctx)
        assert result.blocked is True
        assert "injected_challenge" in result.extra

    def test_verification_request_with_proof_pass(self):
        hook = AutoVerificationHook(require_evidence=True)
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx.extra["verification_request"] = True
        ctx.extra["verification_proof"] = "pytest tests/ -v -> 15 passed"
        result = hook.after_iteration(ctx)
        assert not result.blocked

    def test_verification_passed_flag(self):
        hook = AutoVerificationHook()
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx.extra["verification_request"] = True
        ctx.extra["verification_passed"] = True
        result = hook.after_iteration(ctx)
        assert not result.blocked


class TestVerificationEvidence:
    def test_tool_results_with_passed_keyword(self):
        hook = AutoVerificationHook()
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx.extra["verification_request"] = True
        ctx.extra["tool_results"] = [{"name": "bash", "result": "10 passed"}]
        result = hook.after_iteration(ctx)
        assert not result.blocked

    def test_tool_results_with_chinese_passed(self):
        hook = AutoVerificationHook()
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx.extra["verification_request"] = True
        ctx.extra["tool_results"] = [{"name": "check", "result": "验证通过"}]
        result = hook.after_iteration(ctx)
        assert not result.blocked

    def test_proof_too_short_blocked(self):
        hook = AutoVerificationHook()
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx.extra["verification_request"] = True
        ctx.extra["verification_proof"] = "ok"
        result = hook.after_iteration(ctx)
        assert result.blocked is True


class TestAutoVerificationStats:
    def test_stats_tracking(self):
        hook = AutoVerificationHook()
        
        ctx1 = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx1.extra["verification_request"] = True
        hook.after_iteration(ctx1)
        
        ctx2 = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx2.extra["verification_request"] = True
        ctx2.extra["verification_passed"] = True
        hook.after_iteration(ctx2)
        
        stats = hook.get_stats()
        assert stats["stats"]["requested"] == 2
        assert stats["stats"]["verified"] == 1
        assert stats["stats"]["blocked"] == 1


class TestAutoVerificationNoEvidenceRequired:
    def test_no_evidence_required_passes(self):
        hook = AutoVerificationHook(require_evidence=False)
        ctx = AgentHookContext(event=AgentHookEvent.after_iteration)
        ctx.extra["verification_request"] = True
        result = hook.after_iteration(ctx)
        assert not result.blocked


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
