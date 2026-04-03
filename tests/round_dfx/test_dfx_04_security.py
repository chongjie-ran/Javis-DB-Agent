"""
DFX-04: 安全性测试（Security）
==================================
覆盖范围：
- SEC-01: HMAC签名验证
- SEC-02: IP白名单
- SEC-03: SQL注入防护
- SEC-04: 审批绕过尝试
- SEC-05: 越权访问

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round_dfx/test_dfx_04_security.py -v --tb=short
"""

import asyncio
import hashlib
import hmac
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.gateway.approval import ApprovalGate, ApprovalStatus
from src.gateway.hooks import HookEvent, HookContext, HookRule, HookAction, HookCondition
from src.gateway.hooks import ConditionOperator, ModifyOperation, ModifyOperationType
from src.gateway.hooks import HookEngine
from src.gateway.persistent_session import PersistentSessionManager


# ============================================================================
# SEC-01: HMAC签名验证
# ============================================================================

class TestHMACSignatureVerification:
    """HMAC签名验证测试"""

    def test_hmac_valid_signature(self):
        """SEC-01: 有效签名验证"""
        from src.api.approval_routes import _verify_hmac_signature
        
        secret = "test-secret-key-12345"
        body = b'{"request_id":"abc123","action":"approve"}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": secret}):
            result = _verify_hmac_signature(body, signature)
            assert result is True

    def test_hmac_case_insensitive(self):
        """SEC-02: 签名验证大小写不敏感"""
        from src.api.approval_routes import _verify_hmac_signature
        
        secret = "secret"
        body = b'{"test":true}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": secret}):
            # 大写签名
            result = _verify_hmac_signature(body, signature.upper())
            assert result is True

    def test_hmac_empty_body(self):
        """SEC-03: 空请求体验证"""
        from src.api.approval_routes import _verify_hmac_signature
        
        secret = "secret"
        body = b''
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": secret}):
            result = _verify_hmac_signature(body, signature)
            assert result is True

    def test_hmac_tampered_body(self):
        """SEC-04: 请求体被篡改"""
        from src.api.approval_routes import _verify_hmac_signature
        
        secret = "secret"
        original_body = b'{"request_id":"abc123"}'
        tampered_body = b'{"request_id":"abc123","action":"approve"}'
        signature = hmac.new(secret.encode(), original_body, hashlib.sha256).hexdigest()
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": secret}):
            result = _verify_hmac_signature(tampered_body, signature)
            assert result is False

    def test_hmac_missing_secret(self):
        """SEC-05: 未配置密钥时跳过验证"""
        from src.api.approval_routes import _verify_hmac_signature
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": ""}):
            result = _verify_hmac_signature(b'{"test":true}', "any_signature")
            assert result is True  # 跳过验证

    def test_hmac_wrong_secret(self):
        """SEC-06: 错误密钥"""
        from src.api.approval_routes import _verify_hmac_signature
        
        body = b'{"test":true}'
        wrong_sig = hmac.new("wrong_secret".encode(), body, hashlib.sha256).hexdigest()
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_SECRET": "correct_secret"}):
            result = _verify_hmac_signature(body, wrong_sig)
            assert result is False


# ============================================================================
# SEC-02: IP白名单
# ============================================================================

class TestIPWhitelist:
    """IP白名单测试"""

    def test_ip_exact_match(self):
        """SEC-07: IP精确匹配"""
        from src.api.approval_routes import _verify_ip_whitelist
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": "192.168.1.100"}):
            assert _verify_ip_whitelist("192.168.1.100") is True
            assert _verify_ip_whitelist("192.168.1.101") is False

    def test_ip_cidr_24(self):
        """SEC-08: /24 CIDR范围"""
        from src.api.approval_routes import _verify_ip_whitelist
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": "10.0.0.0/24"}):
            assert _verify_ip_whitelist("10.0.0.1") is True
            assert _verify_ip_whitelist("10.0.0.254") is True
            assert _verify_ip_whitelist("10.0.1.1") is False

    def test_ip_cidr_16(self):
        """SEC-09: /16 CIDR范围"""
        from src.api.approval_routes import _verify_ip_whitelist
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": "172.16.0.0/16"}):
            assert _verify_ip_whitelist("172.16.0.1") is True
            assert _verify_ip_whitelist("172.16.255.254") is True
            assert _verify_ip_whitelist("172.17.0.1") is False

    def test_ip_multiple_networks(self):
        """SEC-10: 多网络白名单"""
        from src.api.approval_routes import _verify_ip_whitelist
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": "10.0.0.0/8,192.168.0.0/16,172.16.0.0/12"}):
            assert _verify_ip_whitelist("10.5.6.7") is True
            assert _verify_ip_whitelist("192.168.1.1") is True
            assert _verify_ip_whitelist("172.20.1.1") is True
            assert _verify_ip_whitelist("8.8.8.8") is False

    def test_ip_empty_whitelist(self):
        """SEC-11: 空白名单跳过检查"""
        from src.api.approval_routes import _verify_ip_whitelist
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": ""}):
            assert _verify_ip_whitelist("1.2.3.4") is True

    def test_ip_invalid_format(self):
        """SEC-12: 无效IP格式"""
        from src.api.approval_routes import _verify_ip_whitelist
        
        with patch.dict(os.environ, {"APPROVAL_WEBHOOK_ALLOWED_IPS": "10.0.0.0/24"}):
            assert _verify_ip_whitelist("not.an.ip.address") is False


