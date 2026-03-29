"""测试 RealAPI OAuth2 认证 (第15轮 P0-3)

验证 OAuth2Provider 支持多种 grant_type 及 refresh_token 刷新
"""
import pytest
import time
from unittest.mock import patch, AsyncMock, MagicMock

from src.real_api.auth import OAuth2Provider, APIKeyProvider, create_auth_provider
from src.real_api.config import RealAPIConfig


class TestOAuth2Provider:
    """OAuth2Provider 测试"""

    def test_client_credentials_grant(self):
        """client_credentials 授权流"""
        provider = OAuth2Provider(
            token_url="https://example.com/token",
            client_id="test-client",
            client_secret="test-secret",
            grant_type="client_credentials",
            timeout=10,
        )
        assert provider.grant_type == "client_credentials"
        assert not provider.is_token_valid()

    def test_authorization_code_grant_with_pre_tokens(self):
        """authorization_code 流：使用预置token"""
        provider = OAuth2Provider(
            token_url="https://example.com/token",
            client_id="test-client",
            client_secret="test-secret",
            grant_type="authorization_code",
            pre_access_token="pre-access-token-123",
            pre_refresh_token="pre-refresh-token-456",
            timeout=10,
        )
        assert provider._access_token == "pre-access-token-123"
        assert provider._refresh_token == "pre-refresh-token-456"
        assert provider.is_token_valid()  # 有预置token，在有效期内

    def test_refresh_token_grant_without_refresh_token_cannot_refresh(self):
        """refresh_token grant_type 无预置refresh_token时，token过期后无法刷新"""
        provider = OAuth2Provider(
            token_url="https://example.com/token",
            client_id="test-client",
            client_secret="test-secret",
            grant_type="refresh_token",
            pre_access_token="pre-access-token",
            pre_refresh_token="",  # 空
            timeout=10,
        )
        # 有pre_access_token所以当前有效
        assert provider.is_token_valid()
        # 强制使token过期
        provider._token_expires_at = time.time() - 1
        assert not provider.is_token_valid()
        # 过期后尝试获取token会失败（因为没有refresh_token）
        with pytest.raises(ValueError, match="没有预置的refresh_token"):
            provider.get_access_token()

    def test_get_access_token_client_credentials_raises_without_secret(self):
        """client_credentials 缺少secret时抛出错误"""
        provider = OAuth2Provider(
            token_url="https://example.com/token",
            client_id="test-client",
            client_secret="",  # 空
            grant_type="client_credentials",
        )
        with pytest.raises(ValueError, match="client_id"):
            provider.get_access_token()

    def test_grant_type_attribute(self):
        """验证 grant_type 属性正确传递"""
        provider = OAuth2Provider(
            token_url="https://example.com/token",
            client_id="test-client",
            client_secret="test-secret",
            grant_type="authorization_code",
        )
        assert provider.grant_type == "authorization_code"


class TestAPIKeyProvider:
    """APIKeyProvider 测试"""

    def test_api_key_valid(self):
        provider = APIKeyProvider(api_key="test-key-123", header_name="X-API-Key")
        assert provider.is_token_valid()
        assert provider.get_access_token() == "test-key-123"
        assert provider.get_auth_headers() == {"X-API-Key": "test-key-123"}

    def test_api_key_auth_header(self):
        provider = APIKeyProvider(api_key="test-key-456", header_name="Authorization")
        assert provider.get_auth_headers() == {"Authorization": "ApiKey test-key-456"}

    @pytest.mark.asyncio
    async def test_api_key_refresh_token_noop(self):
        """API Key 的 refresh_token 是空操作"""
        provider = APIKeyProvider(api_key="test-key")
        result = await provider.refresh_token()
        assert result["access_token"] == "test-key"
        assert result["token_type"] == "ApiKey"


