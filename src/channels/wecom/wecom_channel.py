"""企业微信消息通道

将企微消息接入zCloud Orchestrator，实现：
1. 接收企微用户消息 → 转发Orchestrator处理
2. Orchestrator响应 → 通过企微发送给用户
3. 会话映射管理（企微会话 ↔ zCloud会话）
"""
import asyncio
import logging
import time
import uuid
from typing import Optional, AsyncIterator

from src.channels.base import BaseChannel, ChannelMessage, ChannelResponse
from src.channels.wecom.config import WecomChannelConfig, get_wecom_config
from src.channels.wecom.message_handler import WecomMessageHandler, get_wecom_handler
from src.channels.wecom.models import WecomIncomingMessage

logger = logging.getLogger(__name__)


class WecomChannel(BaseChannel):
    """
    企业微信消息通道

    负责：
    1. 管理企微消息与zCloud会话的映射
    2. 将企微消息转发给Orchestrator
    3. 将Orchestrator响应通过企微发送
    4. 接收企微回调并处理
    """

    channel_name: str = "wecom"

    def __init__(self, config: Optional[WecomChannelConfig] = None):
        self.config = config or get_wecom_config()
        self.handler = WecomMessageHandler(self.config)

        # Orchestrator实例（延迟加载）
        self._orchestrator = None

        # 消息缓冲（用于流式响应收集）
        self._pending_responses: dict[str, asyncio.Event] = {}
        self._response_cache: dict[str, str] = {}

        logger.info(f"[WecomChannel] Initialized (enabled={self.config.enabled})")

    @property
    def orchestrator(self):
        """延迟加载Orchestrator"""
        if self._orchestrator is None:
            from src.agents.orchestrator import OrchestratorAgent
            self._orchestrator = OrchestratorAgent()
        return self._orchestrator

    # ==================== BaseChannel 实现 ====================

    async def receive(self) -> list[ChannelMessage]:
        """
        接收消息（被动模式，由外部路由调用handle_callback触发）
        此方法在WebSocket模式下使用
        """
        # 企微采用回调模式，消息通过handle_callback接收
        # 此处返回空列表，由回调路由处理实际消息
        return []

    async def send(
        self,
        user_id: str,
        content: str,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> ChannelResponse:
        """
        通过企微发送消息

        Args:
            user_id: 企微userid或群ID
            content: 消息内容
            session_id: zCloud会话ID（可选）
            kwargs:
                - chat_type: 1=单聊, 2=群聊
                - msgtype: text/markdown/image/file
                - is_group: 是否为群聊

        Returns:
            ChannelResponse
        """
        if not self.config.enabled:
            return ChannelResponse(success=False, error="Wecom channel disabled")

        chat_type = kwargs.get("chat_type", 1)
        msgtype = kwargs.get("msgtype", "text")
        is_group = kwargs.get("is_group", False)

        # 如果传入的是zCloud session_id，需要找到对应的企微userid/chatid
        # 这里user_id就是企微的userid或chatid，直接使用
        target_id = user_id

        try:
            if msgtype == "text" or not msgtype:
                result = await self.handler.send_text(target_id, content, chat_type)
            elif msgtype == "markdown":
                if is_group:
                    result = await self.handler.send_markdown(target_id, content, chat_type)
                else:
                    # 单聊不支持markdown，降级为文本
                    result = await self.handler.send_text(target_id, content, chat_type)
            else:
                result = await self.handler.send_message(target_id, content, chat_type, msgtype)

            success = result.get("errcode", -1) == 0
            return ChannelResponse(
                success=success,
                message=content[:100],
                data=result,
                error="" if success else result.get("errmsg", "Unknown error"),
                metadata={
                    "target": target_id,
                    "chat_type": chat_type,
                    "msgtype": msgtype,
                },
            )
        except Exception as e:
            logger.error(f"[WecomChannel] Send error: {e}")
            return ChannelResponse(success=False, error=str(e))

    def map_session(self, channel_thread_id: str) -> Optional[str]:
        """
        根据企微会话ID查找对应的zCloud session_id

        Args:
            channel_thread_id: 企微会话标识（userid或chatid）

        Returns:
            zCloud session_id 或 None
        """
        # channel_thread_id 格式: "user:{userid}" 或 "group:{chatid}"
        key = channel_thread_id
        for stored_key, session_id in self.handler.get_all_sessions().items():
            if stored_key == key or stored_key.endswith(channel_thread_id):
                return session_id
        return None

    def save_mapping(self, channel_thread_id: str, session_id: str):
        """
        保存企微会话到zCloud会话的映射

        Args:
            channel_thread_id: 企微会话标识
            session_id: zCloud会话ID
        """
        # channel_thread_id格式: "user:{userid}" 或 "group:{chatid}"
        parts = channel_thread_id.split(":", 1)
        if len(parts) == 2:
            key_type, key_id = parts
            # 通过临时WecomIncomingMessage设置映射
            class _FakeMsg:
                def __init__(self, is_group, from_user, chat_id):
                    self.is_group = is_group
                    self.from_user_name = from_user
                    self.chat_id = chat_id
                    self.chat_type = "group" if is_group else "single"

            if key_type == "group":
                fake_msg = _FakeMsg(True, key_id, key_id)
            else:
                fake_msg = _FakeMsg(False, key_id, "")

            self.handler.set_session_id(fake_msg, session_id)
        logger.info(f"[WecomChannel] Saved mapping: {channel_thread_id} → {session_id}")

    # ==================== 回调处理 ====================

    async def handle_callback(
        self,
        body: bytes,
        headers: dict,
    ) -> ChannelMessage:
        """
        处理企微回调请求（由FastAPI路由调用）

        流程：
        1. 解析消息
        2. 查找或创建会话
        3. 转发给Orchestrator处理
        4. 发送响应

        Args:
            body: 请求体（XML格式）
            headers: 请求头

        Returns:
            转换后的ChannelMessage
        """
        # 1. 解析消息
        msg = self.handler.parse_callback(body, headers)
        if not msg:
            raise ValueError("Failed to parse WeCom callback message")

        # 忽略非文本消息（暂时只处理文本）
        if msg.msg_type not in ("text",):
            logger.info(f"[WecomCallback] Ignored msg_type={msg.msg_type}")
            return self.handler.to_channel_message(msg)

        # 2. 获取或创建zCloud会话
        session_id = self.handler.get_session_id(msg)
        if not session_id:
            session_id = await self._get_or_create_session(msg)
            self.handler.set_session_id(msg, session_id)

        # 3. 转换为ChannelMessage
        channel_msg = self.handler.to_channel_message(msg)

        # 4. 异步处理消息（不阻塞回调响应）
        asyncio.create_task(self._process_message(msg, session_id))

        return channel_msg

    async def _get_or_create_session(self, msg: WecomIncomingMessage) -> str:
        """获取或创建zCloud会话"""
        from src.gateway.session import get_session_manager

        session_mgr = get_session_manager()
        session_id = str(uuid.uuid4())

        if self.config.auto_create_session:
            session = session_mgr.create_session(
                user_id=msg.from_user_name,
                metadata={
                    "channel": "wecom",
                    "agent_id": msg.agent_id,
                    "chat_type": msg.chat_type,
                    "chat_id": msg.chat_id,
                },
            )
            return session.session_id

        return session_id

    async def _process_message(
        self,
        msg: WecomIncomingMessage,
        session_id: str,
    ):
        """
        处理企微消息，转发给Orchestrator并发送响应

        这是一个异步任务，不阻塞回调响应
        """
        from src.gateway.session import get_session_manager

        try:
            session_mgr = get_session_manager()
            session = session_mgr.get_session(session_id)
            if not session:
                logger.error(f"[WecomChannel] Session not found: {session_id}")
                return

            # 构建上下文
            context = {
                "session_id": session_id,
                "user_id": msg.from_user_name,
                "channel": "wecom",
                "agent_id": msg.agent_id,
                "chat_type": msg.chat_type,
                "chat_id": msg.chat_id,
                "extra_info": f"[企微消息] {msg.to_content()}",
            }

            # 添加用户消息到会话
            session.add_message("user", msg.to_content())

            # 发送"正在处理"提示
            await self._send_pending_indicator(msg)

            # 调用Orchestrator处理
            start_time = time.time()
            try:
                response = await self.orchestrator.handle_chat(msg.to_content(), context)
                elapsed_ms = int((time.time() - start_time) * 1000)
                reply_content = response.content if response else "处理完成"
            except Exception as e:
                logger.error(f"[WecomChannel] Orchestrator error: {e}")
                reply_content = f"处理出错: {e}"
                elapsed_ms = int((time.time() - start_time) * 1000)

            # 添加助手响应到会话
            session.add_message("assistant", reply_content)

            # 发送响应到企微
            chat_type = 2 if msg.is_group else 1
            target_id = msg.chat_id if msg.is_group else msg.from_user_name
            await self.handler.send_text(target_id, reply_content, chat_type)

            logger.info(
                f"[WecomChannel] Processed msg={msg.msg_id} "
                f"session={session_id} elapsed={elapsed_ms}ms"
            )

        except Exception as e:
            logger.error(f"[WecomChannel] Process error: {e}", exc_info=True)

    async def _send_pending_indicator(self, msg: WecomIncomingMessage):
        """发送"正在处理"提示（避免用户等待焦虑）"""
        try:
            chat_type = 2 if msg.is_group else 1
            target_id = msg.chat_id if msg.is_group else msg.from_user_name
            await self.handler.send_text(target_id, "🤖 正在处理，请稍候...", chat_type)
        except Exception:
            pass  # 不因提示失败而中断主流程

    # ==================== 流式处理 ====================

    async def handle_stream_callback(
        self,
        body: bytes,
        headers: dict,
    ) -> AsyncIterator[str]:
        """
        处理企微消息并流式返回响应（SSE格式）

        用于需要流式输出的场景（如巡检报告生成）
        """
        msg = self.handler.parse_callback(body, headers)
        if not msg:
            raise ValueError("Failed to parse WeCom callback message")

        session_id = self.handler.get_session_id(msg)
        if not session_id:
            session_id = await self._get_or_create_session(msg)
            self.handler.set_session_id(msg, session_id)

        from src.gateway.session import get_session_manager

        session_mgr = get_session_manager()
        session = session_mgr.get_session(session_id)
        if not session:
            session = session_mgr.create_session(user_id=msg.from_user_name)

        context = {
            "session_id": session_id,
            "user_id": msg.from_user_name,
            "channel": "wecom",
        }

        # 发送初始提示
        yield "event: start\ndata: {}\n\n"

        full_response = ""
        chat_type = 2 if msg.is_group else 1
        target_id = msg.chat_id if msg.is_group else msg.from_user_name

        try:
            async for event in self.orchestrator.handle_chat_stream(msg.to_content(), context):
                event_type = event.get("type")
                content = event.get("content", "")

                if event_type == "thinking":
                    yield f"event: thinking\ndata: {content}\n\n"
                elif event_type == "content":
                    full_response += content
                    yield f"event: chunk\ndata: {content}\n\n"
                elif event_type == "done":
                    elapsed = event.get("execution_time_ms", 0)
                    session.add_message("user", msg.to_content())
                    session.add_message("assistant", full_response)
                    yield f"event: done\ndata: elapsed={elapsed}\n\n"

        except Exception as e:
            logger.error(f"[WecomChannel] Stream error: {e}")
            yield f"event: error\ndata: {str(e)}\n\n"

        # 发送最终响应到企微
        if full_response:
            await self.handler.send_text(target_id, full_response, chat_type)

    # ==================== 告警推送 ====================

    async def push_alert(
        self,
        content: str,
        alert_level: str = "warning",
        target: Optional[str] = None,
    ) -> ChannelResponse:
        """
        推送告警通知到企微

        Args:
            content: 告警内容
            alert_level: 告警级别
            target: 目标会话ID（可选，使用配置的默认目标）

        Returns:
            ChannelResponse
        """
        if not self.config.alert_push_enabled:
            return ChannelResponse(success=False, error="Alert push disabled")

        try:
            result = await self.handler.send_alert(content, alert_level, target)
            success = result.get("errcode", -1) == 0
            return ChannelResponse(
                success=success,
                message=content[:100],
                error="" if success else result.get("errmsg", ""),
            )
        except Exception as e:
            logger.error(f"[WecomChannel] Alert push error: {e}")
            return ChannelResponse(success=False, error=str(e))

    # ==================== 生命周期 ====================

    async def start(self):
        """启动通道（WebSocket连接等）"""
        logger.info("[WecomChannel] Starting...")
        if not self.config.enabled:
            logger.warning("[WecomChannel] Disabled in config, skipping start")
            return

        # 企微使用回调模式，不需要主动连接
        # 如果使用企微的主动拉取模式，可以在这里初始化WebSocket
        logger.info("[WecomChannel] Started (callback mode)")

    async def stop(self):
        """停止通道"""
        logger.info("[WecomChannel] Stopping...")
        self._orchestrator = None
        logger.info("[WecomChannel] Stopped")


# 全局单例
_wecom_channel: Optional[WecomChannel] = None


def get_wecom_channel() -> WecomChannel:
    global _wecom_channel
    if _wecom_channel is None:
        _wecom_channel = WecomChannel()
    return _wecom_channel


def reset_wecom_channel():
    global _wecom_channel
    if _wecom_channel is not None:
        asyncio.run(_wecom_channel.stop())
    _wecom_channel = None