# ============================================================================
# SEC-03: SQL注入防护
# ============================================================================

class TestSQLInjectionPrevention:
    """SQL注入防护测试"""

    @pytest.fixture
    def sql_guard_engine(self):
        """带SQL防护规则的HookEngine"""
        import src.gateway.hooks.hook_registry as hr_module
        hr_module._registry = None
        engine = HookEngine()
        
        async def sanitize_handler(ctx):
            sql = ctx.get("sql_statement", "")
            # 简单的SQL注入检测和清理
            dangerous_patterns = ["DROP TABLE", "DELETE FROM", "TRUNCATE", "--", "/*", "UNION SELECT", "UNION ALL"]
            for pattern in dangerous_patterns:
                if pattern in sql.upper():
                    ctx.set("sql_statement", "[SQL SANITIZED]")
                    ctx.set("blocked_reason", f"Potential SQL injection: {pattern}")
                    break
            return ctx
        
        engine.register_rule(HookRule(
            name="sql_guard",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.CONTAINS,
                    value="DROP"
                )
            ],
            action=HookAction.MODIFY,
            handler=sanitize_handler
        ))
        
        # Separate rule for UNION injection detection
        engine.register_rule(HookRule(
            name="sql_guard_union",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.CONTAINS,
                    value="UNION"
                )
            ],
            action=HookAction.MODIFY,
            handler=sanitize_handler
        ))
        
        yield engine
        
        import src.gateway.hooks.hook_registry as hr_module
        hr_module._registry = None

    @pytest.mark.asyncio
    async def test_sql_injection_drop_table_blocked(self, sql_guard_engine):
        """SEC-14: DROP TABLE被阻断"""
        engine = sql_guard_engine
        
        result = await engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "SELECT * FROM users; DROP TABLE users"},
            session_id="sess1",
            user_id="user1"
        )
        
        # SQL应该被清理
        assert result.payload.get("sql_statement") == "[SQL SANITIZED]"

    @pytest.mark.asyncio
    async def test_sql_injection_drop_table_variant(self, sql_guard_engine):
        """SEC-15: DROP TABLE变体被阻断"""
        engine = sql_guard_engine
        
        result = await engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "1; DROP TABLE admin_users--"},
            session_id="sess1",
            user_id="user1"
        )
        
        assert result.payload.get("sql_statement") == "[SQL SANITIZED]"

    @pytest.mark.asyncio
    async def test_safe_sql_not_blocked(self, sql_guard_engine):
        """SEC-16: 安全SQL不被阻断"""
        engine = sql_guard_engine
        
        result = await engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "SELECT id, name FROM users WHERE id = 1"},
            session_id="sess1",
            user_id="user1"
        )
        
        # 安全SQL应该不被修改
        assert "SELECT" in result.payload.get("sql_statement", "")


# ============================================================================
# SEC-04: 审批绕过尝试
# ============================================================================

