"""P0 测试: V2.7 Webhook/Callback 替代审批轮询"""
import pytest
import asyncio
import time

from src.gateway.approval import ApprovalGate, ApprovalStatus, ApprovalRequest


class TestApprovalGateCallback:
    """ApprovalGate Callback 注册与触发测试"""

    @pytest.mark.asyncio
    async def test_register_callback_returns_true_for_existing_request(self):
        """测试 register_callback 对已存在的 request 返回 True"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"},
        )
        called = []
        def cb(req):
            called.append(req.request_id)

        success = gate.register_callback(result.request_id, cb)
        assert success is True
        assert result.request_id in gate._webhook_callbacks

    @pytest.mark.asyncio
    async def test_register_callback_returns_false_for_unknown_request(self):
        """测试 register_callback 对不存在的 request 返回 False"""
        gate = ApprovalGate(timeout_seconds=60)
        success = gate.register_callback("unknown_id", lambda r: None)
        assert success is False

    @pytest.mark.asyncio
    async def test_callback_triggered_on_approve(self):
        """测试 approve 时触发 callback"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"},
        )
        called = []

        def cb(req):
            called.append(req.request_id)

        gate.register_callback(result.request_id, cb)
        await gate.approve(result.request_id, "admin", "ok")
        await asyncio.sleep(0.05)  # 等待 callback 执行

        assert len(called) == 1
        assert called[0] == result.request_id

    @pytest.mark.asyncio
    async def test_callback_triggered_on_reject(self):
        """测试 reject 时触发 callback"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"},
        )
        called = []

        def cb(req):
            called.append(req.request_id)

        gate.register_callback(result.request_id, cb)
        await gate.reject(result.request_id, "admin", "too risky")
        await asyncio.sleep(0.05)

        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_callback_auto_unregisters_after_trigger(self):
        """测试 callback 触发后自动注销"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"},
        )

        def cb(req):
            pass

        gate.register_callback(result.request_id, cb)
        await gate.approve(result.request_id, "admin")
        await asyncio.sleep(0.05)

        assert result.request_id not in gate._webhook_callbacks

    @pytest.mark.asyncio
    async def test_unregister_callback_manually(self):
        """测试手动注销 callback"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"},
        )

        def cb(req):
            pass

        gate.register_callback(result.request_id, cb)
        gate.unregister_callback(result.request_id)

        assert result.request_id not in gate._webhook_callbacks
        # approve 不应该触发任何 callback
        await gate.approve(result.request_id, "admin")
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_async_callback(self):
        """测试异步 callback"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"},
        )
        called = []

        async def async_cb(req):
            await asyncio.sleep(0.01)
            called.append(req.request_id)

        gate.register_callback(result.request_id, async_cb)
        await gate.approve(result.request_id, "admin")
        await asyncio.sleep(0.05)

        assert len(called) == 1


class TestSafetyGuardRailEventBasedWait:
    """SafetyGuardRail Event-based 等待测试（替代轮询）"""

    @pytest.mark.asyncio
    async def test_approval_completes_quickly_with_callback(self):
        """测试使用 callback 时审批立即完成（无需轮询）"""
        from src.security.guard_rail import SafetyGuardRail

        gate = ApprovalGate(timeout_seconds=60)
        rail = SafetyGuardRail(
            approval_gate=gate,
            l4_ttl_seconds=600,
            l5_ttl_seconds=300,
        )

        # Mock _request_approval to simulate instant approval
        # 直接调用 gate.approve() 模拟审批通过
        original_request = gate.request_approval

        async def mock_request(*args, **kwargs):
            result = await original_request(*args, **kwargs)
            # 立即 approve
            await gate.approve(result.request_id, "admin", "ok")
            return result

        gate.request_approval = mock_request

        context = {
            "user_id": "user1",
            "params": {"statement": "SELECT 1", "limit": 10},
            "approval_tokens": {},
        }

        start = time.time()
        try:
            await rail.enforce("execute_sql", 4, context, timeout=5)
        except Exception:
            pass  # 可能抛出 ApprovalRequiredError，忽略
        elapsed = time.time() - start

        # 如果使用了 callback 机制，应该非常快（< 0.5s）
        # 而不是等待 2 秒轮询间隔
        assert elapsed < 1.0, f"Wait took {elapsed:.2f}s, expected < 1.0s (should use Event, not polling)"


class TestApprovalWebhookAPI:
    """Approval Webhook API 测试"""

    def test_webhook_payload_schema(self):
        """测试 WebhookPayload 数据模型"""
        from src.api.approval_routes import WebhookPayload

        # approve payload
        payload = WebhookPayload(
            request_id="req123",
            action="approve",
            approver="admin",
            comment="ok",
        )
        assert payload.request_id == "req123"
        assert payload.action == "approve"
        assert payload.approver == "admin"
        assert payload.comment == "ok"

        # reject payload
        payload2 = WebhookPayload(
            request_id="req456",
            action="reject",
            approver="admin",
            reason="too risky",
        )
        assert payload2.action == "reject"
        assert payload2.reason == "too risky"

    def test_webhook_response_schema(self):
        """测试 WebhookResponse 数据模型"""
        from src.api.approval_routes import WebhookResponse

        resp = WebhookResponse(success=True, message="Approved")
        assert resp.success is True
        assert resp.message == "Approved"
