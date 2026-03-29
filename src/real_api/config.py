"""Real API 配置"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional


class RealAPIConfig(BaseSettings):
    """真实Javis API配置"""
    
    # API基础地址
    base_url: str = "https://javis-db.example.com/api/v1"
    
    # 认证方式: "oauth2" | "api_key"
    auth_type: str = "api_key"
    
    # OAuth2配置
    oauth_token_url: str = "https://javis-db.example.com/oauth/token"
    oauth_authorize_url: str = "https://javis-db.example.com/oauth/authorize"
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_scope: str = "read write"
    # OAuth2授权类型: "client_credentials" | "authorization_code" | "refresh_token"
    # - client_credentials: 使用client_id/secret直接获取token（无refresh_token）
    # - authorization_code: 使用授权码获取token（有refresh_token可用）
    # - refresh_token: 仅使用已有的refresh_token刷新（需要预先获取）
    oauth2_grant_type: str = "client_credentials"
    # 预置的access_token（用于 refresh_token grant type）
    oauth2_access_token: str = ""
    # 预置的refresh_token（用于 refresh_token grant type）
    oauth2_refresh_token: str = ""
    
    # API Key配置
    api_key: str = ""
    api_key_header: str = "X-API-Key"  # 或 "Authorization" (ApiKey前缀)
    
    # 连接配置
    timeout: int = 30
    max_retries: int = 3
    
    # Mock开关（运行时可覆盖）
    use_mock: bool = True
    
    model_config = ConfigDict(
        env_prefix="ZCLOUD_",
        env_file=".env",
        env_file_encoding="utf-8"
    )


_config: Optional[RealAPIConfig] = None


def get_real_api_config() -> RealAPIConfig:
    global _config
    if _config is None:
        _config = RealAPIConfig()
    return _config


def reload_real_api_config():
    global _config
    _config = RealAPIConfig()

