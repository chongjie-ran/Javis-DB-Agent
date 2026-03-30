"""认证鉴权测试 - V1.4 Round 1
测试 OAuth2Provider.refresh_token() 修复和 API Key + OAuth2 双模式
"""
import pytest
import time
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class TestOAuth2ProviderRefreshToken:
    """OAuth2Provider.refresh_token() 测试"""

    def test_refresh_token_sync_success(self):
        """测试同步刷新Token成功"""
        from src.real_api.auth import OAuth2Provider

        provider = OAuth2Provider(
            token_url="https://api.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            grant_type="refresh_token",
            pre_refresh_token="old_refresh_token",
        )

        # Mock httpx.Client.post
        with patch("httpx.Client") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            # 调用同步刷新
            result = provider._sync_refresh()

            assert result is True
            assert provider._access_token == "new_access_token"
            assert provider._refresh_token == "new_refresh_token"

    def test_refresh_token_sync_no_token(self):
        """测试同步刷新无refresh_token"""
        from src.real_api.auth import OAuth2Provider

        provider = OAuth2Provider(
            token_url="https://api.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            grant_type="refresh_token",
        )

        result = provider._sync_refresh()
        assert result is False

    def test_refresh_token_sync_failure(self):
        """测试同步刷新失败"""
        from src.real_api.auth import OAuth2Provider

        provider = OAuth2Provider(
            token_url="https://api.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            grant_type="refresh_token",
            pre_refresh_token="old_refresh_token",
        )

        with patch("httpx.Client") as mock_client_class:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = Exception("HTTP Error")

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = provider._sync_refresh()
            assert result is False

    @pytest.mark.asyncio
    async def test_refresh_token_async_success(self):
        """测试异步refresh_token方法成功"""
        from src.real_api.auth import OAuth2Provider

        provider = OAuth2Provider(
            token_url="https://api.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            grant_type="refresh_token",
            pre_refresh_token="old_refresh_token",
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "new_access_token_async",
                "refresh_token": "new_refresh_token_async",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
            mock_response.raise_for_status = MagicMock()

            async def mock_post(*args, **kwargs):
                return mock_response
            
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            result = await provider.refresh_token()

            assert "access_token" in result
            assert result["access_token"] == "new_access_token_async"

    @pytest.mark.asyncio
    async def test_refresh_token_async_no_token(self):
        """测试异步refresh_token无token"""
        from src.real_api.auth import OAuth2Provider

        provider = OAuth2Provider(
            token_url="https://api.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            grant_type="refresh_token",
        )

        result = await provider.refresh_token()
        assert "error" in result
        assert result["error"] == "no_refresh_token"

    @pytest.mark.asyncio
    async def test_refresh_token_async_http_error(self):
        """测试异步refresh_token HTTP错误"""
        from src.real_api.auth import OAuth2Provider

        provider = OAuth2Provider(
            token_url="https://api.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            grant_type="refresh_token",
            pre_refresh_token="old_refresh_token",
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            import httpx

            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "invalid refresh token"

            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=mock_response,
            )

            mock_client = MagicMock()
            mock_client.__aenter__ = MagicMock(return_value=mock_client)
            mock_client.__aexit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await provider.refresh_token()
            assert "error" in result
            assert result["error"] == "token_refresh_failed"


class TestAPIModeDualSupport:
    """API Key + OAuth2 双模式测试"""

    def test_api_key_provider_is_valid(self):
        """测试API Key模式token有效性"""
        from src.real_api.auth import APIKeyProvider

        provider = APIKeyProvider(api_key="test_api_key_12345")

        assert provider.is_token_valid() is True
        assert provider.get_access_token() == "test_api_key_12345"

    @pytest.mark.asyncio
    async def test_api_key_refresh_returns_api_key(self):
        """测试API Key模式refresh_token返回"""
        from src.real_api.auth import APIKeyProvider

        provider = APIKeyProvider(api_key="test_api_key_12345")

        result = await provider.refresh_token()
        assert result["access_token"] == "test_api_key_12345"
        assert result["token_type"] == "ApiKey"

    def test_api_key_get_auth_headers(self):
        """测试API Key获取认证头"""
        from src.real_api.auth import APIKeyProvider

        provider = APIKeyProvider(api_key="test_api_key_12345", header_name="X-API-Key")
        headers = provider.get_auth_headers()
        assert headers == {"X-API-Key": "test_api_key_12345"}

        # 测试Authorization头
        provider2 = APIKeyProvider(api_key="test_api_key_12345", header_name="Authorization")
        headers2 = provider2.get_auth_headers()
        assert headers2 == {"Authorization": "ApiKey test_api_key_12345"}

    def test_oauth2_get_auth_headers(self):
        """测试OAuth2获取认证头"""
        from src.real_api.auth import OAuth2Provider

        provider = OAuth2Provider(
            token_url="https://api.example.com/oauth/token",
            client_id="test_client",
            client_secret="test_secret",
            pre_access_token="test_access_token",
        )

        headers = provider.get_auth_headers()
        assert headers == {"Authorization": "Bearer test_access_token"}

    def test_create_auth_provider_api_key(self):
        """测试创建API Key认证提供者"""
        from src.real_api.auth import create_auth_provider

        config = {"auth_type": "api_key", "api_key": "my_api_key"}
        provider = create_auth_provider(config)

        assert provider.get_access_token() == "my_api_key"

    def test_create_auth_provider_oauth2(self):
        """测试创建OAuth2认证提供者"""
        from src.real_api.auth import create_auth_provider

        config = {
            "auth_type": "oauth2",
            "oauth_token_url": "https://api.example.com/token",
            "oauth_client_id": "client_123",
            "oauth_client_secret": "secret_456",
        }
        provider = create_auth_provider(config)

        assert provider.client_id == "client_123"
        assert provider.client_secret == "secret_456"


class TestAuthManagerRefresh:
    """AuthManager refresh_token 测试"""

    def test_auth_manager_create_and_refresh_token(self, tmp_path):
        """测试AuthManager创建和刷新token"""
        from src.api.auth import AuthManager, User

        # 使用临时文件
        users_file = tmp_path / "users.json"
        secret_file = tmp_path / "secret.key"
        users_file.write_text("{}")

        manager = AuthManager(users_file=users_file, secret_file=secret_file)

        # 创建测试用户
        user = User(
            user_id="test_user",
            username="testuser",
            password_hash="hash",
            password_salt="salt",
            role="user",
        )

        # 创建token
        access_token, refresh_token = manager.create_token(user)
        assert access_token is not None
        assert refresh_token is not None

        # 使用refresh_token刷新
        new_tokens = manager.refresh_access_token(refresh_token)
        assert new_tokens is not None
        new_access, new_refresh = new_tokens
        assert new_access != access_token
        assert new_refresh != refresh_token

    def test_auth_manager_refresh_with_revoked_token(self, tmp_path):
        """测试AuthManager使用已撤销的refresh_token"""
        from src.api.auth import AuthManager, User

        users_file = tmp_path / "users.json"
        secret_file = tmp_path / "secret.key"
        users_file.write_text("{}")

        manager = AuthManager(users_file=users_file, secret_file=secret_file)

        user = User(
            user_id="test_user",
            username="testuser",
            password_hash="hash",
            password_salt="salt",
            role="user",
        )

        access_token, refresh_token = manager.create_token(user)

        # 撤销refresh_token
        manager.revoke_token(refresh_token)

        # 尝试使用已撤销的token刷新
        result = manager.refresh_access_token(refresh_token)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
