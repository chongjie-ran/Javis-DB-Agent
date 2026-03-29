"""消息通道基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
import time


@dataclass
class ChannelMessage:
    """通道消息"""
    message_id: str
    channel: str               # email/wecom/feishu/...
    user_id: str               # 用户标识
    session_id: Optional[str]   # 会话ID
    content: str                # 消息内容
    metadata: dict = field(default_factory=dict)  # 通道特有元数据
    timestamp: float = field(default_factory=time.time)


@dataclass
class ChannelResponse:
    """通道响应"""
    success: bool
    message: str = ""
    data: Any = None
    error: str = ""
    metadata: dict = field(default_factory=dict)


class BaseChannel(ABC):
    """消息通道基类"""

    channel_name: str = "base"

    @abstractmethod
    async def receive(self) -> list[ChannelMessage]:
        """接收消息"""
        pass

    @abstractmethod
    async def send(
        self,
        user_id: str,
        content: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> ChannelResponse:
        """发送消息"""
        pass

    @abstractmethod
    def map_session(self, channel_thread_id: str) -> Optional[str]:
        """映射邮件线程到会话ID"""
        pass

    @abstractmethod
    def save_mapping(self, thread_id: str, session_id: str):
        """保存线程-会话映射"""
        pass
