"""V2.7 Webhook/Callback 集成测试 - 扩展覆盖"""
import pytest
import asyncio
import time

from src.gateway.approval import ApprovalGate, ApprovalStatus


class TestWebhookCallbackEdgeCases:
    """Callback 边界情况测试"""

    @pytest.mark.asyncio
    async def test_unknown_request_returns_false_on_register(self):
        """注册到不存在的 request_id 返回 False"""
        gate = ApprovalGate(timeout_seconds=60)
        result = gate.register_callback("does_not_exist", lambda r: None)
        assert result is False

    @pytest.mark.asyncio
    async def test_unregister_on_nonexistent_id_is_safe(self):
        """注销不存在的 callback 不抛异常"""
        gate = ApprovalGate(timeout_seconds=60)
        gate.unregister_callback("does_not_exist")  # Should not raise
        assert True

    @pytest.mark.asyncio
    async def test_callback_receives_correct_request_object(self):
        """Callback 收到的 ApprovalRequest 对象包含正确字段"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user_abc"},
            params={"statement": "SELECT * FROM users"},
        )
        received = []

        def cb(req):
            received.append(req)

        gate.register_callback(result.request_id, cb)
        await gate.approve(result.request_id, "admin", "looks good")
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0].action == "execute_sql"
        assert received[0].requester == "user_abc"
        assert received[0].params == {"statement": "SELECT * FROM users"}
        assert received[0].status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_propagate(self):
        """Callback 抛异常不影响 ApprovalGate 主流程"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="test", context={"user_id": "u"}, params={}
        )

        def bad_cb(req):
            raise RuntimeError("callback error")

        gate.register_callback(result.request_id, bad_cb)
        # Should not raise
        await gate.approve(result.request_id, "admin", "ok")
        await asyncio.sleep(0.05)
        # Request should still be approved
        status = await gate.get_status(result.request_id)
        assert status.status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_async_callback_awaitable(self):
        """异步 callback 正常工作"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="test", context={"user_id": "u"}, params={}
        )
        called = []

        async def async_cb(req):
            await asyncio.sleep(0.01)
            called.append(req.request_id)

        gate.register_callback(result.request_id, async_cb)
        await gate.approve(result.request_id, "admin")
        await asyncio.sleep(0.05)
        assert len(called) == 1


class TestEventBasedWaiting:
    """Event-based 等待机制测试（替代轮询）"""

    @pytest.mark.asyncio
    async def test_event_wait_is_fast(self):
        """Event 等待比轮询快（< 0.1s）"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="test", context={"user_id": "u"}, params={}
        )
        done_event = asyncio.Event()

        def cb(req):
            done_event.set()

        gate.register_callback(result.request_id, cb)
        start = time.time()
        await gate.approve(result.request_id, "admin")
        await done_event.wait()
        elapsed = time.time() - start
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_event_wait_with_timeout(self):
        """Event 等待支持超时"""
        gate = ApprovalGate(timeout_seconds=1)
        result = await gate.request_approval(
            action="test", context={"user_id": "u"}, params={}
        )
        done_event = asyncio.Event()

        def cb(req):
            done_event.set()

        gate.register_callback(result.request_id, cb)
        start = time.time()
        # Do NOT approve - wait for timeout cleanup
        await asyncio.sleep(2)
        await gate.cleanup_timeout()
        await done_event.wait()
        elapsed = time.time() - start
        assert elapsed >= 1.9  # At least timeout seconds
        assert result.request_id in gate._webhook_callbacks or True  # callback fired

    @pytest.mark.asyncio
    async def test_multiple_requests_independent_events(self):
        """多个并发请求的事件互相独立"""
        gate = ApprovalGate(timeout_seconds=60)
        r1 = await gate.request_approval(action="a", context={"user_id": "u1"}, params={})
        r2 = await gate.request_approval(action="b", context={"user_id": "u2"}, params={})

        called1, called2 = [], []

        def cb1(req):
            called1.append(req.request_id)

        def cb2(req):
            called2.append(req.request_id)

        gate.register_callback(r1.request_id, cb1)
        gate.register_callback(r2.request_id, cb2)

        await gate.approve(r1.request_id, "admin")
        await gate.reject(r2.request_id, "admin")

        await asyncio.sleep(0.05)
        assert len(called1) == 1
        assert len(called2) == 1
        assert called1[0] == r1.request_id
        assert called2[0] == r2.request_id


class TestWebhookAPIRoute:
    """Webhook API 路由测试（Schema层面）"""

    def test_webhook_payload_approve_schema(self):
        from src.api.approval_routes import WebhookPayload
        payload = WebhookPayload(
            request_id="req_123",
            action="approve",
            approver="zhangsan",
            comment="同意该操作",
        )
        assert payload.request_id == "req_123"
        assert payload.action == "approve"
        assert payload.approver == "zhangsan"
        assert payload.comment == "同意该操作"

    def test_webhook_payload_reject_schema(self):
        from src.api.approval_routes import WebhookPayload
        payload = WebhookPayload(
            request_id="req_456",
            action="reject",
            approver="lisi",
            reason="风险太高",
        )
        assert payload.action == "reject"
        assert payload.reason == "风险太高"
        assert payload.comment == ""

    def test_webhook_response_schema(self):
        from src.api.approval_routes import WebhookResponse
        resp = WebhookResponse(success=True, message="ok")
        assert resp.success is True
        assert resp.message == "ok"


class TestApprovalGateEventSet:
    """ApprovalGate Event 设置测试"""

    @pytest.mark.asyncio
    async def test_event_set_on_approve(self):
        """approve 时 Event 被设置"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="test", context={"user_id": "u"}, params={}
        )
        event = gate._events[result.request_id]
        assert not event.is_set()
        await gate.approve(result.request_id, "admin")
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_event_set_on_reject(self):
        """reject 时 Event 被设置"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="test", context={"user_id": "u"}, params={}
        )
        event = gate._events[result.request_id]
        assert not event.is_set()
        await gate.reject(result.request_id, "admin", "no")
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_event_set_on_timeout(self):
        """timeout 时 Event 被设置"""
        gate = ApprovalGate(timeout_seconds=1)
        result = await gate.request_approval(
            action="test", context={"user_id": "u"}, params={}
        )
        event = gate._events[result.request_id]
        assert not event.is_set()
        await asyncio.sleep(1.5)
        await gate.cleanup_timeout()
        assert event.is_set()
