"""Real API 配置"""
from pydantic_settings import BaseSettings
from typing import Optional


class RealAPIConfig(BaseSettings):
    """真实zCloud API配置"""
    
    # API基础地址
    base_url: str = "https://zcloud.example.com/api/v1"
    
    # 认证方式: "oauth2" | "api_key"
    auth_type: str = "api_key"
    
    # OAuth2配置
    oauth_token_url: str = "https://zcloud.example.com/oauth/token"
    oauth_authorize_url: str = "https://zcloud.example.com/oauth/authorize"
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_scope: str = "read write"
    
    # API Key配置
    api_key: str = ""
    api_key_header: str = "X-API-Key"  # 或 "Authorization" (ApiKey前缀)
    
    # 连接配置
    timeout: int = 30
    max_retries: int = 3
    
    # Mock开关（运行时可覆盖）
    use_mock: bool = True
    
    class Config:
        env_prefix = "ZCLOUD_"
        env_file = ".env"
        env_file_encoding = "utf-8"


_config: Optional[RealAPIConfig] = None


def get_real_api_config() -> RealAPIConfig:
    global _config
    if _config is None:
        _config = RealAPIConfig()
    return _config


def reload_real_api_config():
    global _config
    _config = RealAPIConfig()
