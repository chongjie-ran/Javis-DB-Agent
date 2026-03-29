"""测试 API限速 (第15轮 P0-2)

验证 IP/用户维度的限流功能
"""
import pytest
import time
from unittest.mock import MagicMock

from src.security.rate_limit import (
    RateLimitStore,
    RateLimitConfig,
    RateLimitExceeded,
    RateLimitDependency,
    extract_client_ip,
    DEFAULT_LIMITS,
    get_rate_limit_status,
    configure_rate_limits,
)


class TestRateLimitStore:
    """滑动窗口计数器测试"""

    def test_first_request_allowed(self):
        store = RateLimitStore()
        config = RateLimitConfig(requests=5, window_seconds=60, block_seconds=0)
        allowed, retry_after = store.check_and_increment("test", "client1", config)
        assert allowed is True
        assert retry_after == 0

    def test_within_limit_allowed(self):
        store = RateLimitStore()
        config = RateLimitConfig(requests=3, window_seconds=60, block_seconds=0)
        for _ in range(3):
            allowed, _ = store.check_and_increment("test", "client1", config)
            assert allowed is True

    def test_over_limit_blocked(self):
        store = RateLimitStore()
        config = RateLimitConfig(requests=2, window_seconds=60, block_seconds=0)
        store.check_and_increment("test", "client1", config)
        store.check_and_increment("test", "client1", config)
        allowed, retry_after = store.check_and_increment("test", "client1", config)
        assert allowed is False
        assert retry_after > 0

    def test_different_identifiers_independent(self):
        store = RateLimitStore()
        config = RateLimitConfig(requests=1, window_seconds=60, block_seconds=0)
        allowed1, _ = store.check_and_increment("test", "client1", config)
        allowed2, _ = store.check_and_increment("test", "client2", config)
        assert allowed1 is True
        assert allowed2 is True

    def test_different_limit_types_independent(self):
        store = RateLimitStore()
        config1 = RateLimitConfig(requests=1, window_seconds=60, block_seconds=0)
        config2 = RateLimitConfig(requests=1, window_seconds=60, block_seconds=0)
        # 耗尽 login 限制
        store.check_and_increment("login", "client1", config1)
        # chat 限制不受影响
        allowed, _ = store.check_and_increment("chat", "client1", config2)
        assert allowed is True

    def test_window_reset_after_time(self):
        store = RateLimitStore()
        config = RateLimitConfig(requests=1, window_seconds=1, block_seconds=0)
        allowed1, _ = store.check_and_increment("test", "client1", config)
        assert allowed1 is True
        # 超限
        allowed2, _ = store.check_and_increment("test", "client1", config)
        assert allowed2 is False
        # 等待窗口过期
        time.sleep(1.1)
        allowed3, _ = store.check_and_increment("test", "client1", config)
        assert allowed3 is True

    def test_block_activated_when_configured(self):
        store = RateLimitStore()
        config = RateLimitConfig(requests=1, window_seconds=60, block_seconds=300)
        store.check_and_increment("test", "client1", config)
        allowed, retry_after = store.check_and_increment("test", "client1", config)
        assert allowed is False
        assert retry_after > 0
        # 立即再次检查，应该仍在封禁中（block与window共用同一个key: "{limiter_type}:{identifier}"）
        allowed_blocked, remaining = store._is_blocked("test:client1")
        assert allowed_blocked is True
        assert remaining > 0


class TestExtractClientIP:
    """IP提取测试"""

    def test_x_forwarded_for_first_ip(self):
        mock_request = MagicMock()
        mock_request.headers = {"x-forwarded-for": "203.0.113.50, 70.41.3.18, 150.172.238.178"}
        mock_request.client = MagicMock(host="10.0.0.1")
        ip = extract_client_ip(mock_request)
        assert ip == "203.0.113.50"

    def test_x_real_ip(self):
        mock_request = MagicMock()
        mock_request.headers = {"x-real-ip": "198.51.100.178"}
        mock_request.client = MagicMock(host="10.0.0.1")
        ip = extract_client_ip(mock_request)
        assert ip == "198.51.100.178"

    def test_direct_connection(self):
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "192.168.1.100"
        ip = extract_client_ip(mock_request)
        assert ip == "192.168.1.100"

    def test_empty_x_forwarded_for_falls_back(self):
        mock_request = MagicMock()
        mock_request.headers = {"x-forwarded-for": ""}
        mock_request.client.host = "10.0.0.1"
        ip = extract_client_ip(mock_request)
        assert ip == "10.0.0.1"


class TestRateLimitConfig:
    """限流配置默认值测试"""

    def test_default_limits_defined(self):
        assert "login" in DEFAULT_LIMITS
        assert "refresh" in DEFAULT_LIMITS
        assert "register" in DEFAULT_LIMITS
        assert "chat" in DEFAULT_LIMITS
        assert "global_ip" in DEFAULT_LIMITS

    def test_login_limit_is_strict(self):
        login_cfg = DEFAULT_LIMITS["login"]
        assert login_cfg.requests <= 10  # 应该比较严格

    def test_chat_limit_allows_burst(self):
        chat_cfg = DEFAULT_LIMITS["chat"]
        assert chat_cfg.requests >= 20  # 应该允许一定频率


class TestRateLimitDependency:
    """FastAPI 依赖测试"""

    def test_rate_limit_dep_allows_first_request(self):
        """测试依赖允许首个请求"""
        # 用独立store避免全局状态
        import sys
        rl_module = sys.modules["src.security.rate_limit"]
        original_store = getattr(rl_module, "_rate_store", None)
        rl_module._rate_store = RateLimitStore()
        try:
            configure_rate_limits({
                "login": RateLimitConfig(requests=1, window_seconds=60, block_seconds=0)
            })
            # 预填充0个请求，让第一个dep调用通过
            store = rl_module._rate_store
            # 不做任何预填充，第一个请求应该在限制内
            dep = RateLimitDependency("login")
            mock_request = MagicMock()
            # Use dict-like mock so .get() returns the default value
            mock_request.headers = MagicMock()
            mock_request.headers.get = lambda k, d="": d  # type: ignore
            mock_request.client.host = "127.0.0.1"

            # 第1个请求应通过
            dep(mock_request)
        finally:
            rl_module._rate_store = original_store

    def test_rate_limit_exceeded_returns_retry_after(self):
        """RateLimitExceeded 应包含正确的 retry_after"""
        from src.security.rate_limit import RateLimitExceeded
        exc = RateLimitExceeded(retry_after=30, message="test")
        assert exc.status_code == 429
        assert exc.headers["Retry-After"] == "30"
        assert "test" in exc.detail



class TestGetRateLimitStatus:
    """限流状态查询测试"""

    def test_status_returns_dict(self):
        status = get_rate_limit_status("login", "test_client")
        assert isinstance(status, dict)
        assert status["action"] == "login"
        assert status["identifier"] == "test_client"
        assert "blocked" in status
        assert "current_count" in status
