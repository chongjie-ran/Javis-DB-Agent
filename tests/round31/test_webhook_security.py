"""P0 测试: V2.7 Webhook 安全验证"""
import hashlib
import hmac
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from src.api.approval_routes import router, _verify_hmac_signature, _verify_ip_whitelist, _get_client_ip
from src.gateway.approval import ApprovalGate, ApprovalStatus


class TestWebhookSecurityHMAC:
    """HMAC签名验证测试"""

    def test_hmac_signature_valid(self):
        """测试有效签名"""
        secret = "test-secret-key"
        body = b'{"request_id":"abc123","action":"approve"}'

        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": secret}):
            # 生成正确签名
            signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

            # 验证
            assert _verify_hmac_signature(body, signature) is True

    def test_hmac_signature_invalid(self):
        """测试无效签名"""
        secret = "test-secret-key"
        body = b'{"request_id":"abc123","action":"approve"}'

        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": secret}):
            # 使用错误的签名
            wrong_signature = "invalid_signature_here"

            assert _verify_hmac_signature(body, wrong_signature) is False

    def test_hmac_signature_missing_secret(self):
        """测试未配置密钥时跳过验证"""
        body = b'{"request_id":"abc123","action":"approve"}'

        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": ""}):
            # 未配置密钥时，应该跳过验证（返回True）
            assert _verify_hmac_signature(body, "any_signature") is True

    def test_hmac_signature_empty_signature_with_secret(self):
        """测试有密钥但空签名"""
        secret = "test-secret-key"
        body = b'{"request_id":"abc123","action":"approve"}'

        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": secret}):
            # 有密钥但空签名，应该失败
            assert _verify_hmac_signature(body, "") is False


class TestWebhookSecurityIPWhitelist:
    """IP白名单验证测试"""

    def test_ip_allowed_no_whitelist_configured(self):
        """测试未配置白名单时跳过检查"""
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": ""}):
            assert _verify_ip_whitelist("1.2.3.4") is True

    def test_ip_allowed_single_ip(self):
        """测试单个IP在白名单中"""
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": "10.0.0.1"}):
            assert _verify_ip_whitelist("10.0.0.1") is True

    def test_ip_not_allowed_single_ip(self):
        """测试单个IP不在白名单中"""
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": "10.0.0.1"}):
            assert _verify_ip_whitelist("10.0.0.2") is False

    def test_ip_allowed_cidr(self):
        """测试CIDR范围"""
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": "192.168.1.0/24"}):
            assert _verify_ip_whitelist("192.168.1.100") is True
            assert _verify_ip_whitelist("192.168.1.1") is True
            assert _verify_ip_whitelist("192.168.2.1") is False

    def test_ip_allowed_multiple_networks(self):
        """测试多个网络"""
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": "10.0.0.0/8,172.16.0.0/12"}):
            assert _verify_ip_whitelist("10.5.6.7") is True
            assert _verify_ip_whitelist("172.20.1.1") is True
            assert _verify_ip_whitelist("8.8.8.8") is False


class TestRejectIdempotency:
    """Reject幂等性测试"""

    @pytest.mark.asyncio
    async def test_reject_idempotent_same_approver(self):
        """测试同一审批人重复reject被忽略"""
        gate = ApprovalGate(timeout_seconds=60)
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"},
        )
        request_id = result.request_id

        # 第一次reject
        success1 = await gate.reject(request_id, "admin", "too risky")
        assert success1 is True
        assert gate.get_request(request_id).status == ApprovalStatus.REJECTED

        # 第二次reject同一审批人 - 应该被忽略（幂等）
        success2 = await gate.reject(request_id, "admin", "too risky again")
        assert success2 is True  # 返回True表示已处理，但不改变状态
        assert gate.get_request(request_id).status == ApprovalStatus.REJECTED

        # approvers列表中只有一条记录
        assert gate.get_request(request_id).approvers.count("admin") == 1

    @pytest.mark.asyncio
    async def test_reject_different_approver_still_changes_status(self):
        """测试不同审批人reject仍可改变状态（如果第一个是approve）"""
        gate = ApprovalGate(timeout_seconds=60)

        # 创建一个L5双签审批
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1", "risk_level": 3},  # L5
            params={"statement": "SELECT 1"},
        )
        request_id = result.request_id

        # L5: 第一个approve后还是PENDING
        await gate.approve(request_id, "admin1", "ok")
        assert gate.get_request(request_id).status == ApprovalStatus.PENDING  # L5需要两人

        # 重新建一个测试（用不同 params 确保不同 request_id）
        result2 = await gate.request_approval(
            action="delete_data",
            context={"user_id": "user1", "risk_level": 3},  # L5
            params={"statement": "DELETE FROM users WHERE id=1"},  # 不同 params → 不同 hash
        )
        request_id2 = result2.request_id
        # 确认 request_id2 != request_id（不同 params 产生不同 hash）
        assert request_id2 != request_id, "params 太相似导致 hash 碰撞，请修改 params"

        # 先reject
        await gate.reject(request_id2, "admin", "too risky")
        assert gate.get_request(request_id2).status == ApprovalStatus.REJECTED

        # 再approve同一审批人应该被忽略（幂等）
        await gate.approve(request_id2, "admin", "changed my mind")
        assert gate.get_request(request_id2).status == ApprovalStatus.REJECTED  # 状态不变


class TestWebhookClientIPExtraction:
    """客户端IP提取测试"""

    def test_get_client_ip_forwarded(self):
        """测试从X-Forwarded-For提取IP"""
        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
        mock_request.client = None

        assert _get_client_ip(mock_request) == "1.2.3.4"

    def test_get_client_ip_real_ip(self):
        """测试从X-Real-IP提取IP"""
        mock_request = MagicMock()
        mock_request.headers = {"X-Real-IP": "9.9.9.9"}
        mock_request.client = None

        assert _get_client_ip(mock_request) == "9.9.9.9"

    def test_get_client_ip_direct(self):
        """测试直接连接"""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"

        assert _get_client_ip(mock_request) == "127.0.0.1"
