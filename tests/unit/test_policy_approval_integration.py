"""P0-1测试: PolicyEngine × ApprovalGate 端到端集成"""
import pytest
import time
import tempfile
import os
from unittest.mock import MagicMock, AsyncMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.gateway.policy_engine import PolicyEngine, PolicyContext, UserRole, get_policy_engine
from src.models.approval import ApprovalGate, ApprovalStore, ApprovalStatus
from src.tools.base import RiskLevel


class TestPolicyEngineApprovalGateIntegration:
    """PolicyEngine与ApprovalGate集成测试"""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._store_path = os.path.join(self._tmpdir, "approvals.jsonl")
        self._store = ApprovalStore(store_path=self._store_path)
        self._gate = ApprovalGate(store=self._store)
        self._policy = PolicyEngine(approval_gate=self._gate)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_policy_engine_has_approval_gate(self):
        """PolicyEngine持有ApprovalGate"""
        assert self._policy.approval_gate is not None
        assert isinstance(self._policy.approval_gate, ApprovalGate)

    def test_l5_needs_approval_from_policy(self):
        """L5工具策略检查返回需要审批"""
        ctx = PolicyContext(user_id="user1", user_role=UserRole.ADMIN)
        result = self._policy.check(ctx, "tool.kill_session", RiskLevel.L5_HIGH)
        assert result.allowed is True
        assert result.approval_required is True
        assert len(result.approvers) == 2  # 双人审批

    def test_l5_submit_approval_request(self):
        """L5工具触发提交审批申请"""
        tool_call_id = "call_kill_session_user1_123456"
        record = self._policy.request_approval(
            tool_call_id=tool_call_id,
            tool_name="kill_session",
            tool_params={"instance_id": "INS-001"},
            risk_level=5,
            requester="user1",
            reason="紧急解除锁等待",
            session_id="sess_001",
        )
        assert record.status == ApprovalStatus.PENDING
        assert record.tool_name == "kill_session"
        assert record.risk_level == 5

    def test_approval_gate_check_not_approved(self):
        """ApprovalGate检查：未审批的L5工具不可执行"""
        tool_call_id = "call_not_approved"
        ok, msg = self._gate.check_can_execute(tool_call_id)
        assert ok is False
        assert "无审批记录" in msg

    def test_approval_gate_is_approved_method(self):
        """ApprovalGate.is_approved() 方法"""
        tool_call_id = "call_approved_test"
        # 未提交审批
        assert self._gate.is_approved(tool_call_id) is False
        
        # 提交审批
        record = self._gate.request_approval(
            tool_call_id=tool_call_id,
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        # 第一审批人审批
        self._store.approve1(record.id, "manager1")
        assert self._gate.is_approved(tool_call_id) is False
        
        # 第二审批人审批
        self._store.approve2(record.id, "manager2")
        assert self._gate.is_approved(tool_call_id) is True

    def test_full_e2e_approval_flow(self):
        """完整端到端：L5工具 → 审批 → 执行"""
        user_id = "user1"
        session_id = "sess_001"
        instance_id = "INS-001"
        tool_call_id = f"call_kill_session_{user_id}_{int(time.time() * 1000)}"

        # Step 1: 策略检查 - L5需要审批
        ctx = PolicyContext(user_id=user_id, user_role=UserRole.ADMIN, session_id=session_id)
        policy_result = self._policy.check(ctx, "tool.kill_session", RiskLevel.L5_HIGH)
        assert policy_result.allowed is True
        assert policy_result.approval_required is True

        # Step 2: 提交审批申请
        record = self._policy.request_approval(
            tool_call_id=tool_call_id,
            tool_name="kill_session",
            tool_params={"instance_id": instance_id},
            risk_level=5,
            requester=user_id,
            reason="紧急解除锁等待",
            session_id=session_id,
            approver1="manager1",
            approver2="manager2",
        )
        assert record.status == ApprovalStatus.PENDING
        assert record.approver1 == "manager1"
        assert record.approver2 == "manager2"

        # Step 3: 第一审批人审批
        record = self._store.approve1(record.id, "manager1")
        assert record.status == ApprovalStatus.APPROVED1
        assert self._gate.is_approved(tool_call_id) is False

        # Step 4: 第二审批人审批
        record = self._store.approve2(record.id, "manager2")
        assert record.status == ApprovalStatus.APPROVED2
        assert self._gate.is_approved(tool_call_id) is True

        # Step 5: 执行后标记
        executed = self._gate.enforce_execution(tool_call_id, executor="user1", result="session killed")
        assert executed.status == ApprovalStatus.EXECUTED
        assert executed.executor == "user1"

    def test_full_e2e_rejected_flow(self):
        """完整端到端：L5工具 → 审批被拒"""
        user_id = "user2"
        session_id = "sess_002"
        tool_call_id = f"call_kill_session_{user_id}_{int(time.time() * 1000)}"

        # 提交审批
        record = self._policy.request_approval(
            tool_call_id=tool_call_id,
            tool_name="kill_session",
            tool_params={"instance_id": "INS-002"},
            risk_level=5,
            requester=user_id,
            reason="可疑请求",
            session_id=session_id,
        )
        
        # 被拒绝
        rejected = self._store.reject(record.id, "manager1", "理由不充分，风险过高")
        assert rejected.status == ApprovalStatus.REJECTED
        assert self._gate.is_approved(tool_call_id) is False
        
        # 执行前检查不可通过
        ok, msg = self._gate.check_can_execute(tool_call_id)
        assert ok is False
        assert "审批状态: rejected" in msg.lower()

    def test_get_approval_status(self):
        """获取审批状态方法"""
        tool_call_id = "call_status_test"
        
        # 无记录
        assert self._gate.get_approval_status(tool_call_id) is None
        
        # 提交
        record = self._policy.request_approval(
            tool_call_id=tool_call_id,
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        assert self._gate.get_approval_status(tool_call_id) == ApprovalStatus.PENDING
        
        # 第一审批
        self._store.approve1(record.id, "manager1")
        assert self._gate.get_approval_status(tool_call_id) == ApprovalStatus.APPROVED1

    def test_approval_gate_singleton_via_policy(self):
        """通过PolicyEngine获取ApprovalGate单例"""
        policy = get_policy_engine()
        gate1 = policy.approval_gate
        gate2 = policy.approval_gate
        assert gate1 is gate2

    def test_request_approval_dup_raises(self):
        """重复提交审批应抛出异常"""
        tool_call_id = "call_dup_test"
        self._policy.request_approval(
            tool_call_id=tool_call_id,
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        with pytest.raises(ValueError, match="已有审批记录"):
            self._policy.request_approval(
                tool_call_id=tool_call_id,
                tool_name="kill_session",
                tool_params={},
                risk_level=5,
                requester="user1",
                reason="test2",
            )