class TestCreateAuthProvider:
    """create_auth_provider 工厂函数测试"""

    def test_creates_api_key_provider(self):
        provider = create_auth_provider({"auth_type": "api_key", "api_key": "key-123"})
        assert isinstance(provider, APIKeyProvider)
        assert provider.get_access_token() == "key-123"

    def test_creates_oauth2_provider(self):
        provider = create_auth_provider({
            "auth_type": "oauth2",
            "oauth_token_url": "https://example.com/token",
            "oauth_client_id": "client-id",
            "oauth_client_secret": "client-secret",
            "oauth_scope": "read write",
            "oauth2_grant_type": "client_credentials",
        })
        assert isinstance(provider, OAuth2Provider)
        assert provider.grant_type == "client_credentials"
        assert provider.client_id == "client-id"

    def test_creates_oauth2_with_grant_type(self):
        provider = create_auth_provider({
            "auth_type": "oauth2",
            "oauth_token_url": "https://example.com/token",
            "oauth_client_id": "client-id",
            "oauth_client_secret": "client-secret",
            "oauth2_grant_type": "authorization_code",
            "oauth2_access_token": "initial-access",
            "oauth2_refresh_token": "initial-refresh",
        })
        assert isinstance(provider, OAuth2Provider)
        assert provider.grant_type == "authorization_code"
        assert provider._access_token == "initial-access"
        assert provider._refresh_token == "initial-refresh"


class TestRealAPIConfigOAuth2:
    """RealAPIConfig OAuth2 字段测试"""

    def test_oauth2_grant_type_default(self):
        config = RealAPIConfig()
        assert config.oauth2_grant_type == "client_credentials"

    def test_oauth2_pre_tokens_default_empty(self):
        config = RealAPIConfig()
        assert config.oauth2_access_token == ""
        assert config.oauth2_refresh_token == ""

    def test_oauth2_fields_env_override(self, monkeypatch):
        monkeypatch.setenv("ZCLOUD_AUTH_TYPE", "oauth2")
        monkeypatch.setenv("ZCLOUD_OAUTH2_GRANT_TYPE", "authorization_code")
        monkeypatch.setenv("ZCLOUD_OAUTH2_ACCESS_TOKEN", "env-access-token")
        monkeypatch.setenv("ZCLOUD_OAUTH2_REFRESH_TOKEN", "env-refresh-token")
        config = RealAPIConfig()
        assert config.auth_type == "oauth2"
        assert config.oauth2_grant_type == "authorization_code"
        assert config.oauth2_access_token == "env-access-token"
        assert config.oauth2_refresh_token == "env-refresh-token"


class TestOAuth2ProviderRefreshToken:
    """OAuth2 refresh_token 异步刷新测试"""

    @pytest.mark.asyncio
    async def test_refresh_token_success(self):
        provider = OAuth2Provider(
            token_url="https://example.com/token",
            client_id="test-client",
            client_secret="test-secret",
            grant_type="client_credentials",
            pre_refresh_token="old-refresh-token",
        )
        provider._access_token = "old-access-token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 7200,
            "token_type": "Bearer",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client

            result = await provider.refresh_token()

        assert result["access_token"] == "new-access-token"
        assert result["refresh_token"] == "new-refresh-token"
        assert provider._access_token == "new-access-token"
        assert provider._refresh_token == "new-refresh-token"

    @pytest.mark.asyncio
    async def test_refresh_token_no_token_error(self):
        provider = OAuth2Provider(
            token_url="https://example.com/token",
            client_id="test-client",
            client_secret="test-secret",
            grant_type="client_credentials",
        )
        # 没有refresh_token
        result = await provider.refresh_token()
        assert "error" in result
        assert result["error"] == "no_refresh_token"

    @pytest.mark.asyncio
    async def test_refresh_token_custom_token(self):
        provider = OAuth2Provider(
            token_url="https://example.com/token",
            client_id="test-client",
            client_secret="test-secret",
            grant_type="client_credentials",
            pre_refresh_token="stored-refresh",
        )
        provider._access_token = "old-access"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_async_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_async_client.return_value.__aenter__.return_value = mock_client

            # 使用自定义refresh_token覆盖
            result = await provider.refresh_token(refresh_token="custom-refresh-token")

        assert result["access_token"] == "new-access"
        # provider内部存储的_refresh_token被更新
        assert provider._refresh_token == "new-refresh"
