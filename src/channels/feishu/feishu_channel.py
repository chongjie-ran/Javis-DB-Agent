"""飞书消息通道

统一入口：FeishuChannel 类负责启动和停止飞书消息通道。

支持两种连接模式：
1. WebSocket模式（推荐）：长连接，实时接收消息
2. Webhook模式：HTTP回调，需要公网入口
"""
import asyncio
import logging
import threading
from typing import Optional, Any
from dataclasses import dataclass

from src.channels.feishu.client import FeishuClient, get_feishu_client
from src.channels.feishu.config import FeishuChannelConfig
from src.channels.feishu.message_handler import FeishuMessageHandler, create_message_handler
from src.channels.feishu.session_mapper import FeishuSessionMapper, get_feishu_session_mapper

logger = logging.getLogger(__name__)


@dataclass
class FeishuChannelStatus:
    """通道状态"""
    running: bool = False
    mode: str = "websocket"
    account_id: str = "default"
    error: Optional[str] = None
    last_start_at: Optional[float] = None
    last_stop_at: Optional[float] = None


class FeishuChannel:
    """
    飞书消息通道

    负责：
    1. 管理WebSocket连接（或Webhook服务）
    2. 接收并处理飞书消息
    3. 将Agent响应发送回飞书
    4. 会话映射管理
    """

    def __init__(
        self,
        config: FeishuChannelConfig,
        account_id: str = "default",
    ):
        """
        Args:
            config: 飞书通道配置
            account_id: 账户标识
        """
        self.config = config
        self.account_id = account_id
        self.status = FeishuChannelStatus(mode=config.connection_mode, account_id=account_id)

        # 组件
        self._client: Optional[FeishuClient] = None
        self._handler: Optional[FeishuMessageHandler] = None
        self._session_mapper: Optional[FeishuSessionMapper] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._abort_signal: Optional[threading.Event] = None
        self._lock = threading.Lock()

    # ==================== 生命周期 ====================

    async def start(self):
        """启动飞书通道"""
        with self._lock:
            if self.status.running:
                logger.warning("飞书通道已在运行中")
                return

            try:
                logger.info(f"启动飞书通道 (mode={self.config.connection_mode})")

                # 1. 创建客户端
                self._client = get_feishu_client(
                    app_id=self.config.app_id,
                    app_secret=self.config.app_secret,
                )

                # 2. 创建会话映射器
                self._session_mapper = get_feishu_session_mapper(
                    ttl_seconds=self.config.session_ttl_seconds,
                    max_per_user=self.config.max_sessions_per_user,
                )

                # 3. 创建消息处理器
                self._handler = create_message_handler(
                    client=self._client,
                    config=self.config,
                    session_mapper=self._session_mapper,
                )

                # 4. 启动连接
                if self.config.is_websocket_mode:
                    await self._start_websocket()
                else:
                    await self._start_webhook()

                self.status.running = True
                self.status.last_start_at = None
                self.status.error = None
                logger.info("飞书通道启动成功")

            except Exception as e:
                self.status.error = str(e)
                logger.error(f"飞书通道启动失败: {e}", exc_info=True)
                raise

    async def stop(self):
        """停止飞书通道"""
        with self._lock:
            if not self.status.running:
                logger.warning("飞书通道未运行")
                return

            logger.info("停止飞书通道...")

            try:
                # 取消WebSocket任务
                if self._ws_task and not self._ws_task.done():
                    self._ws_task.cancel()
                    try:
                        await asyncio.wait_for(self._ws_task, timeout=5.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

                self.status.running = False
                self.status.last_stop_at = None
                logger.info("飞书通道已停止")

            except Exception as e:
                logger.error(f"停止飞书通道时出错: {e}", exc_info=True)
                self.status.error = str(e)

    # ==================== WebSocket模式 ====================

    async def _start_websocket(self):
        """启动WebSocket连接"""
        logger.info("启动WebSocket长连接...")

        try:
            # 探测Bot信息
            bot_info = await self._client.get_bot_info()
            logger.info(f"Bot信息: {bot_info}")
        except Exception as e:
            logger.warning(f"获取Bot信息失败: {e}")

        # 启动WebSocket客户端
        self._abort_signal = threading.Event()
        self._ws_task = asyncio.create_task(
            self._websocket_loop()
        )

    async def _websocket_loop(self):
        """WebSocket事件循环"""
        import httpx

        url = "https://open.feishu.cn/open-apis/event/v1/im/message/receive_v1"
        token = await self._client.get_tenant_access_token()

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                async with client.stream(
                    "GET",
                    url,
                    headers=headers,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line.strip():
                            try:
                                import json
                                data = json.loads(line)
                                await self._handler.handle_event(data)
                            except Exception as e:
                                logger.error(f"处理WebSocket消息失败: {e}")

            except asyncio.CancelledError:
                logger.info("WebSocket连接已取消")
                raise
            except Exception as e:
                logger.error(f"WebSocket连接错误: {e}", exc_info=True)
                raise

    # ==================== Webhook模式 ====================

    async def _start_webhook(self):
        """启动Webhook服务"""
        if not self.config.webhook_port:
            raise ValueError("Webhook模式需要配置webhook_port")

        from fastapi import FastAPI
        import uvicorn

        app = FastAPI()

        @app.post(self.config.webhook_path)
        async def feishu_webhook(request: dict, headers: dict):
            # 从headers获取X-Feishu相关头
            feishu_headers = {
                "X-Feishu-Encryption-Token": headers.get("X-Feishu-Encryption-Token", ""),
                "X-Feishu-Signature": headers.get("X-Feishu-Signature", ""),
            }
            return await self._handler.handle_webhook(request, feishu_headers)

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self.config.webhook_port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        self._ws_task = asyncio.create_task(server.serve())

    # ==================== 发送消息 ====================

    async def send_message(
        self,
        chat_id: str,
        text: str,
        msg_type: str = "text",
        reply_message_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        发送消息到飞书

        Args:
            chat_id: 飞书会话ID
            text: 消息内容
            msg_type: 消息类型 (text/post/interactive)
            reply_message_id: 回复的消息ID

        Returns:
            发送的消息ID
        """
        if not self._client or not self._handler:
            raise RuntimeError("通道未启动")

        sender = self._handler.sender

        if msg_type == "text":
            result = await sender.send_text(
                receive_id=chat_id,
                receive_id_type="chat_id",
                text=text,
                reply_message_id=reply_message_id,
            )
        elif msg_type == "post":
            result = await sender.send_markdown(
                receive_id=chat_id,
                receive_id_type="chat_id",
                markdown=text,
                reply_message_id=reply_message_id,
            )
        else:
            result = await sender.send_agent_response(
                receive_id=chat_id,
                receive_id_type="chat_id",
                text=text,
                reply_message_id=reply_message_id,
            )

        return result.message_id

    async def send_alert(
        self,
        chat_id: str,
        title: str,
        level: str = "info",
        content: str = "",
    ) -> Optional[str]:
        """
        发送告警通知

        Args:
            chat_id: 飞书会话ID
            title: 告警标题
            level: 告警级别 (critical/warning/info)
            content: 告警内容

        Returns:
            发送的消息ID
        """
        if not self._handler:
            raise RuntimeError("通道未启动")

        result = await self._handler.sender.send_alert_notification(
            receive_id=chat_id,
            receive_id_type="chat_id",
            title=title,
            level=level,
            content=content,
        )
        return result.message_id

    # ==================== 会话管理 ====================

    def get_session_id(
        self,
        feishu_chat_id: str,
        feishu_user_id: str,
    ) -> Optional[str]:
        """获取zCloud会话ID"""
        if not self._session_mapper:
            return None
        return self._session_mapper.get_zcloud_session_id(
            feishu_chat_id=feishu_chat_id,
            feishu_user_id=feishu_user_id,
        )

    def clear_user_sessions(self, feishu_user_id: str) -> int:
        """清除用户所有会话"""
        if not self._session_mapper:
            return 0
        return self._session_mapper.clear_user_sessions(feishu_user_id)

    # ==================== 状态 ====================

    def get_status(self) -> FeishuChannelStatus:
        """获取通道状态"""
        return self.status

    def get_stats(self) -> dict:
        """获取统计信息"""
        if self._handler:
            return self._handler.get_stats()
        return {}


# ==================== 单例管理 ====================

_channel: Optional[FeishuChannel] = None
_channel_lock = threading.Lock()


def get_feishu_channel() -> Optional[FeishuChannel]:
    """获取当前飞书通道实例"""
    return _channel


async def start_feishu_channel(config: FeishuChannelConfig) -> FeishuChannel:
    """启动飞书通道并返回实例"""
    global _channel
    with _channel_lock:
        if _channel is None:
            _channel = FeishuChannel(config=config)
        await _channel.start()
    return _channel


async def stop_feishu_channel():
    """停止飞书通道"""
    global _channel
    with _channel_lock:
        if _channel:
            await _channel.stop()
