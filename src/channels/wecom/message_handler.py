"""企业微信消息处理器

负责解析企微回调消息，转换为统一ChannelMessage格式，
并管理企微会话与Javis会话的映射关系。
"""
import hashlib
import hmac
import base64
import struct
import xml.etree.ElementTree as ET
import time
import logging
from typing import Optional
from src.channels.base import ChannelMessage
from src.channels.wecom.models import WecomIncomingMessage, WecomMessage
from src.channels.wecom.config import get_wecom_config

logger = logging.getLogger(__name__)


class WecomMessageHandler:
    """
    企业微信消息处理器

    功能：
    1. 解析企微回调消息（支持XML和JSON格式）
    2. 验证消息签名（可选）
    3. 管理会话映射（企微userid/chatid → Javis-DB-Agent session_id）
    4. 将企微消息转换为统一ChannelMessage格式
    """

    def __init__(self, config: Optional[WecomChannelConfig] = None):
        self.config = config or get_wecom_config()
        self._session_map: dict[str, str] = {}  # channel_key → Javis-DB-Agent session_id
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    # ==================== 消息解析 ====================

    def parse_callback(self, body: bytes, headers: dict) -> Optional[WecomIncomingMessage]:
        """
        解析企微回调请求

        Args:
            body: 请求体（XML格式）
            headers: 请求头

        Returns:
            WecomIncomingMessage 或 None（无效消息）
        """
        try:
            body_str = body.decode("utf-8") if isinstance(body, bytes) else body
            msg = WecomIncomingMessage.from_wx_callback_xml(body_str)
            logger.info(f"[WecomCallback] msg_type={msg.msg_type}, from={msg.from_user_name}, chat_type={msg.chat_type}")
            return msg
        except Exception as e:
            logger.error(f"[WecomCallback] Failed to parse message: {e}")
            return None

    def parse_json_payload(self, payload: dict) -> WecomIncomingMessage:
        """解析JSON格式的企微消息（用于API轮询模式）"""
        return WecomIncomingMessage.from_json_payload(payload)

    # ==================== 签名验证 ====================

    def verify_callback_signature(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        encrypted_xml: str,
    ) -> bool:
        """
        验证企微回调消息签名

        企微回调使用AES加解密，签名验证基于SHA1
        参考: https://developer.work.weixin.qq.com/document/path/90930
        """
        if not self.config.callback_token:
            logger.warning("[WecomCallback] Token not configured, skipping signature verification")
            return True

        token = self.config.callback_token
        # 将token、timestamp、nonce按字典序排序后拼接
        sort_str = sorted([token, timestamp, nonce], key=str.lower)
        sort_str.append(encrypted_xml)
        signature_str = "".join(sort_str)

        # SHA1哈希
        signature = hashlib.sha1(signature_str.encode("utf-8")).hexdigest()

        return signature == msg_signature

    def decrypt_message(self, encrypted_xml: str) -> str:
        """
        解密企微回调消息（AES加解密）

        使用AES-256-CBC解密，PKCS7填充
        注意：需要callback_aes_key配置
        """
        if not self.config.callback_aes_key:
            logger.warning("[WecomCallback] AES key not configured, returning raw content")
            return encrypted_xml

        try:
            import crypto.Cipher as Cipher
            import crypto.Util.padding as padding
        except ImportError:
            logger.error("[WecomCallback] pycryptodome not installed, cannot decrypt message")
            return encrypted_xml

        aes_key = base64.b64decode(self.config.callback_aes_key + "=")
        encrypted_data = base64.b64decode(encrypted_xml)

        # 提取16字节随机串 + 4字节消息长度 + 消息内容
        iv = encrypted_data[:16]
        msg_len = struct.unpack(">I", encrypted_data[16:20])[0]
        msg_content = encrypted_data[20:20 + msg_len]

        # AES解密
        cipher = Cipher.new(Cipher.AES, Cipher.MODE_CBC, iv, AES_KEY=aes_key)
        decrypted = cipher.decrypt(msg_content)
        # 去除PKCS7填充
        decrypted = padding.unpad(decrypted, 16)

        return decrypted.decode("utf-8")

    # ==================== 会话映射 ====================

    def _get_channel_key(self, msg: WecomIncomingMessage) -> str:
        """获取企微会话的唯一键"""
        if msg.is_group:
            return f"group:{msg.chat_id}"
        return f"user:{msg.from_user_name}"

    def get_session_id(self, msg: WecomIncomingMessage) -> Optional[str]:
        """获取企微会话对应的zCloud session_id"""
        key = self._get_channel_key(msg)
        return self._session_map.get(key)

    def set_session_id(self, msg: WecomIncomingMessage, session_id: str):
        """保存企微会话到zCloud session_id的映射"""
        key = self._get_channel_key(msg)
        self._session_map[key] = session_id
        logger.info(f"[WecomSession] Mapped {key} → {session_id}")

    def remove_session(self, msg: WecomIncomingMessage):
        """删除会话映射"""
        key = self._get_channel_key(msg)
        self._session_map.pop(key, None)

    def get_all_sessions(self) -> dict[str, str]:
        """获取所有会话映射"""
        return self._session_map.copy()

    # ==================== 消息转换 ====================

    def to_channel_message(self, msg: WecomIncomingMessage) -> ChannelMessage:
        """
        将企微消息转换为统一ChannelMessage格式
        """
        session_id = self.get_session_id(msg)

        return ChannelMessage(
            message_id=msg.msg_id or f"wecom-{int(time.time()*1000)}",
            channel="wecom",
            user_id=msg.from_user_name,
            session_id=session_id,
            content=msg.to_content(),
            metadata={
                "agent_id": msg.agent_id,
                "chat_id": msg.chat_id,
                "chat_type": msg.chat_type,
                "msg_type": msg.msg_type,
                "create_time": msg.create_time,
                "is_group": msg.is_group,
                "is_alert": msg.is_alert,
                "raw_msg": {
                    "msg_id": msg.msg_id,
                    "from_user": msg.from_user_name,
                    "to_user": msg.to_user_name,
                    "msg_type": msg.msg_type,
                    "content": msg.content,
                    "media_id": msg.media_id,
                    "file_name": msg.file_name,
                },
            },
            timestamp=float(msg.create_time) if msg.create_time else time.time(),
        )

    # ==================== Access Token管理 ====================

    async def get_access_token(self) -> Optional[str]:
        """
        获取企微API访问令牌

        企微access_token有效期为7200秒，缓存至过期
        """
        if self._access_token and time.time() < self._token_expires_at - 300:
            return self._access_token

        if not self.config.corp_id or not self.config.corp_secret:
            logger.error("[WecomAPI] corp_id or corp_secret not configured")
            return None

        import httpx
        url = f"{self.config.api_base_url}/cgi-bin/gettoken"
        params = {"corpid": self.config.corp_id, "corpsecret": self.config.corp_secret}

        try:
            async with httpx.AsyncClient(timeout=self.config.api_timeout) as client:
                resp = await client.get(url, params=params)
                data = resp.json()

            if data.get("errcode", 0) == 0:
                self._access_token = data["access_token"]
                self._token_expires_at = time.time() + data.get("expires_in", 7200)
                logger.info("[WecomAPI] Access token refreshed")
                return self._access_token
            else:
                logger.error(f"[WecomAPI] Failed to get access_token: {data}")
                return None
        except Exception as e:
            logger.error(f"[WecomAPI] Error getting access_token: {e}")
            return None

    # ==================== 消息发送 ====================

    async def send_message(
        self,
        chatid: str,
        content: str,
        chat_type: int = 1,
        msgtype: str = "text",
    ) -> dict:
        """
        通过企微API发送消息

        Args:
            chatid: 接收方userid（单聊）或群ID（群聊）
            content: 消息内容
            chat_type: 1=单聊, 2=群聊
            msgtype: 消息类型 text/markdown/image/file

        Returns:
            API响应dict
        """
        token = await self.get_access_token()
        if not token:
            return {"errcode": -1, "errmsg": "Failed to get access token"}

        import httpx
        url = f"{self.config.api_base_url}/cgi-bin/message/send"
        params = {"access_token": token}

        payload = {
            "chat_type": chat_type,
            "chatid": chatid,
            "msgtype": msgtype,
        }

        if msgtype == "text":
            payload["text"] = {"content": content}
        elif msgtype == "markdown":
            payload["markdown"] = {"content": content}
        elif msgtype == "image":
            payload["image"] = {"media_id": content}
        elif msgtype == "file":
            payload["file"] = {"media_id": content}

        try:
            async with httpx.AsyncClient(timeout=self.config.api_timeout) as client:
                resp = await client.post(url, params=params, json=payload)
                result = resp.json()

            if result.get("errcode", 0) == 0:
                logger.info(f"[WecomAPI] Message sent to {chatid}")
            else:
                logger.error(f"[WecomAPI] Send failed: {result}")

            return result
        except Exception as e:
            logger.error(f"[WecomAPI] Error sending message: {e}")
            return {"errcode": -1, "errmsg": str(e)}

    async def send_text(self, chatid: str, content: str, chat_type: int = 1) -> dict:
        """发送文本消息"""
        # 截断超长消息
        if len(content) > self.config.max_message_length:
            content = content[: self.config.max_message_length - 3] + "..."
        return await self.send_message(chatid, content, chat_type, "text")

    async def send_markdown(self, chatid: str, content: str, chat_type: int = 1) -> dict:
        """
        发送Markdown消息（仅支持群聊部分语法）

        支持的Markdown语法：
        - 标题 (# ## ###)
        - 加粗 (**text**)
        - 链接 ([text](url))
        - 引用 (> quote)
        - 代码 (`code`)
        - 列表 (- item)
        """
        if len(content) > self.config.max_message_length:
            content = content[: self.config.max_message_length - 3] + "..."
        return await self.send_message(chatid, content, chat_type, "markdown")

    async def send_alert(
        self,
        content: str,
        alert_level: str = "warning",
        chatid: Optional[str] = None,
    ) -> dict:
        """
        发送告警通知

        Args:
            content: 告警内容
            alert_level: 告警级别（critical/warning/info）
            chatid: 目标会话ID（不传则使用配置的默认目标）
        """
        target = chatid or self.config.alert_target
        if not target:
            logger.warning("[WecomAlert] No alert target configured")
            return {"errcode": -1, "errmsg": "No alert target configured"}

        # 告警级别前缀
        level_prefix = {
            "critical": "🚨【严重告警】",
            "warning": "⚠️【警告】",
            "info": "ℹ️【通知】",
        }.get(alert_level, "📢【通知】")

        full_content = f"{level_prefix}\n\n{content}"
        return await self.send_text(target, full_content, chat_type=2 if "@" not in target else 1)


# 全局handler单例
_wecom_handler: Optional[WecomMessageHandler] = None


def get_wecom_handler() -> WecomMessageHandler:
    global _wecom_handler
    if _wecom_handler is None:
        _wecom_handler = WecomMessageHandler()
    return _wecom_handler


def reset_wecom_handler():
    global _wecom_handler
    _wecom_handler = None
