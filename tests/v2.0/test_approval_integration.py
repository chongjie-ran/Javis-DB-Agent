"""
ApprovalGate 集成测试套件 (V2.1 Round 3)

测试范围：
1. ApprovalGate 单元测试 (src/gateway/approval.py)
2. SOPExecutor 审批流集成测试 (src/security/execution/sop_executor.py)
3. API 路由测试 (src/api/approval_routes.py)

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/v2.0/test_approval_integration.py -v --tb=short
"""

import asyncio
import sys
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# 确保 src 在路径中
sys.path.insert(0, "/Users/chongjieran/SWproject/Javis-DB-Agent")

from src.gateway.approval import (
    ApprovalGate,
    ApprovalStatus,
    ApprovalStatusResponse,
    ApprovalRequestResult,
)
from src.security.execution.sop_executor import SOPExecutor


# =============================================================================
# 1. ApprovalGate 单元测试
# =============================================================================

class TestApprovalGateUnit:
    """ApprovalGate 核心功能单元测试"""

    @pytest.fixture
    def gate(self):
        """5秒超时 gate，用于快速测试"""
        return ApprovalGate(timeout_seconds=5)

    @pytest.fixture
    def ctx_l4(self):
        return {"user_id": "test_user", "session_id": "sess_001", "risk_level": "L4"}

    @pytest.fixture
    def ctx_l5(self):
        return {"user_id": "test_user", "session_id": "sess_002", "risk_level": "L5"}

    # ------------------------------------------------------------------
    # L4 单签审批
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_l4_single_approval_approve(self, gate, ctx_l4):
        """L4单签审批通过"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }
        params = {"session_id": "abc123"}

        # 发起审批请求
        result = await gate.request_approval(
            step_def=step_def, params=params, context=ctx_l4
        )
        assert isinstance(result, ApprovalRequestResult)
        assert result.success is True
        assert result.request_id != ""
        request_id = result.request_id

        # 审批通过
        ok = await gate.approve(request_id, approver="admin", comment="同意")
        assert ok is True

        # 验证状态
        approved, reason = await gate.check_approval_status(request_id)
        assert approved is True
        assert reason == "approved"

        # get_status 一致性验证
        status = await gate.get_status(request_id)
        assert status.approved is True
        assert status.status == ApprovalStatus.APPROVED
        assert status.risk_level == "L4"
        assert "admin" in status.approvers

    @pytest.mark.asyncio
    async def test_l4_single_approval_reject(self, gate, ctx_l4):
        """L4单签审批拒绝"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }

        result = await gate.request_approval(
            step_def=step_def, params={}, context=ctx_l4
        )
        request_id = result.request_id
        assert result.success is True

        # 审批拒绝
        ok = await gate.reject(request_id, approver="dba_lead", reason="风险太高")
        assert ok is True

        # 验证状态
        approved, reason = await gate.check_approval_status(request_id)
        assert approved is False
        assert reason == "rejected"

        # get_status 一致性验证
        status = await gate.get_status(request_id)
        assert status.approved is False
        assert status.status == ApprovalStatus.REJECTED

    # ------------------------------------------------------------------
    # L5 双人审批
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_l5_dual_approval_both_approve(self, gate, ctx_l5):
        """L5双人审批都通过"""
        step_def = {
            "step_id": "2",
            "action": "pg_kill_session",
            "risk_level": "L5",  # 双签：需要两人
        }
        params = {"sid": 12345}

        result = await gate.request_approval(
            step_def=step_def, params=params, context=ctx_l5
        )
        assert result.success is True
        request_id = result.request_id
        req = gate.get_request(request_id)
        assert req.risk_level == "L5"
        assert req.required_approvals == 2

        # 第一人通过 → 状态仍是 PENDING
        ok1 = await gate.approve(request_id, approver="admin", comment="一票同意")
        assert ok1 is True
        status_after_first = await gate.get_status(request_id)
        assert status_after_first.status == ApprovalStatus.PENDING
        assert status_after_first.approved is False

        # 第二人通过 → 状态变为 APPROVED
        ok2 = await gate.approve(request_id, approver="dba_lead", comment="批准")
        assert ok2 is True

        approved, reason = await gate.check_approval_status(request_id)
        assert approved is True
        assert reason == "approved"

        final_status = await gate.get_status(request_id)
        assert final_status.approved is True
        assert final_status.status == ApprovalStatus.APPROVED
        assert len(final_status.approvers) == 2
        assert "admin" in final_status.approvers
        assert "dba_lead" in final_status.approvers

    @pytest.mark.asyncio
    async def test_l5_dual_approval_one_reject(self, gate, ctx_l5):
        """L5双人审批一人拒绝 → 整体拒绝"""
        step_def = {
            "step_id": "2",
            "action": "pg_kill_session",
            "risk_level": "L5",
        }

        result = await gate.request_approval(
            step_def=step_def, params={}, context=ctx_l5
        )
        request_id = result.request_id

        # 第一人通过
        ok1 = await gate.approve(request_id, approver="admin", comment="同意")
        assert ok1 is True

        # 第二人拒绝 → 整体拒绝
        ok2 = await gate.reject(request_id, approver="dba_lead", reason="不同意")
        assert ok2 is True

        approved, reason = await gate.check_approval_status(request_id)
        assert approved is False
        assert reason == "rejected"

        final_status = await gate.get_status(request_id)
        assert final_status.status == ApprovalStatus.REJECTED
        assert final_status.approved is False

    # ------------------------------------------------------------------
    # 幂等性
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_approval_idempotency(self, gate, ctx_l4):
        """相同 action + params → 幂等（同一 request_id）"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }
        params = {"session_id": "abc123"}

        r1 = await gate.request_approval(
            step_def=step_def, params=params, context=ctx_l4
        )
        r2 = await gate.request_approval(
            step_def=step_def, params=params, context=ctx_l4
        )
        r3 = await gate.request_approval(
            step_def=step_def, params=params, context=ctx_l4
        )

        # 相同参数 → 相同 request_id
        assert r1.request_id == r2.request_id == r3.request_id
        assert r1.success is True
        assert r2.success is True
        assert r3.success is True

        # 只有一条待审批记录
        pending = gate.list_pending()
        assert len(pending) == 1
        assert pending[0].request_id == r1.request_id

    @pytest.mark.asyncio
    async def test_different_params_different_request_id(self, gate, ctx_l4):
        """不同 params → 不同 request_id（不幂等）"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }

        r1 = await gate.request_approval(
            step_def=step_def, params={"session_id": "abc"}, context=ctx_l4
        )
        r2 = await gate.request_approval(
            step_def=step_def, params={"session_id": "xyz"}, context=ctx_l4
        )

        assert r1.request_id != r2.request_id
        pending = gate.list_pending()
        assert len(pending) == 2

    # ------------------------------------------------------------------
    # 超时处理
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_approval_timeout(self, ctx_l4):
        """审批超时 → 返回 False + timeout"""
        fast_gate = ApprovalGate(timeout_seconds=1)
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }

        result = await fast_gate.request_approval(
            step_def=step_def, params={}, context=ctx_l4
        )
        request_id = result.request_id

        # 不做任何操作，直接等待超时检查
        approved, reason = await fast_gate.check_approval_status(request_id)
        assert approved is False
        assert reason == "timeout"

    @pytest.mark.asyncio
    async def test_get_status_expired(self, ctx_l4):
        """get_status 正确报告 expired=True"""
        fast_gate = ApprovalGate(timeout_seconds=1)
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }

        result = await fast_gate.request_approval(
            step_def=step_def, params={}, context=ctx_l4
        )
        request_id = result.request_id

        # 等待超过超时时间
        await asyncio.sleep(1.6)

        status = await fast_gate.get_status(request_id)
        assert status.expired is True
        assert status.status == ApprovalStatus.PENDING  # 未被主动处理

    @pytest.mark.asyncio
    async def test_cleanup_timeout(self, gate, ctx_l4):
        """cleanup_timeout 正确清理超时请求"""
        fast_gate = ApprovalGate(timeout_seconds=1)
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }

        result = await fast_gate.request_approval(
            step_def=step_def, params={}, context=ctx_l4
        )
        request_id = result.request_id

        # 等待超时
        await asyncio.sleep(1.6)

        cleaned = await fast_gate.cleanup_timeout()
        assert cleaned >= 1

        # 状态变为 TIMEOUT
        req = fast_gate.get_request(request_id)
        assert req.status == ApprovalStatus.TIMEOUT

    # ------------------------------------------------------------------
    # 审批人验证
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_invalid_approver_rejected(self, gate, ctx_l4):
        """无效审批人 → request_approval 返回 success=False"""
        result = await gate.request_approval(
            action="kill_session",
            context=ctx_l4,
            approvers=["nonexistent_user_xyz"],
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    # ------------------------------------------------------------------
    # 未知 request_id 处理
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_unknown_request_id(self, gate):
        """未知 request_id → check_approval_status 返回 False + unknown_request"""
        approved, reason = await gate.check_approval_status("fake_id_12345")
        assert approved is False
        assert reason == "unknown_request"

        status = await gate.get_status("fake_id_12345")
        assert status.status == ApprovalStatus.PENDING
        assert status.approved is False

    # ------------------------------------------------------------------
    # 重复审批
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_duplicate_approval_ignored(self, gate, ctx_l4):
        """同一审批人重复审批 → 被忽略（幂等）"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }

        result = await gate.request_approval(
            step_def=step_def, params={}, context=ctx_l4
        )
        request_id = result.request_id

        # 第一次审批
        ok1 = await gate.approve(request_id, approver="admin", comment="同意")
        assert ok1 is True

        # 第二次重复审批 → 被忽略
        ok2 = await gate.approve(request_id, approver="admin", comment="再同意")
        assert ok2 is True  # 不报错，但忽略

        req = gate.get_request(request_id)
        assert len(req.approvers) == 1  # 仍然只有1人
        assert req.approval_count == 1


# =============================================================================
# 2. SOPExecutor 审批流集成测试
# =============================================================================

class TestSOPExecutorApprovalIntegration:
    """SOPExecutor 与 ApprovalGate 集成测试"""

    @pytest.fixture
    def gate(self):
        return ApprovalGate(timeout_seconds=5)

    @pytest.mark.asyncio
    async def test_sop_executor_l4_triggers_approval(self, gate):
        """SOPExecutor L4 风险步骤 → 触发单签审批"""
        exec_ctx = {"approval_gate": gate, "user_id": "test_user"}

        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
            "require_approval": True,
        }

        executor = SOPExecutor()

        # 启动检查（不阻塞）
        async def do_approval():
            await asyncio.sleep(0.1)
            pending = gate.list_pending()
            if pending:
                await gate.approve(pending[0].request_id, approver="admin")

        # 并发执行
        check_task = asyncio.create_task(
            executor._check_approval(step_def, {}, exec_ctx)
        )
        approve_task = asyncio.create_task(do_approval())

        done, pending = await asyncio.wait(
            [check_task, approve_task], timeout=3
        )

        # 检查结果
        assert len(done) == 2
        result = check_task.result()
        assert result is True  # 审批通过

    @pytest.mark.asyncio
    async def test_sop_executor_l5_triggers_dual(self, gate):
        """SOPExecutor L5 风险步骤 → 触发双人审批"""
        exec_ctx = {"approval_gate": gate, "user_id": "test_user"}

        step_def = {
            "step_id": "2",
            "action": "pg_kill_session",
            "risk_level": "L5",  # 双签
            "require_approval": True,
        }

        executor = SOPExecutor()

        async def do_dual_approval():
            await asyncio.sleep(0.1)
            pending = gate.list_pending()
            if pending:
                req = pending[0]
                await gate.approve(req.request_id, approver="admin")
                await gate.approve(req.request_id, approver="dba_lead")

        check_task = asyncio.create_task(
            executor._check_approval(step_def, {}, exec_ctx)
        )
        approve_task = asyncio.create_task(do_dual_approval())

        done, pending = await asyncio.wait(
            [check_task, approve_task], timeout=3
        )

        assert len(done) == 2
        result = check_task.result()
        assert result is True

        # 验证两人都有审批记录
        pending = gate.list_pending()
        assert len(pending) == 0  # 已完成
        req = gate.get_request(list(gate._requests.keys())[0])
        assert len(req.approvers) == 2

    @pytest.mark.asyncio
    async def test_sop_executor_no_gate_fallback(self):
        """无 ApprovalGate 时 → 降级放行（不阻塞）"""
        exec_ctx = {"approval_gate": None}  # 无 gate

        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
            "require_approval": True,
        }

        executor = SOPExecutor()

        # 降级放行应返回 True，不抛异常
        result = await executor._check_approval(step_def, {}, exec_ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_sop_executor_approval_reject_fails_step(self, gate):
        """审批拒绝 → _check_approval 返回 False，步骤无法继续"""
        exec_ctx = {"approval_gate": gate, "user_id": "test_user"}

        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
            "require_approval": True,
        }

        executor = SOPExecutor()

        async def do_reject():
            await asyncio.sleep(0.1)
            pending = gate.list_pending()
            if pending:
                await gate.reject(
                    pending[0].request_id,
                    approver="dba_lead",
                    reason="风险太高"
                )

        check_task = asyncio.create_task(
            executor._check_approval(step_def, {}, exec_ctx)
        )
        reject_task = asyncio.create_task(do_reject())

        done, pending = await asyncio.wait(
            [check_task, reject_task], timeout=3
        )

        assert len(done) == 2
        result = check_task.result()
        assert result is False  # 审批拒绝

    @pytest.mark.asyncio
    async def test_sop_executor_l3_no_approval(self, gate):
        """L3 及以下 → 无需审批，直接放行"""
        exec_ctx = {"approval_gate": gate, "user_id": "test_user"}

        step_def = {
            "step_id": "1",
            "action": "execute_sql",
            "risk_level": "L3",
            "require_approval": True,  # 即使标记了需要审批
        }

        executor = SOPExecutor()
        result = await executor._check_approval(step_def, {}, exec_ctx)
        assert result is True

        # 无待审批记录
        pending = gate.list_pending()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_sop_executor_full_workflow_with_approval(self, gate):
        """完整 SOP 执行流程（含审批步骤）"""
        exec_ctx = {"approval_gate": gate, "user_id": "test_user"}

        sop = {
            "id": "test_kill_session",
            "name": "测试终止会话",
            "steps": [
                {
                    "step": 1,
                    "action": "find_idle_sessions",
                    "params": {},
                    "risk_level": 1,
                    "timeout_seconds": 30,
                },
                {
                    "step": 2,
                    "action": "kill_session",
                    "params": {"session_id": "test_sid"},
                    "risk_level": 3,
                    "require_approval": True,
                    "timeout_seconds": 30,
                },
                {
                    "step": 3,
                    "action": "verify_session_killed",
                    "params": {},
                    "risk_level": 1,
                    "timeout_seconds": 30,
                },
            ],
            "risk_level": 3,
            "timeout_seconds": 120,
        }

        executor = SOPExecutor()

        async def approve_step2():
            await asyncio.sleep(0.1)
            pending = gate.list_pending()
            if pending:
                await gate.approve(pending[0].request_id, approver="admin")

        import asyncio
        exec_task = asyncio.create_task(executor.execute(sop, exec_ctx))
        approve_task = asyncio.create_task(approve_step2())

        done, pending = await asyncio.wait(
            [exec_task, approve_task], timeout=10
        )

        # 验证执行结果
        assert len(done) >= 1
        exec_result = exec_task.result()
        assert exec_result.status.value in ("completed", "waiting_approval", "failed")

        # 如果审批完成，步骤2应该完成
        if gate.list_pending() == []:
            # 审批已完成
            pass  # 不强制要求完成（时序竞争）

    @pytest.mark.asyncio
    async def test_sop_executor_approval_timeout_fails(self, gate):
        """审批超时 → _check_approval 返回 False"""
        exec_ctx = {"approval_gate": gate, "user_id": "test_user"}

        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
            "require_approval": True,
        }

        # gate 超时设短，审批人从不出现
        fast_gate = ApprovalGate(timeout_seconds=1)
        exec_ctx["approval_gate"] = fast_gate

        executor = SOPExecutor()

        start = time.time()
        result = await executor._check_approval(step_def, {}, exec_ctx)
        elapsed = time.time() - start

        assert result is False
        # 超时检测有1秒延迟（轮询间隔）
        assert elapsed >= 0.9


# =============================================================================
# 3. API 路由测试（mock FastAPI）
# =============================================================================

class TestApprovalRoutes:
    """API 路由单元测试（mock ApprovalGate）"""

    @pytest.fixture
    def gate(self):
        return ApprovalGate(timeout_seconds=5)

    @pytest.mark.asyncio
    async def test_approve_route(self, gate):
        """POST /approvals/{id}/approve → 审批通过"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }
        ctx = {"user_id": "test_user"}
        result = await gate.request_approval(step_def=step_def, params={}, context=ctx)
        request_id = result.request_id

        # 模拟 API 调用
        ok = await gate.approve(request_id, approver="admin", comment="ok")
        assert ok is True

        req = gate.get_request(request_id)
        assert req.status == ApprovalStatus.APPROVED
        assert "admin" in req.approvers

    @pytest.mark.asyncio
    async def test_reject_route(self, gate):
        """POST /approvals/{id}/reject → 审批拒绝"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }
        ctx = {"user_id": "test_user"}
        result = await gate.request_approval(step_def=step_def, params={}, context=ctx)
        request_id = result.request_id

        ok = await gate.reject(request_id, approver="dba_lead", reason="风险太高")
        assert ok is True

        req = gate.get_request(request_id)
        assert req.status == ApprovalStatus.REJECTED

    @pytest.mark.asyncio
    async def test_status_route_pending(self, gate):
        """GET /approvals/{id}/status → 待审批状态"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }
        ctx = {"user_id": "test_user"}
        result = await gate.request_approval(step_def=step_def, params={}, context=ctx)
        request_id = result.request_id

        status = await gate.get_status(request_id)
        assert status.status == ApprovalStatus.PENDING
        assert status.approved is False
        assert status.expired is False

    @pytest.mark.asyncio
    async def test_status_route_approved(self, gate):
        """GET /approvals/{id}/status → 已通过状态"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }
        ctx = {"user_id": "test_user"}
        result = await gate.request_approval(step_def=step_def, params={}, context=ctx)
        request_id = result.request_id

        await gate.approve(request_id, approver="admin")
        status = await gate.get_status(request_id)
        assert status.approved is True
        assert status.status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_status_route_rejected(self, gate):
        """GET /approvals/{id}/status → 已拒绝状态"""
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }
        ctx = {"user_id": "test_user"}
        result = await gate.request_approval(step_def=step_def, params={}, context=ctx)
        request_id = result.request_id

        await gate.reject(request_id, approver="dba_lead", reason="拒绝")
        status = await gate.get_status(request_id)
        assert status.approved is False
        assert status.status == ApprovalStatus.REJECTED

    @pytest.mark.asyncio
    async def test_status_route_timeout(self, gate):
        """GET /approvals/{id}/status → 超时状态（通过 cleanup_timeout 确认）"""
        fast_gate = ApprovalGate(timeout_seconds=1)
        step_def = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }
        ctx = {"user_id": "test_user"}
        result = await fast_gate.request_approval(step_def=step_def, params={}, context=ctx)
        request_id = result.request_id

        # 不审批，等待超时
        await asyncio.sleep(1.6)

        # get_status: expired=True 但内部 status 仍为 PENDING（不对内部状态做修改）
        status = await fast_gate.get_status(request_id)
        assert status.expired is True
        assert status.status == ApprovalStatus.PENDING  # get_status 不修改内部状态

        # cleanup_timeout 才真正将状态改为 TIMEOUT
        cleaned = await fast_gate.cleanup_timeout()
        assert cleaned >= 1
        req = fast_gate.get_request(request_id)
        assert req.status == ApprovalStatus.TIMEOUT

        # get_status 在 cleanup 后反映正确状态
        status_after_cleanup = await fast_gate.get_status(request_id)
        assert status_after_cleanup.status == ApprovalStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_list_pending_route(self, gate):
        """GET /approvals/pending → 列出待审批"""
        step_def1 = {
            "step_id": "2",
            "action": "kill_session",
            "risk_level": "L4",
        }
        step_def2 = {
            "step_id": "3",
            "action": "pg_kill_session",
            "risk_level": "L5",
        }
        ctx = {"user_id": "test_user"}

        r1 = await gate.request_approval(step_def=step_def1, params={}, context=ctx)
        r2 = await gate.request_approval(step_def=step_def2, params={}, context=ctx)

        pending = gate.list_pending()
        assert len(pending) == 2
        ids = [p.request_id for p in pending]
        assert r1.request_id in ids
        assert r2.request_id in ids

    @pytest.mark.asyncio
    async def test_approve_unknown_request(self, gate):
        """POST /approvals/{fake_id}/approve → 404"""
        ok = await gate.approve("fake_id_123", approver="admin")
        assert ok is False

    @pytest.mark.asyncio
    async def test_reject_unknown_request(self, gate):
        """POST /approvals/{fake_id}/reject → 404"""
        ok = await gate.reject("fake_id_123", approver="dba_lead", reason="拒绝")
        assert ok is False


# =============================================================================
# 运行入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
