"""Javis-DB-Agent 消息通道"""
from src.channels.base import BaseChannel, ChannelMessage, ChannelResponse
from src.channels.email.client import EmailClient
from src.channels.email.message_handler import EmailChannel, EmailMessageHandler, EmailChannelConfig
from src.channels.email.models import EmailMessage, EmailThread

# 飞书通道 (已存在)
from src.channels.feishu.message_handler import FeishuMessageHandler
from src.channels.feishu.sender import FeishuSender
from src.channels.feishu.session_mapper import FeishuSessionMapper

__all__ = [
    # 基础
    "BaseChannel",
    "ChannelMessage",
    "ChannelResponse",
    # Email通道
    "EmailClient",
    "EmailChannel",
    "EmailMessageHandler",
    "EmailChannelConfig",
    "EmailMessage",
    "EmailThread",
    # 飞书通道
    "FeishuMessageHandler",
    "FeishuSender",
    "FeishuSessionMapper",
]
