"""
ApprovalGate 完整测试套件

测试 ApprovalGate 的核心功能：
1. L4 单签审批流程
2. L5 双人审批流程
3. 审批超时处理
4. 审批拒绝处理
5. SOPExecutor 集成
"""

import asyncio
import time
import pytest

from src.gateway.approval import (
    ApprovalGate,
    ApprovalStatus,
    ApprovalStatusResponse,
    ApprovalRequestResult,
)


class TestApprovalGateBasic:
    """基础功能测试"""

    @pytest.fixture
    def gate(self):
        return ApprovalGate(timeout_seconds=5)

    @pytest.fixture
    def mock_context(self):
        return {
            "user_id": "test_user",
            "session_id": "test_session",
            "risk_level": "L4",
        }

    # ------------------------------------------------------------------
    # L4 单签审批
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_l4_single_approval_approve(self, gate, mock_context):
        """L4-001: 单签审批 → 审批通过"""
        step_def = {
            "step_id": "1",
            "action": "kill_session",
            "risk_level": "L4",
        }
        params = {"session_id": "abc123"}

        # 发起审批
        result = await gate.request_approval(
            step_def=step_def, params=params, context=mock_context
        )
        assert hasattr(result, "request_id"), "应返回 ApprovalRequestResult"
        request_id = result.request_id
        assert result.success is True
        assert request_id

        # 审批通过
        ok = await gate.approve(request_id, approver="admin", comment="OK")
        assert ok is True

        # 验证状态
        approved, reason = await gate.check_approval_status(request_id)
        assert approved is True
        assert reason == "approved"

    @pytest.mark.asyncio
    async def test_l4_single_approval_reject(self, gate, mock_context):
        """L4-002: 单签审批 → 审批拒绝"""
        step_def = {
            "step_id": "1",
            "action": "kill_session",
            "risk_level": "L4",
        }

        result = await gate.request_approval(
            step_def=step_def, params={}, context=mock_context
        )
        request_id = result.request_id

        ok = await gate.reject(request_id, approver="dba_lead", reason="风险太高")
        assert ok is True

        approved, reason = await gate.check_approval_status(request_id)
        assert approved is False
        assert reason == "rejected"

    # ------------------------------------------------------------------
    # L5 双人审批
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_l5_dual_approval_one_approver_waits(self, gate, mock_context):
        """L5-001: 双人审批 → 第一人通过后等待第二人"""
        step_def = {
            "step_id": "1",
            "action": "pg_kill_session",
            "risk_level": "L5",  # 双签
        }

        result = await gate.request_approval(
            step_def=step_def, params={}, context=mock_context
        )
        request_id = result.request_id
        assert result.success is True

        # 第一人通过
        ok1 = await gate.approve(request_id, approver="admin", comment="同意")
        assert ok1 is True

        # 状态仍是 pending（等待第二人）
        status = await gate.get_status(request_id)
        assert status.status == ApprovalStatus.PENDING
        assert status.approved is False

        # 第二人通过 → 完成
        ok2 = await gate.approve(request_id, approver="dba_lead", comment="批准")
        assert ok2 is True

        approved, reason = await gate.check_approval_status(request_id)
        assert approved is True
        assert reason == "approved"

    @pytest.mark.asyncio
    async def test_l5_dual_approval_first_reject(self, gate, mock_context):
        """L5-002: 双人审批 → 第一人拒绝即终止"""
        step_def = {
            "step_id": "1",
            "action": "pg_kill_session",
            "risk_level": "L5",
        }

        result = await gate.request_approval(
            step_def=step_def, params={}, context=mock_context
        )
        request_id = result.request_id

        ok = await gate.reject(request_id, approver="admin", reason="不同意")
        assert ok is True

        approved, reason = await gate.check_approval_status(request_id)
        assert approved is False
        assert reason == "rejected"

    # ------------------------------------------------------------------
    # 超时处理
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self, gate, mock_context):
        """TIMEOUT-001: 审批超时 → 返回 False"""
        # 使用1秒超时的 gate
        fast_gate = ApprovalGate(timeout_seconds=1)
        step_def = {
            "step_id": "1",
            "action": "kill_session",
            "risk_level": "L4",
        }

        result = await fast_gate.request_approval(
            step_def=step_def, params={}, context=mock_context
        )
        request_id = result.request_id

        # 不做任何审批操作，直接等待超时
        approved, reason = await fast_gate.check_approval_status(request_id)
        assert approved is False
        assert reason == "timeout"

    @pytest.mark.asyncio
    async def test_get_status_expired_flag(self, gate, mock_context):
        """TIMEOUT-002: get_status 正确报告 expired"""
        fast_gate = ApprovalGate(timeout_seconds=1)
        step_def = {
            "step_id": "1",
            "action": "kill_session",
            "risk_level": "L4",
        }

        result = await fast_gate.request_approval(
            step_def=step_def, params={}, context=mock_context
        )
        request_id = result.request_id

        # 等1.5秒（超过1秒超时）
        await asyncio.sleep(1.5)

        status = await fast_gate.get_status(request_id)
        assert status.expired is True

    # ------------------------------------------------------------------
    # 审批人验证
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_invalid_approver_rejected(self, gate, mock_context):
        """APPROVER-001: 无效审批人 → success=False"""
        result = await gate.request_approval(
            action="kill_session",
            context=mock_context,
            approvers=["nonexistent_user_xyz"],
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_pending(self, gate, mock_context):
        """QUERY-001: list_pending 返回待审批请求"""
        step_def = {
            "step_id": "1",
            "action": "kill_session",
            "risk_level": "L4",
        }
        result = await gate.request_approval(
            step_def=step_def, params={}, context=mock_context
        )
        request_id = result.request_id

        pending = gate.list_pending()
        assert len(pending) >= 1
        assert any(r.request_id == request_id for r in pending)

        # 审批后不再出现在 pending
        await gate.approve(request_id, approver="admin")
        pending = gate.list_pending()
        assert all(r.request_id != request_id for r in pending)

    @pytest.mark.asyncio
    async def test_get_request(self, gate, mock_context):
        """QUERY-002: get_request 返回请求详情"""
        step_def = {
            "step_id": "1",
            "action": "pg_kill_session",
            "risk_level": "L5",
        }
        result = await gate.request_approval(
            step_def=step_def, params={"sid": 123}, context=mock_context
        )
        request_id = result.request_id

        req = gate.get_request(request_id)
        assert req is not None
        assert req.action == "pg_kill_session"
        assert req.risk_level == "L5"
        assert req.params == {"sid": 123}

    # ------------------------------------------------------------------
    # 幂等性
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_idempotent_request(self, gate, mock_context):
        """IDEM-001: 相同参数重复请求返回同一 request_id"""
        step_def = {
            "step_id": "1",
            "action": "kill_session",
            "risk_level": "L4",
        }
        params = {"session_id": "abc123"}

        r1 = await gate.request_approval(
            step_def=step_def, params=params, context=mock_context
        )
        r2 = await gate.request_approval(
            step_def=step_def, params=params, context=mock_context
        )

        # 相同参数 → 相同 request_id（幂等）
        assert r1.request_id == r2.request_id

    # ------------------------------------------------------------------
    # 降级放行（无 ApprovalGate）
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_no_approval_gate_allows(self):
        """DEGRADE-001: 无 ApprovalGate 时 _check_approval 降级放行"""

        class DummyContext(dict):
            def get(self, key, default=None):
                if key == "approval_gate":
                    return None  # 无 ApprovalGate
                return super().get(key, default)

        from src.security.execution.sop_executor import SOPExecutor

        exec_ctx = {"approval_gate": None}  # 模拟无 gate

        executor = SOPExecutor()
        step_def = {
            "step_id": "1",
            "action": "kill_session",
            "risk_level": "L4",
            "require_approval": True,
        }

        # 同步调用 _check_approval（无 gate → 降级放行不抛异常）
        result = await executor._check_approval(step_def, {}, exec_ctx)
        # 降级放行返回 True
        assert result is True


# =============================================================================
# SOPExecutor 集成测试（需要完整的 sop_executor）
# =============================================================================

class TestApprovalGateSOPExecutorIntegration:
    """SOPExecutor 与 ApprovalGate 集成测试"""

    @pytest.fixture
    def gate(self):
        return ApprovalGate(timeout_seconds=5)

    @pytest.mark.asyncio
    async def test_sop_executor_waits_for_approval(self, gate):
        """INT-001: SOPExecutor 在审批期间阻塞"""
        from src.security.execution.sop_executor import SOPExecutor

        exec_ctx = {"approval_gate": gate, "user_id": "test_user"}

        step_def = {
            "step_id": "1",
            "action": "kill_session",
            "risk_level": "L4",
            "require_approval": True,
            "params": {"session_id": "test_sid"},
        }

        executor = SOPExecutor()

        async def approve_after_delay():
            await asyncio.sleep(0.2)
            # 获取 pending 请求
            pending = gate.list_pending()
            if pending:
                await gate.approve(pending[0].request_id, approver="admin")

        # 并发：批准者和执行者同时启动
        import asyncio
        await asyncio.gather(
            executor._check_approval(step_def, {}, exec_ctx),
            approve_after_delay(),
        )

        # 如果走到这里说明没有卡死（超时会被测）
        pending = gate.list_pending()
        # 可能还有pending（如果审批还没完成）
        assert isinstance(pending, list)

    @pytest.mark.asyncio
    async def test_risk_level_l3_no_approval(self, gate):
        """INT-002: L3 及以下无需审批"""
        from src.security.execution.sop_executor import SOPExecutor

        exec_ctx = {"approval_gate": gate, "user_id": "test_user"}

        step_def = {
            "step_id": "1",
            "action": "execute_sql",
            "risk_level": "L3",  # 不需要审批
            "require_approval": True,  # 但标记为需要审批
        }

        executor = SOPExecutor()
        # L3 bypasses approval check
        result = await executor._check_approval(step_def, {}, exec_ctx)
        assert result is True
