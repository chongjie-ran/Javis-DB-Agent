"""Round 14 安全加固测试 - P0任务"""
import pytest
import ssl
import time
import tempfile
import os
from pathlib import Path

from src.security.tls import TLSConfig, TLSMiddleware
from src.security.sensitive import (
    SensitiveDataMask, mask_value, mask_ip, mask_email, mask_phone,
    _is_sensitive_field,
)
from src.gateway.audit import _sanitize_audit_record
from src.api.auth import AuthManager, hash_password, verify_password
from src.api.auth_routes import LoginResponse, RefreshTokenResponse


# ============ P0-1: TLS/SSL配置测试 ============

class TestTLSConfig:
    """TLS配置测试"""
    
    def test_tls_config_defaults(self):
        """测试默认配置"""
        config = TLSConfig()
        assert config.enabled is False
        assert config.hsts_enabled is False
        assert config.cert_file is None
        assert config.key_file is None
    
    def test_tls_config_from_env(self):
        """测试从环境变量加载"""
        config = TLSConfig.from_env()
        # 不应抛出异常
        assert isinstance(config.enabled, bool)
        assert isinstance(config.hsts_max_age, int)
    
    def test_tls_config_hsts_header(self):
        """测试HSTS响应头生成"""
        config = TLSConfig(
            enabled=True,
            hsts_enabled=True,
            hsts_max_age=31536000,
            hsts_include_subdomains=True,
        )
        header = config.get_hsts_header()
        assert header is not None
        assert "max-age=31536000" in header
        assert "includeSubDomains" in header
    
    def test_tls_config_hsts_header_disabled(self):
        """测试HSTS禁用时不生成头"""
        config = TLSConfig(enabled=False, hsts_enabled=False)
        assert config.get_hsts_header() is None
    
    def test_tls_config_validate_missing_cert(self):
        """测试缺少证书文件时的验证"""
        config = TLSConfig(enabled=True, cert_file="/nonexistent/cert.pem")
        errors = config.validate()
        assert len(errors) > 0
        assert any("不存在" in e for e in errors)
    
    def test_tls_config_validate_ok(self, tmp_path):
        """测试有效配置通过验证"""
        # 创建临时证书文件
        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"
        cert_file.write_text("dummy cert")
        key_file.write_text("dummy key")
        # 设置合理权限
        os.chmod(key_file, 0o600)
        
        config = TLSConfig(enabled=True, cert_file=str(cert_file), key_file=str(key_file))
        errors = config.validate()
        assert len(errors) == 0
    
    def test_tls_config_validate_key_permissions(self, tmp_path):
        """测试私钥权限过宽时的警告"""
        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"
        cert_file.write_text("dummy cert")
        key_file.write_text("dummy key")
        os.chmod(key_file, 0o644)  # 过宽的权限
        
        config = TLSConfig(enabled=True, cert_file=str(cert_file), key_file=str(key_file))
        errors = config.validate()
        assert any("权限过宽" in e for e in errors)
    
    def test_get_ssl_context_requires_enabled(self):
        """测试只有启用时才创建SSL上下文"""
        config = TLSConfig(enabled=False)
        assert config.get_ssl_context() is None
    
    def test_ollama_ssl_context_skip_verify(self):
        """测试Ollama跳过SSL验证"""
        config = TLSConfig(ollama_verify_ssl=False)
        ctx = config.get_ollama_ssl_context()
        assert ctx is None  # 返回None表示跳过验证


