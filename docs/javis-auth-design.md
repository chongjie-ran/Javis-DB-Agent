# Javis-DB-Agent 认证机制设计草案

> 版本：v1.0 | 日期：2026-03-28 | 作者：悟通

---

## 一、背景

Javis-DB-Agent 智能体系统需要与真实的 Javis-DB-Agent 平台对接，需要设计一套统一的认证框架，支持：
- OAuth2.0 授权码模式（用户授权场景）
- API Key 认证（机器到机器场景）
- Token 自动刷新机制
- Mock/Real 模式切换

---

## 二、认证框架设计

### 2.1 认证接口抽象

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from enum import Enum
import time


class AuthType(Enum):
    """认证类型枚举"""
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    MOCK = "mock"


@dataclass
class TokenInfo:
    """Token 信息"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: Optional[str] = None
    scope: str = "read write"
    obtained_at: float = 0.0
    
    def __post_init__(self):
        if self.obtained_at == 0.0:
            self.obtained_at = time.time()
    
    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """检查 token 是否过期（预留 buffer）"""
        return time.time() > self.obtained_at + self.expires_in - buffer_seconds
    
    def expires_soon(self, buffer_seconds: int = 300) -> bool:
        """检查 token 是否即将过期（5分钟前预警）"""
        return time.time() > self.obtained_at + self.expires_in - buffer_seconds


class AuthProvider(ABC):
    """认证提供者抽象接口"""
    
    @abstractmethod
    def get_auth_type(self) -> AuthType:
        """获取认证类型"""
        pass
    
    @abstractmethod
    def get_token(self) -> str:
        """获取当前有效 token"""
        pass
    
    @abstractmethod
    def refresh_if_needed(self) -> bool:
        """必要时刷新 token"""
        pass
    
    @abstractmethod
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        pass
    
    @abstractmethod
    def get_auth_headers(self) -> dict:
        """获取认证 HTTP Headers"""
        pass


class OAuth2Provider(AuthProvider):
    """OAuth2.0 认证提供者"""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_url: str,
        authorization_url: str,
        redirect_uri: str,
        scope: str = "read write",
        verify_ssl: bool = True
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.authorization_url = authorization_url
        self.redirect_uri = redirect_uri
        self.scope = scope
        self.verify_ssl = verify_ssl
        
        self._token: Optional[TokenInfo] = None
        self._code: Optional[str] = None
    
    def get_auth_type(self) -> AuthType:
        return AuthType.OAUTH2
    
    def get_authorization_url(self) -> str:
        """获取授权 URL（用于用户访问）"""
        import urllib.parse
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scope
        }
        return f"{self.authorization_url}?{urllib.parse.urlencode(params)}"
    
    def exchange_code_for_token(self, code: str) -> TokenInfo:
        """用授权码换取 token"""
        import requests
        response = requests.post(
            self.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri
            },
            verify=self.verify_ssl,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        self._token = TokenInfo(
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in", 3600),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope", self.scope)
        )
        return self._token
    
    def get_token(self) -> str:
        """获取有效 token（自动刷新）"""
        if not self._token or self._token.is_expired():
            self.refresh_if_needed()
        return self._token.access_token
    
    def refresh_if_needed(self) -> bool:
        """刷新 token"""
        if not self._token:
            return False
        
        if not self._token.refresh_token:
            return False
        
        import requests
        try:
            response = requests.post(
                self.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._token.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                },
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            self._token = TokenInfo(
                access_token=data["access_token"],
                token_type=data.get("token_type", "Bearer"),
                expires_in=data.get("expires_in", 3600),
                refresh_token=data.get("refresh_token", self._token.refresh_token),
                scope=data.get("scope", self.scope)
            )
            return True
        except Exception:
            return False
    
    def is_authenticated(self) -> bool:
        return self._token is not None and not self._token.is_expired()
    
    def get_auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.get_token()}"
        }


class APIKeyProvider(AuthProvider):
    """API Key 认证提供者"""
    
    def __init__(self, api_key: str, header_name: str = "X-API-Key"):
        self._api_key = api_key
        self._header_name = header_name
    
    def get_auth_type(self) -> AuthType:
        return AuthType.API_KEY
    
    def get_token(self) -> str:
        return self._api_key
    
    def refresh_if_needed(self) -> bool:
        return True  # API Key 不需要刷新
    
    def is_authenticated(self) -> bool:
        return bool(self._api_key)
    
    def get_auth_headers(self) -> dict:
        return {
            self._header_name: self._api_key
        }


class MockAuthProvider(AuthProvider):
    """Mock 认证提供者（用于开发和测试）"""
    
    def __init__(self):
        self._token = TokenInfo(
            access_token="mock_token_12345",
            token_type="Bearer",
            expires_in=999999,
            scope="read write"
        )
    
    def get_auth_type(self) -> AuthType:
        return AuthType.MOCK
    
    def get_token(self) -> str:
        return self._token.access_token
    
    def refresh_if_needed(self) -> bool:
        return True
    
    def is_authenticated(self) -> bool:
        return True
    
    def get_auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token.access_token}"
        }
```

### 2.2 认证管理器

```python
from typing import Optional
from dataclasses import dataclass


@dataclass
class AuthConfig:
    """认证配置"""
    auth_type: AuthType
    # OAuth2 配置
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    token_url: Optional[str] = None
    authorization_url: Optional[str] = None
    redirect_uri: Optional[str] = None
    scope: str = "read write"
    # API Key 配置
    api_key: Optional[str] = None
    api_key_header: str = "X-API-Key"


class AuthManager:
    """认证管理器"""
    
    _instance: Optional['AuthManager'] = None
    
    def __init__(self, config: AuthConfig):
        self.config = config
        self._provider: Optional[AuthProvider] = None
        self._init_provider()
    
    def _init_provider(self):
        """根据配置初始化认证提供者"""
        if self.config.auth_type == AuthType.OAUTH2:
            self._provider = OAuth2Provider(
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                token_url=self.config.token_url,
                authorization_url=self.config.authorization_url,
                redirect_uri=self.config.redirect_uri,
                scope=self.config.scope
            )
        elif self.config.auth_type == AuthType.API_KEY:
            self._provider = APIKeyProvider(
                api_key=self.config.api_key,
                header_name=self.config.api_key_header
            )
        else:
            self._provider = MockAuthProvider()
    
    @classmethod
    def get_instance(cls, config: Optional[AuthConfig] = None) -> 'AuthManager':
        """获取单例"""
        if cls._instance is None and config:
            cls._instance = cls(config)
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """重置单例（用于切换配置）"""
        cls._instance = None
    
    def get_provider(self) -> AuthProvider:
        """获取认证提供者"""
        return self._provider
    
    def get_headers(self) -> dict:
        """获取认证头"""
        return self._provider.get_auth_headers()
```

---

## 三、客户端集成

### 3.1 统一客户端接口

```python
from typing import Protocol, Optional


class ZCloudClientProtocol(Protocol):
    """Javis-DB-Agent 客户端协议"""
    
    async def get_instance(self, instance_id: str) -> dict:
        """获取实例详情"""
        ...
    
    async def get_alerts(
        self,
        instance_id: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> list[dict]:
        """获取告警列表"""
        ...
    
    # ... 其他方法


class RealZCloudClient:
    """真实 Javis-DB-Agent API 客户端"""
    
    def __init__(
        self,
        base_url: str,
        auth_provider: AuthProvider,
        timeout: int = 30,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_provider = auth_provider
        self.timeout = timeout
        self.max_retries = max_retries
    
    def _get_headers(self) -> dict:
        return {
            **self.auth_provider.get_auth_headers(),
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def _request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> dict:
        import requests
        import asyncio
        
        url = f"{self.base_url}{path}"
        headers = self._get_headers()
        kwargs.setdefault("timeout", self.timeout)
        
        loop = asyncio.get_event_loop()
        
        def _do_request():
            return requests.request(
                method=method,
                url=url,
                headers=headers,
                **kwargs
            )
        
        # 异步执行HTTP请求
        response = await loop.run_in_executor(None, _do_request)
        
        if response.status_code == 429:
            raise RateLimitError(response.json())
        
        response.raise_for_status()
        return response.json()
    
    async def get_instance(self, instance_id: str) -> dict:
        return await self._request("GET", f"/instances/{instance_id}")
    
    async def get_alerts(
        self,
        instance_id: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> list[dict]:
        params = {"limit": limit}
        if instance_id:
            params["instance_id"] = instance_id
        if severity:
            params["severity"] = severity
        if status:
            params["status"] = status
        
        result = await self._request("GET", "/alerts", params=params)
        return result.get("data", [])
```

### 3.2 工厂模式

```python
class ZCloudClientFactory:
    """Javis-DB-Agent 客户端工厂"""
    
    @staticmethod
    def create(
        use_mock: bool = True,
        # Mock 配置
        mock_host: str = "localhost",
        mock_port: int = 18080,
        # Real 配置
        real_base_url: Optional[str] = None,
        auth_config: Optional[AuthConfig] = None,
        timeout: int = 30
    ) -> ZCloudClientProtocol:
        """
        创建客户端
        
        Args:
            use_mock: 是否使用 Mock 客户端
            mock_host: Mock 服务地址
            mock_port: Mock 服务端口
            real_base_url: 真实 API 地址
            auth_config: 认证配置
            timeout: 请求超时时间
        """
        if use_mock:
            from mock_javis_api.javis_client import get_mock_javis_client
            return get_mock_javis_client()
        else:
            if not real_base_url:
                raise ValueError("real_base_url is required when use_mock=False")
            if not auth_config:
                raise ValueError("auth_config is required when use_mock=False")
            
            auth_provider = AuthManager(auth_config).get_provider()
            return RealZCloudClient(
                base_url=real_base_url,
                auth_provider=auth_provider,
                timeout=timeout
            )
```

---

## 四、使用示例

### 4.1 Mock 模式（开发/测试）

```python
# 配置文件
config = {
    "use_mock": True,
    "mock_host": "localhost",
    "mock_port": 18080
}

# 创建客户端
client = ZCloudClientFactory.create(**config)
alerts = await client.get_alerts()
```

### 4.2 API Key 模式（生产环境）

```python
# 配置文件
config = {
    "use_mock": False,
    "real_base_url": "https://javis-db.example.com/api/v1",
    "auth_config": AuthConfig(
        auth_type=AuthType.API_KEY,
        api_key="your-api-key-here"
    )
}

# 创建客户端
client = ZCloudClientFactory.create(**config)
alerts = await client.get_alerts()
```

### 4.3 OAuth2 模式（用户授权场景）

```python
# 初始化
auth_config = AuthConfig(
    auth_type=AuthType.OAUTH2,
    client_id="your-client-id",
    client_secret="your-client-secret",
    token_url="https://javis-db.example.com/oauth/token",
    authorization_url="https://javis-db.example.com/oauth/authorize",
    redirect_uri="http://localhost:8080/callback",
    scope="read write"
)

auth_manager = AuthManager(auth_config)

# 获取授权 URL
auth_url = auth_manager.get_provider().get_authorization_url()
print(f"Please visit: {auth_url}")

# 用户授权后，用返回的 code 换取 token
code = "returned_authorization_code"
auth_manager.get_provider().exchange_code_for_token(code)

# 创建客户端
client = ZCloudClientFactory.create(
    use_mock=False,
    real_base_url="https://javis-db.example.com/api/v1",
    auth_config=auth_config
)
```

---

## 五、配置管理

### 5.1 环境变量配置

```python
import os


def load_auth_config_from_env() -> Optional[AuthConfig]:
    """从环境变量加载认证配置"""
    auth_type = os.getenv("ZCLOUD_AUTH_TYPE", "mock")
    
    if auth_type == "oauth2":
        return AuthConfig(
            auth_type=AuthType.OAUTH2,
            client_id=os.getenv("ZCLOUD_CLIENT_ID"),
            client_secret=os.getenv("ZCLOUD_CLIENT_SECRET"),
            token_url=os.getenv("ZCLOUD_TOKEN_URL"),
            authorization_url=os.getenv("ZCLOUD_AUTH_URL"),
            redirect_uri=os.getenv("ZCLOUD_REDIRECT_URI"),
            scope=os.getenv("ZCLOUD_SCOPE", "read write")
        )
    elif auth_type == "api_key":
        return AuthConfig(
            auth_type=AuthType.API_KEY,
            api_key=os.getenv("ZCLOUD_API_KEY"),
            api_key_header=os.getenv("ZCLOUD_API_KEY_HEADER", "X-API-Key")
        )
    else:
        return None  # 使用 Mock
```

### 5.2 配置文件格式

```yaml
# config.yaml
javis-db:
  use_mock: false
  base_url: https://javis-db.example.com/api/v1
  
  auth:
    type: api_key  # oauth2, api_key, mock
    api_key: ${ZCLOUD_API_KEY}
    # oauth2:
    #   client_id: ${ZCLOUD_CLIENT_ID}
    #   client_secret: ${ZCLOUD_CLIENT_SECRET}
    #   token_url: ${ZCLOUD_TOKEN_URL}
    #   authorization_url: ${ZCLOUD_AUTH_URL}
    #   redirect_uri: ${ZCLOUD_REDIRECT_URI}
    #   scope: read write

  timeout: 30
  max_retries: 3
```

---

## 六、后续计划

### 6.1 实现阶段

| 阶段 | 任务 | 状态 |
|------|------|------|
| 1 | 定义认证接口和模型 | ✅ 已完成 |
| 2 | 实现 Mock/Real 切换工厂 | ✅ 已完成 |
| 3 | 实现 OAuth2Provider | ✅ 已完成 |
| 4 | 实现 Token 自动刷新 | ✅ 已完成 |
| 5 | 集成到客户端 | 🔄 待实现 |
| 6 | 添加配置管理 | 🔄 待实现 |

### 6.2 待接入真实环境

1. 获取 Javis-DB-Agent 平台的 OAuth2.0 凭证
2. 配置生产环境的 token URL
3. 完善 token 刷新失败的处理逻辑
4. 添加 token 缓存到文件系统

---

*文档版本：v1.0 | 最后更新：2026-03-28*
