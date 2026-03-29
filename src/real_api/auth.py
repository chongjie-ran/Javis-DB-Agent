"""真实API认证模块"""
import time
import httpx
from abc import ABC, abstractmethod
from typing import Optional


class AuthProvider(ABC):
    """认证提供者抽象接口"""
    
    @abstractmethod
    def get_access_token(self) -> str:
        """获取访问令牌"""
        pass
    
    @abstractmethod
    async def refresh_token(self, refresh_token: Optional[str] = None) -> dict:
        """刷新令牌（RFC6749）"""
        pass
    
    @abstractmethod
    def is_token_valid(self) -> bool:
        """检查令牌是否有效"""
        pass
    
    @abstractmethod
    def get_auth_headers(self) -> dict:
        """获取认证HTTP Headers"""
        pass


class OAuth2Provider(AuthProvider):
    """OAuth2.0认证提供者"""
    
    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str = "read write",
        timeout: int = 30,
    ):
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.timeout = timeout
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: float = 0
    
    def get_access_token(self) -> str:
        """获取访问令牌（自动刷新）"""
        if not self.is_token_valid():
            if self._refresh_token:
                self._refresh()
            else:
                self._authorize()
        return self._access_token
    
    def _authorize(self) -> None:
        """授权获取Token"""
        if not self.client_id or not self.client_secret:
            raise ValueError("OAuth2 client_id 或 client_secret 未配置")
        
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": self.scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()
            self._access_token = data["access_token"]
            self._refresh_token = data.get("refresh_token")
            expires_in = data.get("expires_in", 3600)
            self._token_expires_at = time.time() + expires_in - 60  # 提前60秒过期
    
    def _refresh(self) -> bool:
        """刷新Token"""
        if not self._refresh_token:
            return False
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                data = response.json()
                self._access_token = data["access_token"]
                self._refresh_token = data.get("refresh_token", self._refresh_token)
                expires_in = data.get("expires_in", 3600)
                self._token_expires_at = time.time() + expires_in - 60
                return True
        except Exception:
            return False
    
    def is_token_valid(self) -> bool:
        if not self._access_token:
            return False
        return time.time() < self._token_expires_at
    
    async def refresh_token(self, refresh_token: Optional[str] = None) -> dict:
        """
        使用refresh_token换取新的access_token（RFC6749标准流程）。

        Args:
            refresh_token: 可选的refresh_token。如果不提供，使用实例中存储的_refresh_token。

        Returns:
            dict: 包含以下键的token响应：
                - access_token: 新的访问令牌
                - refresh_token: 新的刷新令牌（如果有）
                - expires_in: 过期时间（秒）
                - token_type: 令牌类型（通常为"Bearer"）
        """
        token_to_use = refresh_token or self._refresh_token
        if not token_to_use:
            return {"error": "no_refresh_token", "error_description": "没有可用的refresh_token"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": token_to_use,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                data = response.json()

                # 更新存储的token
                self._access_token = data["access_token"]
                self._refresh_token = data.get("refresh_token", self._refresh_token)
                expires_in = data.get("expires_in", 3600)
                self._token_expires_at = time.time() + expires_in - 60  # 提前60秒

                return data
        except httpx.HTTPStatusError as e:
            return {
                "error": "token_refresh_failed",
                "error_description": f"HTTP {e.response.status_code}: {e.response.text}"
            }
        except Exception as e:
            return {"error": "token_refresh_failed", "error_description": str(e)}
    
    def get_auth_headers(self) -> dict:
        token = self.get_access_token()
        return {"Authorization": f"Bearer {token}"}


class APIKeyProvider(AuthProvider):
    """API Key认证提供者"""
    
    def __init__(self, api_key: str, header_name: str = "X-API-Key"):
        self._api_key = api_key
        self._header_name = header_name
    
    def get_access_token(self) -> str:
        return self._api_key
    
    async def refresh_token(self, refresh_token: Optional[str] = None) -> dict:
        # API Key 不需要刷新，直接返回成功
        return {"access_token": self._api_key, "token_type": "ApiKey"}
    
    def is_token_valid(self) -> bool:
        return bool(self._api_key)
    
    def get_auth_headers(self) -> dict:
        if self._header_name == "Authorization":
            return {"Authorization": f"ApiKey {self._api_key}"}
        return {self._header_name: self._api_key}


def create_auth_provider(config: dict) -> AuthProvider:
    """根据配置创建认证提供者"""
    auth_type = config.get("auth_type", "api_key")
    
    if auth_type == "oauth2":
        return OAuth2Provider(
            token_url=config.get("oauth_token_url", ""),
            client_id=config.get("oauth_client_id", ""),
            client_secret=config.get("oauth_client_secret", ""),
            scope=config.get("oauth_scope", "read write"),
            timeout=config.get("timeout", 30),
        )
    else:
        return APIKeyProvider(
            api_key=config.get("api_key", ""),
            header_name=config.get("api_key_header", "X-API-Key"),
        )
