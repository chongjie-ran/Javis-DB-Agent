"""P0-1测试: L5双人审批完整状态机"""
import pytest
import time
import tempfile
import os
from src.models.approval import (
    ApprovalRecord, ApprovalStatus, ApprovalStore, ApprovalGate,
    ApprovalStore, get_approval_store, get_approval_gate,
)


class TestApprovalRecord:
    """ApprovalRecord数据模型测试"""

    def test_default_status_is_pending(self):
        record = ApprovalRecord(
            tool_call_id="call_001",
            tool_name="kill_session",
            tool_params={"instance_id": "INS-001"},
            risk_level=5,
            requester="user1",
            reason="紧急解除锁等待",
        )
        assert record.status == ApprovalStatus.PENDING
        assert record.is_executable is False
        assert record.is_terminal is False

    def test_is_executable_when_approved2(self):
        record = ApprovalRecord(
            tool_call_id="call_001",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        record.status = ApprovalStatus.APPROVED2
        assert record.is_executable is True

    def test_is_terminal_for_rejected(self):
        record = ApprovalRecord(
            tool_call_id="call_001",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        record.status = ApprovalStatus.REJECTED
        assert record.is_terminal is True

    def test_can_transition_valid(self):
        record = ApprovalRecord(
            tool_call_id="call_001",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        # PENDING -> APPROVED1 ✓
        assert record.can_transition_to(ApprovalStatus.APPROVED1) is True
        # PENDING -> REJECTED ✓
        assert record.can_transition_to(ApprovalStatus.REJECTED) is True
        # PENDING -> EXECUTED ✗
        assert record.can_transition_to(ApprovalStatus.EXECUTED) is False

    def test_state_machine_full_flow(self):
        record = ApprovalRecord(
            tool_call_id="call_001",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        assert record.status == ApprovalStatus.PENDING

        # PENDING -> APPROVED1
        record.status = ApprovalStatus.APPROVED1
        record.approver1 = "manager1"
        record.approver1_at = time.time()
        assert record.can_transition_to(ApprovalStatus.APPROVED2) is True

        # APPROVED1 -> APPROVED2
        record.status = ApprovalStatus.APPROVED2
        record.approver2 = "manager2"
        record.approver2_at = time.time()
        assert record.is_executable is True
        assert record.can_transition_to(ApprovalStatus.EXECUTED) is True


class TestApprovalStore:
    """ApprovalStore测试"""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._store_path = os.path.join(self._tmpdir, "approvals.jsonl")
        self._store = ApprovalStore(store_path=self._store_path)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_submit_creates_pending_record(self):
        record = self._store.submit(
            tool_call_id="call_test_001",
            tool_name="kill_session",
            tool_params={"instance_id": "INS-001"},
            risk_level=5,
            requester="user1",
            reason="解除锁等待",
            session_id="sess_001",
        )
        assert record.status == ApprovalStatus.PENDING
        assert record.tool_call_id == "call_test_001"
        assert record.tool_name == "kill_session"
        assert record.risk_level == 5

    def test_submit_duplicate_raises(self):
        self._store.submit(
            tool_call_id="call_dup",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        with pytest.raises(ValueError, match="已有审批记录"):
            self._store.submit(
                tool_call_id="call_dup",
                tool_name="kill_session",
                tool_params={},
                risk_level=5,
                requester="user2",
                reason="test2",
            )

    def test_approve1_flow(self):
        record = self._store.submit(
            tool_call_id="call_ap1",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        approved = self._store.approve1(record.id, "manager1")
        assert approved.status == ApprovalStatus.APPROVED1
        assert approved.approver1 == "manager1"
        assert approved.approver1_at is not None

    def test_approve2_only_after_approve1(self):
        record = self._store.submit(
            tool_call_id="call_ap2",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        # 不能跳过第一审批直接第二审批
        with pytest.raises(ValueError, match="必须先完成第一审批"):
            self._store.approve2(record.id, "manager2")

    def test_approve2_after_approve1(self):
        record = self._store.submit(
            tool_call_id="call_ap2_full",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        self._store.approve1(record.id, "manager1")
        approved2 = self._store.approve2(record.id, "manager2")
        assert approved2.status == ApprovalStatus.APPROVED2
        assert approved2.is_executable is True

    def test_reject_from_pending(self):
        record = self._store.submit(
            tool_call_id="call_rej",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        rejected = self._store.reject(record.id, "manager1", "理由不充分")
        assert rejected.status == ApprovalStatus.REJECTED
        assert rejected.rejector == "manager1"
        assert rejected.reject_reason == "理由不充分"

    def test_reject_terminal_cannot_reject_again(self):
        record = self._store.submit(
            tool_call_id="call_rej2",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        self._store.reject(record.id, "manager1", "拒绝")
        with pytest.raises(ValueError, match="终态"):
            self._store.reject(record.id, "manager2", "再次拒绝")

    def test_mark_executed_only_after_approved2(self):
        record = self._store.submit(
            tool_call_id="call_exec",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        # pending状态不能执行
        with pytest.raises(ValueError, match="必须先完成双人审批"):
            self._store.mark_executed(record.id, "executor", "done")
        # approved1状态也不能执行
        self._store.approve1(record.id, "manager1")
        with pytest.raises(ValueError, match="必须先完成双人审批"):
            self._store.mark_executed(record.id, "executor", "done")

    def test_mark_executed_after_approved2(self):
        record = self._store.submit(
            tool_call_id="call_exec2",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        self._store.approve1(record.id, "manager1")
        self._store.approve2(record.id, "manager2")
        executed = self._store.mark_executed(record.id, "executor", "会话已终止")
        assert executed.status == ApprovalStatus.EXECUTED
        assert executed.executor == "executor"

    def test_list_pending(self):
        self._store.submit(tool_call_id="p1", tool_name="t1", tool_params={}, risk_level=5, requester="u1", reason="r")
        self._store.submit(tool_call_id="p2", tool_name="t2", tool_params={}, risk_level=5, requester="u2", reason="r")
        pending = self._store.list_pending()
        assert len(pending) == 2

    def test_cancel_pending(self):
        record = self._store.submit(
            tool_call_id="call_cancel",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        cancelled = self._store.cancel(record.id)
        assert cancelled.status == ApprovalStatus.CANCELLED

    def test_expire_pending(self):
        record = self._store.submit(
            tool_call_id="call_expire",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
            ttl_seconds=-1,  # 已过期
        )
        expired = self._store.expire_pending()
        assert record.id in expired
        assert self._store.get(record.id).status == ApprovalStatus.EXPIRED


class TestApprovalGate:
    """ApprovalGate集成测试"""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._store_path = os.path.join(self._tmpdir, "approvals.jsonl")
        from src.models.approval import ApprovalStore, ApprovalGate
        self._store = ApprovalStore(store_path=self._store_path)
        self._gate = ApprovalGate(store=self._store)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_requires_approval_l5(self):
        assert self._gate.requires_approval(5) is True
        assert self._gate.requires_approval(4) is False

    def test_check_can_execute_no_record(self):
        ok, msg = self._gate.check_can_execute("nonexistent")
        assert ok is False
        assert "无审批记录" in msg

    def test_check_can_execute_pending(self):
        record = self._store.submit(
            tool_call_id="call_gate1",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        ok, msg = self._gate.check_can_execute("call_gate1")
        assert ok is False
        assert "pending" in msg.lower() or "审批" in msg

    def test_check_can_execute_approved2(self):
        record = self._store.submit(
            tool_call_id="call_gate2",
            tool_name="kill_session",
            tool_params={},
            risk_level=5,
            requester="user1",
            reason="test",
        )
        self._store.approve1(record.id, "manager1")
        self._store.approve2(record.id, "manager2")
        ok, msg = self._gate.check_can_execute("call_gate2")
        assert ok is True
        assert msg is None
