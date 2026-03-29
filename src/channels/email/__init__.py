"""Email 消息通道"""
from src.channels.email.client import EmailClient
from src.channels.email.message_handler import EmailMessageHandler
from src.channels.email.models import EmailMessage, EmailThread

__all__ = [
    "EmailClient",
    "EmailMessageHandler",
    "EmailMessage",
    "EmailThread",
]