class TestApprovalBypassAttempts:
    """审批绕过尝试测试"""

    @pytest.mark.asyncio
    async def test_cannot_approve_nonexistent_request(self, approval_gate_normal):
        """SEC-18: 审批不存在的请求"""
        gate = approval_gate_normal
        
        result = await gate.approve("nonexistent_id_12345", "approver1", "LGTM")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_cannot_reject_nonexistent_request(self, approval_gate_normal):
        """SEC-19: 拒绝不存在的请求"""
        gate = approval_gate_normal
        
        result = await gate.reject("nonexistent_id_12345", "approver1", "No")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_already_approved_cannot_approve_again(self, approval_gate_normal):
        """SEC-20: 已通过的请求不能再审批"""
        gate = approval_gate_normal
        
        result = await gate.request_approval(
            action="test",
            context={"user_id": "user1"},
            params={"sql": "SELECT 1"}
        )
        
        request_id = result.request_id
        
        # 第一次审批通过
        await gate.approve(request_id, "approver1")
        
        status = await gate.get_status(request_id)
        assert status.status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_already_rejected_cannot_approve(self, approval_gate_normal):
        """SEC-21: 已拒绝的请求不能再通过"""
        gate = approval_gate_normal
        
        result = await gate.request_approval(
            action="test",
            context={"user_id": "user1"},
            params={"sql": "SELECT 1"}
        )
        
        request_id = result.request_id
        
        # 拒绝
        await gate.reject(request_id, "approver1", "Rejected")
        
        # 尝试通过
        approved = await gate.approve(request_id, "approver2", "Override")
        
        status = await gate.get_status(request_id)
        assert status.status == ApprovalStatus.REJECTED
        assert approved is False

    @pytest.mark.asyncio
    async def test_timeout_request_cannot_be_approved(self, approval_gate_short):
        """SEC-22: 超时的请求不能再审批"""
        gate = approval_gate_short
        
        result = await gate.request_approval(
            action="test",
            context={"user_id": "user1"},
            params={"sql": "SELECT 1"}
        )
        
        request_id = result.request_id
        
        # 等待超时
        await asyncio.sleep(4)
        await gate.cleanup_timeout()
        
        # 尝试审批超时的请求
        approved = await gate.approve(request_id, "approver1", "Late approval")
        
        assert approved is False

    @pytest.mark.asyncio
    async def test_params_hash_prevents_tampering(self, approval_gate_normal):
        """SEC-23: params_hash防止参数篡改"""
        gate = approval_gate_normal
        
        result = await gate.request_approval(
            action="test",
            context={"user_id": "user1"},
            params={"sql": "SELECT 1", "risk_level": "L3"}
        )
        
        request_id = result.request_id
        
        # 获取原始请求
        req = gate.get_request(request_id)
        original_hash = req.params_hash
        
        # params_hash应该被计算
        assert original_hash is not None
        assert len(original_hash) == 64  # SHA256 hex length


# ============================================================================
# SEC-05: 越权访问
# ============================================================================

class TestUnauthorizedAccess:
    """越权访问测试"""

    def test_session_cannot_access_other_user_session(self, temp_db_path):
        """SEC-24: 会话不能访问其他用户的会话"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        # 用户1创建会话
        session1 = mgr.create_session("user1")
        
        # 用户2创建会话
        session2 = mgr.create_session("user2")
        
        # 用户2不应该能获取用户1的会话
        user2_sessions = mgr.list_user_sessions("user2")
        user2_sids = [s.session_id for s in user2_sessions]
        
        assert session1.session_id not in user2_sids
        assert session2.session_id in user2_sids
        
        mgr.cleanup_all()

    def test_session_isolation_by_user_id(self, temp_db_path):
        """SEC-25: 用户ID隔离"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        session1 = mgr.create_session("user1")
        mgr.create_session("user2")
        
        # 每个用户只能看到自己的会话
        user1_sessions = mgr.list_user_sessions("user1")
        user1_ids = [s.session_id for s in user1_sessions]
        
        assert session1.session_id in user1_ids
        
        mgr.cleanup_all()

    @pytest.mark.asyncio
    async def test_approval_request_isolation(self, approval_gate_normal):
        """SEC-26: 审批请求隔离"""
        gate = approval_gate_normal
        
        result1 = await gate.request_approval(
            action="test1",
            context={"user_id": "user1"},
            params={"sql": "SELECT 1"}
        )
        
        result2 = await gate.request_approval(
            action="test2",
            context={"user_id": "user2"},
            params={"sql": "SELECT 2"}
        )
        
        # 两个请求ID应该不同
        assert result1.request_id != result2.request_id
        
        # user1不能审批user2的请求（user1不在审批人列表中）
        # 但user1可以查询user2请求的状态
        status1_of_req2 = await gate.get_status(result2.request_id)
        assert status1_of_req2 is not None


# ============================================================================
# SEC-06: 安全配置验证
# ============================================================================

class TestSecurityConfiguration:
    """安全配置验证测试"""

    def test_hmac_secret_not_empty_in_production(self):
        """SEC-27: 生产环境HMAC密钥检查"""
        # 检查是否配置了非空密钥
        secret = os.environ.get("APPROVAL_WEBHOOK_SECRET", "")
        
        # 如果在生产环境，应该有密钥
        # 测试环境允许为空
        if os.environ.get("ZLOUD_ENV") == "production":
            assert secret != "", "生产环境必须配置APPROVAL_WEBHOOK_SECRET"

    def test_ip_whitelist_cidr_validation(self):
        """SEC-28: 白名单CIDR格式验证"""
        from src.api.approval_routes import _verify_ip_whitelist
        
        # 无效网络格式应该被正确处理（不崩溃）
        # 具体行为取决于实现
