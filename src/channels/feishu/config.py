"""飞书通道配置"""
from typing import Optional
from pydantic import BaseModel, Field


class FeishuChannelConfig(BaseModel):
    """飞书通道配置"""

    # 连接模式: "websocket" | "webhook"
    connection_mode: str = Field(default="websocket", description="连接模式")

    # Webhook配置（webhook模式）
    webhook_port: Optional[int] = Field(default=None, description="Webhook服务端口")
    webhook_path: str = Field(default="/feishu/webhook", description="Webhook路径")
    webhook_verify_token: Optional[str] = Field(default=None, description="飞书验签Token")
    webhook_encrypt_key: Optional[str] = Field(default=None, description="飞书加密Key")

    # 飞书应用凭证
    app_id: str = Field(default="", description="飞书 App ID")
    app_secret: str = Field(default="", description="飞书 App Secret")

    # Bot配置
    bot_name: str = Field(default="Javis-DB-Agent Agent", description="Bot名称")

    # 会话管理
    session_ttl_seconds: int = Field(default=86400, description="会话TTL（秒）")
    max_sessions_per_user: int = Field(default=10, description="单用户最大会话数")

    # 消息去重
    dedup_ttl_ms: int = Field(default=5000, description="消息去重TTL（毫秒）")

    # 允许的用户/群组
    allow_from: list[str] = Field(default_factory=list, description="允许的发送者列表（user_id或chat_id）")
    allow_from_all: bool = Field(default=True, description="是否允许所有用户")

    # 群组配置
    group_auto_join: bool = Field(default=False, description="是否自动加入群组")
    group_mention_only: bool = Field(default=True, description="是否仅响应@提及")

    # 流式响应
    streaming_enabled: bool = Field(default=True, description="是否启用流式响应")
    streaming_card_enabled: bool = Field(default=True, description="是否启用流式卡片")

    # 能力开关
    capability_text: bool = Field(default=True, description="支持文本消息")
    capability_card: bool = Field(default=True, description="支持卡片消息")
    capability_markdown: bool = Field(default=True, description="支持Markdown")
    capability_media: bool = Field(default=True, description="支持媒体消息")
    capability_reaction: bool = Field(default=True, description="支持表情反应")

    @property
    def is_configured(self) -> bool:
        """是否已配置"""
        return bool(self.app_id and self.app_secret)

    @property
    def is_webhook_mode(self) -> bool:
        """是否为Webhook模式"""
        return self.connection_mode == "webhook"

    @property
    def is_websocket_mode(self) -> bool:
        """是否为WebSocket模式"""
        return self.connection_mode == "websocket"

    model_config = {"extra": "allow"}