class TestSensitiveDataMask:
    """敏感数据脱敏测试"""
    
    def test_mask_password(self):
        """测试密码字段自动掩码"""
        data = {"password": "supersecret123"}
        mask = SensitiveDataMask()
        result = mask.mask(data)
        assert result["password"] != "supersecret123"
        assert "supersecret123" not in str(result)
    
    def test_mask_api_key(self):
        """测试API Key字段自动掩码"""
        data = {"api_key": "sk_test_abcdef123456"}
        mask = SensitiveDataMask()
        result = mask.mask(data)
        assert result["api_key"] != "sk_test_abcdef123456"
        assert result["api_key"].endswith("3456")  # 保留后4位
    
    def test_mask_nested_dict(self):
        """测试嵌套字典脱敏"""
        data = {
            "user": {
                "name": "testuser",
                "credentials": {
                    "password": "secretpass",
                    "token": "bearer_token_abc123",
                }
            }
        }
        mask = SensitiveDataMask()
        result = mask.mask(data)
        assert result["user"]["credentials"]["password"] != "secretpass"
        assert result["user"]["name"] == "testuser"  # 非敏感字段不掩码
    
    def test_mask_list(self):
        """测试列表脱敏"""
        data = [
            {"name": "user1", "password": "pass1"},
            {"name": "user2", "password": "pass2"},
        ]
        mask = SensitiveDataMask()
        result = mask.mask(data)
        assert result[0]["password"] != "pass1"
        assert result[1]["password"] != "pass2"
        assert result[0]["name"] == "user1"
    
    def test_mask_ip(self):
        """测试IP地址脱敏"""
        assert mask_ip("192.168.1.100") == "192.168.*.100"
        assert mask_ip("10.0.0.1") == "10.0.*.1"
        assert mask_ip("invalid") == "****"  # 非IP字符串，固定掩码
    
    def test_mask_email(self):
        """测试邮箱脱敏"""
        result = mask_email("user@example.com")
        assert "@example.com" in result
        assert "u" in result and "r" in result  # 首尾字符保留
        assert "****" in result or "**" in result  # 中间字符掩码
        assert "user" not in result  # 不应包含完整用户名
    
    def test_mask_phone(self):
        """测试手机号脱敏"""
        result = mask_phone("13812345678")
        assert result == "138****5678"
        assert "****" in result
    
    def test_is_sensitive_field(self):
        """测试敏感字段识别"""
        sensitive = ["password", "api_key", "token", "secret", "authorization", "refresh_token"]
        non_sensitive = ["username", "email", "name", "description", "comment"]
        
        for field in sensitive:
            assert _is_sensitive_field(field), f"{field} should be sensitive"
        for field in non_sensitive:
            assert not _is_sensitive_field(field), f"{field} should not be sensitive"
    
    def test_mask_pii(self):
        """测试PII脱敏"""
        data = {
            "user": "张三",
            "email": "zhangsan@example.com",
            "phone": "13812345678",
            "ip": "192.168.1.100",
        }
        mask = SensitiveDataMask()
        result = mask.mask_pii(data)
        assert "@example.com" in result["email"]
        assert "****" in result["email"]
        assert result["phone"] == "138****5678"
        assert result["ip"] == "192.168.*.100"


class TestSanitizeAuditRecord:
    """审计日志脱敏测试"""
    
    def test_sanitize_password_in_params(self):
        """测试params中密码脱敏"""
        record = {
            "id": "test-123",
            "action": "tool.call",
            "params": {"password": "secret123", "instance_id": "db1"},
        }
        result = _sanitize_audit_record(record)
        assert result["params"]["password"] != "secret123"
        assert result["params"]["instance_id"] == "db1"  # 非敏感不改变
    
    def test_sanitize_ip_address(self):
        """测试IP地址脱敏"""
        record = {"ip_address": "10.0.0.100"}
        result = _sanitize_audit_record(record)
        assert result["ip_address"] == "10.0.*.100"
    
    def test_sanitize_token_in_error_message(self):
        """测试error_message中token掩码"""
        record = {
            "error_message": "Auth failed: token=abc123def456gh invalid"
        }
        result = _sanitize_audit_record(record)
        assert "abc123def456gh" not in result["error_message"]
        assert "***REDACTED***" in result["error_message"]


# ============ P0-2: API鉴权机制测试 ============

