"""企业微信通道配置"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class WecomChannelConfig(BaseSettings):
    """企业微信通道配置"""

    # ===== 企微应用凭证 =====
    # 企业ID
    corp_id: str = ""
    # 应用AgentId
    agent_id: int = 0
    # 应用Secret
    corp_secret: str = ""

    # ===== 回调配置 =====
    # 企微回调URL（zCloud暴露给企微的webhook地址）
    callback_url: str = "http://localhost:8000/api/v1/channels/wecom/callback"
    # 回调Token（用于验证签名）
    callback_token: str = ""
    # 回调EncodingAESKey（用于消息加解密）
    callback_aes_key: str = ""

    # ===== API配置 =====
    # 企微API基础地址
    api_base_url: str = "https://qyapi.weixin.qq.com"
    # API请求超时（秒）
    api_timeout: int = 30

    # ===== 消息配置 =====
    # 是否启用企微通道
    enabled: bool = False
    # 消息最大长度
    max_message_length: int = 2048
    # 是否启用会话管理
    session_enabled: bool = True
    # 会话TTL（秒）
    session_ttl_seconds: int = 86400
    # 是否自动创建会话
    auto_create_session: bool = True

    # ===== 告警配置 =====
    # 告警推送目标（群ID或用户userid）
    alert_target: str = ""
    # 是否自动推送告警通知
    alert_push_enabled: bool = False

    # ===== 限流配置 =====
    # 消息发送限流（条/秒）
    send_rate_limit: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "WECOM_"
        extra = "allow"


# 全局单例
_wecom_config: Optional[WecomChannelConfig] = None


def get_wecom_config() -> WecomChannelConfig:
    global _wecom_config
    if _wecom_config is None:
        _wecom_config = WecomChannelConfig()
    return _wecom_config


def reload_wecom_config():
    global _wecom_config
    _wecom_config = WecomChannelConfig()
