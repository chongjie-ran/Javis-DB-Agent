"""飞书消息处理器

核心组件：处理飞书机器人接收到的消息，转发给Orchestrator处理。

职责：
1. 消息解析与验证
2. 消息去重
3. 权限检查
4. 消息路由到Orchestrator
5. 响应发送

参考OpenClaw Lark插件架构设计：
- inbound/dispatch.js - 消息分发
- inbound/parse.js - 消息解析
- inbound/handler.js - 消息处理
"""
import time
import json
import hashlib
import logging
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from src.channels.feishu.client import FeishuClient, FeishuAPIError
from src.channels.feishu.sender import FeishuSender, create_feishu_sender
from src.channels.feishu.session_mapper import FeishuSessionMapper, get_feishu_session_mapper
from src.channels.feishu.config import FeishuChannelConfig

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型"""
    TEXT = "text"
    POST = "post"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    STICKER = "sticker"
    CARD = "card"
    MEDIA = "media"
    UNKNOWN = "unknown"


class ChatType(Enum):
    """会话类型"""
    P2P = "p2p"  # 单聊
    GROUP = "group"  # 群聊


@dataclass
class FeishuMessage:
    """飞书消息结构"""
    message_id: str
    chat_id: str
    chat_type: ChatType
    sender_id: str
    sender_type: str  # user / bot
    message_type: MessageType
    content: str
    create_time: str
    update_time: Optional[str] = None
    is_mention: bool = False  # 是否@了机器人
    quoted_message_id: Optional[str] = None
    thread_id: Optional[str] = None
    raw: dict = field(default_factory=dict)

    @property
    def feishu_user_id(self) -> str:
        """飞书用户ID"""
        return self.sender_id

    @property
    def is_group(self) -> bool:
        """是否为群聊"""
        return self.chat_type == ChatType.GROUP

    @property
    def is_p2p(self) -> bool:
        """是否为单聊"""
        return self.chat_type == ChatType.P2P

    @property
    def is_bot_message(self) -> bool:
        """是否为机器人消息"""
        return self.sender_type == "bot"


class FeishuMessageHandler:
    """
    飞书消息处理器

    处理飞书机器人接收到的所有消息：
    1. 解析消息
    2. 去重检查
    3. 权限验证
    4. 路由到Orchestrator
    5. 发送响应
    """

    def __init__(
        self,
        client: FeishuClient,
        config: FeishuChannelConfig,
        session_mapper: Optional[FeishuSessionMapper] = None,
    ):
        self.client = client
        self.config = config
        self.session_mapper = session_mapper or get_feishu_session_mapper(
            ttl_seconds=config.session_ttl_seconds,
            max_per_user=config.max_sessions_per_user,
        )
        self.sender = create_feishu_sender(client, config)

        # 消息去重缓存: message_id -> timestamp
        self._dedup_cache: dict[str, float] = {}
        self._dedup_lock = None  # 将在首次使用时初始化

    def _get_dedup_lock(self):
        """获取去重锁（延迟初始化避免循环导入）"""
        if self._dedup_lock is None:
            import threading
            self._dedup_lock = threading.Lock()
        return self._dedup_lock

    # ==================== 消息解析 ====================

    def parse_message(self, event_data: dict) -> Optional[FeishuMessage]:
        """
        解析飞书WebSocket事件数据

        Args:
            event_data: WebSocket推送的事件数据

        Returns:
            FeishuMessage 或 None（无法解析时）
        """
        try:
            # 提取消息基本信息
            header = event_data.get("header", {})
            event_type = header.get("event_type", "")

            # 目前只处理消息接收事件
            if event_type != "im.message.receive_v1":
                logger.debug(f"忽略非消息事件: {event_type}")
                return None

            event = event_data.get("event", {})
            sender = event.get("sender", {})
            sender_info = sender.get("sender", {})

            message_id = event.get("message", {}).get("message_id", "")
            chat_id = event.get("chat_id", "")
            chat_type_str = event.get("chat_type", "p2p")
            message_type_str = event.get("message_type", "text")

            # 解析消息内容
            raw_content = event.get("content", "{}")
            try:
                content_data = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
            except (json.JSONDecodeError, TypeError):
                content_data = {"text": raw_content}

            return FeishuMessage(
                message_id=message_id,
                chat_id=chat_id,
                chat_type=ChatType.GROUP if chat_type_str == "group" else ChatType.P2P,
                sender_id=sender_info.get("open_id", ""),
                sender_type=sender_info.get("sender_type", "user"),
                message_type=self._parse_message_type(message_type_str),
                content=self._extract_content(content_data, message_type_str),
                create_time=event.get("create_time", ""),
                update_time=event.get("update_time"),
                is_mention=False,  # @判断由外部处理
                quoted_message_id=event.get("quote_id"),
                thread_id=event.get("thread_id"),
                raw=event_data,
            )

        except Exception as e:
            logger.error(f"解析消息失败: {e}", exc_info=True)
            return None

    def _parse_message_type(self, msg_type: str) -> MessageType:
        """解析消息类型"""
        mapping = {
            "text": MessageType.TEXT,
            "post": MessageType.POST,
            "image": MessageType.IMAGE,
            "file": MessageType.FILE,
            "audio": MessageType.AUDIO,
            "video": MessageType.VIDEO,
            "sticker": MessageType.STICKER,
            "interactive": MessageType.CARD,
            "media": MessageType.MEDIA,
        }
        return mapping.get(msg_type, MessageType.UNKNOWN)

    def _extract_content(self, content_data: dict, msg_type: str) -> str:
        """从消息内容中提取纯文本"""
        if msg_type == "text":
            return content_data.get("text", "")
        elif msg_type == "post":
            # 飞书post格式较复杂，简化处理
            zh_cn = content_data.get("zh_cn", {})
            content_list = zh_cn.get("content", [])
            texts = []
            for paragraph in content_list:
                for item in paragraph:
                    if tag := item.get("tag"):
                        if tag == "text":
                            texts.append(item.get("text", ""))
                        elif tag == "at":
                            texts.append(f"@{item.get('text', '')}")
                        elif tag == "link":
                            texts.append(item.get("text", ""))
            return "\n".join(texts)
        elif msg_type == "card":
            # 卡片消息内容
            return content_data.get("content", str(content_data))
        else:
            return str(content_data)

    # ==================== 消息去重 ====================

    def is_duplicate(self, message_id: str) -> bool:
        """
        检查是否为重复消息

        使用滑动窗口去重，缓存TTL为配置的dedup_ttl_ms
        """
        import threading
        if self._dedup_lock is None:
            self._dedup_lock = threading.Lock()

        with self._get_dedup_lock():
            now = time.time()
            ttl_seconds = self.config.dedup_ttl_ms / 1000.0

            # 清理过期条目
            expired = [mid for mid, ts in self._dedup_cache.items() if now - ts > ttl_seconds]
            for mid in expired:
                self._dedup_cache.pop(mid, None)

            # 检查是否重复
            if message_id in self._dedup_cache:
                return True

            # 记录新消息
            self._dedup_cache[message_id] = now
            return False

    # ==================== 权限检查 ====================

    def check_permission(self, message: FeishuMessage) -> bool:
        """
        检查用户是否有权限使用Bot

        Returns:
            True=允许, False=拒绝
        """
        # 如果配置允许所有人，则直接通过
        if self.config.allow_from_all:
            return True

        # 检查是否在白名单中
        sender_id = message.sender_id
        chat_id = message.chat_id

        allowed = self.config.allow_from
        if sender_id in allowed or chat_id in allowed:
            return True

        return False

    # ==================== 核心处理入口 ====================

    async def handle_event(self, event_data: dict) -> Optional[str]:
        """
        处理飞书事件（WebSocket推送）

        这是主要入口，由WebSocket服务器调用。

        Args:
            event_data: 飞书WebSocket事件数据

        Returns:
            发送的消息ID，或None
        """
        # 1. 解析消息
        message = self.parse_message(event_data)
        if not message:
            logger.debug("无法解析消息，跳过")
            return None

        # 2. 跳过机器人自己的消息
        if message.is_bot_message:
            logger.debug(f"跳过机器人消息: {message.message_id}")
            return None

        # 3. 去重检查
        if self.is_duplicate(message.message_id):
            logger.debug(f"消息重复，跳过: {message.message_id}")
            return None

        # 4. 权限检查
        if not self.check_permission(message):
            logger.warning(f"权限拒绝: sender={message.sender_id}")
            await self._send_permission_denied(message)
            return None

        # 5. 处理消息
        logger.info(
            f"收到消息: chat={message.chat_id} user={message.sender_id} "
            f"type={message.message_type.value} content={message.content[:50]}"
        )

        # 6. 获取或创建会话
        session_id = self.session_mapper.get_or_create_session(
            feishu_chat_id=message.chat_id,
            feishu_user_id=message.sender_id,
            feishu_message_id=message.message_id,
            is_thread=bool(message.thread_id),
            thread_id=message.thread_id,
        )

        # 7. 发送到Orchestrator
        result = await self._dispatch_to_orchestrator(message, session_id)

        return result

    # ==================== Orchestrator集成 ====================

    async def _dispatch_to_orchestrator(
        self,
        message: FeishuMessage,
        session_id: str,
    ) -> Optional[str]:
        """
        将消息分发给Orchestrator处理

        这个方法桥接飞书通道和zCloud Orchestrator。
        需要注入OrchestratorAgent实例。
        """
        from src.agents.orchestrator import OrchestratorAgent

        try:
            # 获取或创建Orchestrator实例
            orchestrator = self._get_orchestrator()

            # 构建上下文
            context = {
                "channel": "feishu",
                "chat_id": message.chat_id,
                "user_id": message.sender_id,
                "message_id": message.message_id,
                "chat_type": message.chat_type.value,
                "message_type": message.message_type.value,
                "thread_id": message.thread_id,
                "session_id": session_id,
                "raw_event": message.raw,
            }

            # 如果配置了流式响应
            if self.config.streaming_enabled:
                return await self._handle_streaming(message, session_id, orchestrator, context)
            else:
                return await self._handle_static(message, session_id, orchestrator, context)

        except Exception as e:
            logger.error(f"Orchestrator处理失败: {e}", exc_info=True)
            await self._send_error_response(message, str(e))
            return None

    async def _handle_static(
        self,
        message: FeishuMessage,
        session_id: str,
        orchestrator,
        context: dict,
    ) -> Optional[str]:
        """静态响应处理"""
        response = await orchestrator.handle_chat(
            user_input=message.content,
            context=context,
        )

        if not response.success:
            await self._send_error_response(message, response.error)
            return None

        # 发送响应
        result = await self.sender.send_agent_response(
            receive_id=message.chat_id,
            receive_id_type="chat_id",
            text=response.content,
            metadata=response.metadata,
        )

        return result.message_id

    async def _handle_streaming(
        self,
        message: FeishuMessage,
        session_id: str,
        orchestrator,
        context: dict,
    ) -> Optional[str]:
        """流式响应处理"""
        # 先发送"正在思考..."卡片
        initial_card = FeishuSender.build_streaming_card("🤔 正在思考...")
        result = await self.sender.send_card(
            receive_id=message.chat_id,
            receive_id_type="chat_id",
            card=initial_card,
        )

        if not result.message_id:
            # 降级到静态
            return await self._handle_static(message, session_id, orchestrator, context)

        card_message_id = result.message_id
        full_content = ""

        try:
            # 流式收集响应
            async for event in orchestrator.handle_chat_stream(
                user_input=message.content,
                context=context,
            ):
                event_type = event.get("type")

                if event_type == "thinking":
                    # 正在思考，更新卡片
                    thinking_text = event.get("content", "")
                    await self.sender.update_streaming_card(
                        card_message_id,
                        f"🤔 {thinking_text}\n\n_等待回复..._",
                    )

                elif event_type == "content":
                    # 内容片段，累积并更新
                    token = event.get("content", "")
                    full_content += token
                    await self.sender.update_streaming_card(card_message_id, full_content)

                elif event_type == "done":
                    # 完成
                    full_content = event.get("content", full_content)
                    # 最终更新
                    await self.sender.update_streaming_card(card_message_id, full_content)
                    break

        except Exception as e:
            logger.error(f"流式响应异常: {e}", exc_info=True)
            await self.sender.update_streaming_card(
                card_message_id,
                f"⚠️ 处理出错: {str(e)}",
            )

        return card_message_id

    def _get_orchestrator(self):
        """获取OrchestratorAgent实例"""
        return OrchestratorAgent()

    # ==================== 错误与权限响应 ====================

    async def _send_permission_denied(self, message: FeishuMessage):
        """发送权限拒绝消息"""
        text = "抱歉，您没有权限使用此服务。如需开通，请联系管理员。"
        await self.sender.send_text(
            receive_id=message.chat_id,
            receive_id_type="chat_id",
            text=text,
        )

    async def _send_error_response(self, message: FeishuMessage, error: str):
        """发送错误响应"""
        text = f"⚠️ 处理出错\n\n{error}"
        await self.sender.send_markdown(
            receive_id=message.chat_id,
            receive_id_type="chat_id",
            markdown=text,
        )

    # ==================== Webhook入口 ====================

    async def handle_webhook(
        self,
        body: dict,
        headers: dict,
    ) -> dict:
        """
        处理Webhook HTTP请求

        用于Webhook模式的入口。

        Args:
            body: 请求体
            headers: 请求头

        Returns:
            HTTP响应
        """
        import json

        # 验证请求
        if self.config.webhook_verify_token:
            if not FeishuClient.verify_webhook(
                body=body,
                headers=headers,
                verify_token=self.config.webhook_verify_token,
                encrypt_key=self.config.webhook_encrypt_key,
            ):
                logger.warning("Webhook验证失败")
                return {"code": 401, "msg": "Unauthorized"}

        # 解析事件类型
        event_type = body.get("header", {}).get("event_type", "")

        if event_type == "im.message.receive_v1":
            await self.handle_event(body)
            return {"code": 0, "msg": "success"}
        else:
            return {"code": 0, "msg": f"event {event_type} acknowledged"}

    # ==================== 统计 ====================

    def get_stats(self) -> dict:
        """获取处理器统计信息"""
        return {
            "dedup_cache_size": len(self._dedup_cache),
            "session_mapper": self.session_mapper.get_stats(),
        }


# ==================== 工厂函数 ====================

def create_message_handler(
    client: FeishuClient,
    config: FeishuChannelConfig,
    session_mapper: Optional[FeishuSessionMapper] = None,
) -> FeishuMessageHandler:
    """创建消息处理器实例"""
    return FeishuMessageHandler(
        client=client,
        config=config,
        session_mapper=session_mapper,
    )