class TestAuthManager:
    """认证管理器测试"""
    
    def test_hash_and_verify_password(self):
        """测试密码哈希和验证"""
        password = "MySecurePassword123!"
        hashed, salt = hash_password(password)
        
        assert hashed != password
        assert verify_password(password, hashed, salt) is True
        assert verify_password("wrongpassword", hashed, salt) is False
    
    def test_create_token_returns_tuple(self, tmp_path):
        """测试create_token返回access+refresh对"""
        users_file = tmp_path / "users.json"
        secret_file = tmp_path / "secret.key"
        
        auth = AuthManager(users_file=users_file, secret_file=secret_file)
        user = auth.register_user("testuser", "password123")
        
        access_token, refresh_token = auth.create_token(user)
        
        assert isinstance(access_token, str)
        assert isinstance(refresh_token, str)
        assert access_token != refresh_token
        assert len(access_token) > 20
        assert len(refresh_token) > 20
    
    def test_refresh_access_token(self, tmp_path):
        """测试refresh_token刷新access_token"""
        users_file = tmp_path / "users.json"
        secret_file = tmp_path / "secret.key"
        
        auth = AuthManager(users_file=users_file, secret_file=secret_file)
        user = auth.register_user("testuser", "password123")
        
        _, refresh_token = auth.create_token(user)
        result = auth.refresh_access_token(refresh_token)
        
        assert result is not None
        new_access, new_refresh = result
        assert isinstance(new_access, str)
        assert isinstance(new_refresh, str)
        assert new_access != new_refresh
    
    def test_refresh_token_invalid(self, tmp_path):
        """测试无效refresh_token返回None"""
        users_file = tmp_path / "users.json"
        secret_file = tmp_path / "secret.key"
        
        auth = AuthManager(users_file=users_file, secret_file=secret_file)
        auth.register_user("testuser", "password123")
        
        result = auth.refresh_access_token("invalid_token_string")
        assert result is None
    
    def test_verify_token_requires_correct_type(self, tmp_path):
        """测试verify_token验证token类型"""
        users_file = tmp_path / "users.json"
        secret_file = tmp_path / "secret.key"
        
        auth = AuthManager(users_file=users_file, secret_file=secret_file)
        user = auth.register_user("testuser", "password123")
        
        access_token, refresh_token = auth.create_token(user)
        
        # access token验证为access类型应该通过
        assert auth.verify_token(access_token, require_type="access") is not None
        # access token验证为refresh类型应该失败
        assert auth.verify_token(access_token, require_type="refresh") is None
        # refresh token验证为refresh类型应该通过
        assert auth.verify_token(refresh_token, require_type="refresh") is not None
        # refresh token验证为access类型应该失败
        assert auth.verify_token(refresh_token, require_type="access") is None
    
    def test_revoke_token(self, tmp_path):
        """测试token撤销"""
        users_file = tmp_path / "users.json"
        secret_file = tmp_path / "secret.key"
        
        auth = AuthManager(users_file=users_file, secret_file=secret_file)
        user = auth.register_user("testuser", "password123")
        
        access_token, _ = auth.create_token(user)
        
        # 验证token有效
        assert auth.verify_token(access_token) is not None
        
        # 撤销token
        auth.revoke_token(access_token)
        
        # 验证token已失效
        assert auth.verify_token(access_token) is None
    
    def test_revoke_token_prevents_replay(self, tmp_path):
        """测试撤销后的refresh_token不能用于刷新（replay攻击防护）"""
        users_file = tmp_path / "users.json"
        secret_file = tmp_path / "secret.key"
        
        auth = AuthManager(users_file=users_file, secret_file=secret_file)
        user = auth.register_user("testuser", "password123")
        
        _, refresh_token = auth.create_token(user)
        
        # 第一次刷新应该成功
        result1 = auth.refresh_access_token(refresh_token)
        assert result1 is not None
        
        # 第二次使用同一个refresh_token应该失败（已被撤销）
        result2 = auth.refresh_access_token(refresh_token)
        assert result2 is None


# ============ P0-4: 测试修复验证 ============

class TestRealClientSingleton:
    """RealClient单例测试（验证async事件循环问题已修复）"""
    
    def test_get_real_client_singleton(self):
        """测试get_real_client返回单例"""
        from src.real_api.client import get_real_client, reset_real_client
        
        # 重置以确保干净状态
        reset_real_client()
        
        client1 = get_real_client()
        client2 = get_real_client()
        
        assert client1 is client2  # 应该是同一个对象（单例）
    
    def test_reset_real_client_sync_safe(self):
        """测试reset_real_client在无事件循环时同步安全"""
        from src.real_api import get_real_client, reset_real_client
        import src.real_api.client as client_mod

        # 重置到干净状态
        client_mod._real_client = None

        # 获取一个client
        c1 = get_real_client()
        assert c1 is not None

        # reset应该能同步执行不崩溃
        reset_real_client()

        # 重置后应创建新实例
        c2 = get_real_client()
        assert c2 is not None
        assert c1 is not c2  # 应该是不同对象
