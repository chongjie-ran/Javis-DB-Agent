"""企业微信消息模型"""
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class WecomMessage:
    """企微发送消息结构"""
    chat_type: int          # 1=单聊, 2=群聊
    chatid: str             # 单聊时为userid, 群聊时为群ID
    msgtype: str = "text"   # text/image/card/markdown
    text: dict = field(default_factory=dict)  # {"content": "..."}
    safe_token: Optional[str] = None

    def to_api_payload(self) -> dict:
        """转换为企微API请求payload"""
        payload = {
            "chat_type": self.chat_type,
            "chatid": self.chatid,
            "msgtype": self.msgtype,
            "msgtype": self.msgtype,
        }
        if self.msgtype == "text":
            payload["text"] = self.text
        elif self.msgtype == "markdown":
            payload["markdown"] = self.text
        elif self.msgtype == "image":
            payload["image"] = self.text
        elif self.msgtype == "file":
            payload["file"] = self.text
        return payload

    @classmethod
    def text_message(cls, chatid: str, content: str, chat_type: int = 1) -> "WecomMessage":
        """创建文本消息"""
        return cls(chat_type=chat_type, chatid=chatid, msgtype="text", text={"content": content})

    @classmethod
    def markdown_message(cls, chatid: str, content: str, chat_type: int = 1) -> "WecomMessage":
        """创建Markdown消息（仅群聊支持）"""
        return cls(chat_type=chat_type, chatid=chatid, msgtype="markdown", text={"content": content})

    @classmethod
    def image_message(cls, chatid: str, media_id: str, chat_type: int = 1) -> "WecomMessage":
        """创建图片消息"""
        return cls(chat_type=chat_type, chatid=chatid, msgtype="image", text={"media_id": media_id})


@dataclass
class WecomIncomingMessage:
    """
    企微回调推送的原始消息结构
    参考: https://developer.work.weixin.qq.com/document/path/91774
    """
    # 消息相关
    msg_id: str = ""                    # 消息id
    to_user_name: str = ""              # 接收消息方（企业）
    from_user_name: str = ""            # 发送方（用户userid或群聊的chatid）
    create_time: int = 0                 # 消息创建时间（Unix时间戳）
    msg_type: str = "text"              # 消息类型：text/image/file/voice/video/link/miniapp/text/react
    content: str = ""                   # 消息内容（text类型）
    media_id: str = ""                  # 媒体文件id（image/voice/video/file）
    file_name: str = ""                 # 文件名（file类型）
    file_size: str = ""                 # 文件大小（file类型）
    link: dict = field(default_factory=dict)  # 链接消息内容
    agent_id: int = 0                   # 应用AgentId
    chat_id: str = ""                   # 群聊消息的chatid（群聊时填充）

    # 会话类型
    chat_type: str = "single"           # 会话类型：single/challenge/group

    # 重试相关
    is_redo: bool = False               # 是否是重发消息
    pri_msg_hdr_id: int = 0             # 消息重复发送的唯一标识

    # 原始回调XML（如果需要）
    _raw_xml: str = ""

    @property
    def user_id(self) -> str:
        """从消息中提取用户ID"""
        if self.chat_type == "group":
            return self.from_user_name
        return self.from_user_name

    @property
    def is_group(self) -> bool:
        """是否为群聊消息"""
        return self.chat_type == "group"

    @property
    def is_text(self) -> bool:
        """是否为文本消息"""
        return self.msg_type == "text"

    @property
    def is_alert_message_type(self) -> bool:
        """是否为告警类型的消息（msg_type == "alert"）"""
        return self.msg_type == "alert"

    def contains_alert_keyword(self) -> bool:
        """消息内容是否包含告警关键词"""
        alert_keywords = ["告警", "报警", "alert", "warning", "critical", "error", "故障", "异常"]
        content_lower = self.content.lower()
        return any(kw in content_lower for kw in alert_keywords)

    @property
    def is_alert(self) -> bool:
        """是否可能为告警消息（通过关键词或消息类型判断）"""
        return self.is_alert_message_type or self.contains_alert_keyword()

    def to_content(self) -> str:
        """提取消息内容用于传递给Orchestrator"""
        if self.msg_type == "text":
            return self.content
        elif self.msg_type == "image":
            return "[图片消息]"
        elif self.msg_type == "voice":
            return "[语音消息]"
        elif self.msg_type == "video":
            return "[视频消息]"
        elif self.msg_type == "file":
            return f"[文件: {self.file_name}]"
        elif self.msg_type == "link":
            link_info = self.link or {}
            title = link_info.get("title", "链接")
            desc = link_info.get("desc", "")
            return f"[链接] {title}\n{desc}"
        elif self.msg_type == "miniapp":
            return "[小程序消息]"
        else:
            return f"[{self.msg_type}消息]"

    @classmethod
    def from_wx_callback_xml(cls, xml_string: str | bytes) -> "WecomIncomingMessage":
        """
        从企微回调的XML格式解析消息
        企微回调消息体为XML格式

        Returns:
            WecomIncomingMessage 或 None（无效XML）
        """
        import re
        # 支持直接传入bytes
        if isinstance(xml_string, bytes):
            xml_string = xml_string.decode("utf-8")

        # 简单验证XML格式
        if "<xml" not in xml_string or "</xml>" not in xml_string:
            return None  # 无效XML

        def get_xml_value(xml: str, tag: str) -> str:
            match = re.search(f"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", xml)
            if match:
                return match.group(1)
            match = re.search(f"<{tag}>(.*?)</{tag}>", xml)
            return match.group(1) if match else ""

        def get_xml_int(xml: str, tag: str) -> int:
            val = get_xml_value(xml, tag)
            try:
                return int(val)
            except (ValueError, TypeError):
                return 0

        def get_xml_bool(xml: str, tag: str) -> bool:
            val = get_xml_value(xml, tag)
            return val == "1"

        msg = cls()
        msg._raw_xml = xml_string
        msg.msg_id = get_xml_value(xml_string, "MsgId")
        msg.to_user_name = get_xml_value(xml_string, "ToUserName")
        msg.from_user_name = get_xml_value(xml_string, "FromUserName")
        msg.create_time = get_xml_int(xml_string, "CreateTime")
        msg.msg_type = get_xml_value(xml_string, "MsgType")
        msg.content = get_xml_value(xml_string, "Content")
        msg.media_id = get_xml_value(xml_string, "MediaId")
        msg.file_name = get_xml_value(xml_string, "FileName")
        msg.file_size = get_xml_value(xml_string, "FileSize")
        msg.agent_id = get_xml_int(xml_string, "AgentID")
        msg.chat_id = get_xml_value(xml_string, "ChatId")
        msg.is_redo = get_xml_bool(xml_string, "IsRedact")
        msg.pri_msg_hdr_id = get_xml_int(xml_string, "PriMsgHeaderId")

        # chat_type: 区分单聊和群聊
        # 单聊: FromUserName是userid, ToUserName是第三方应用绑定的企业互联的CorpID
        # 群聊: 有ChatId字段
        if msg.chat_id:
            msg.chat_type = "group"
        else:
            msg.chat_type = "single"

        # 解析链接消息
        if msg.msg_type == "link":
            msg.link = {
                "title": get_xml_value(xml_string, "Title"),
                "description": get_xml_value(xml_string, "Description"),
                "url": get_xml_value(xml_string, "Url"),
                "app_name": get_xml_value(xml_string, "AppName"),
                "logo_url": get_xml_value(xml_string, "LogoUrl"),
            }

        return msg

    @classmethod
    def from_json_payload(cls, payload: dict) -> "WecomIncomingMessage":
        """
        从JSON格式解析消息（部分企微接口返回JSON格式）
        """
        msg = cls()
        msg.msg_id = str(payload.get("msgId", payload.get("msg_id", "")))
        msg.to_user_name = payload.get("toUserName", payload.get("to_user_name", ""))
        msg.from_user_name = payload.get("fromUserName", payload.get("from_user_name", ""))
        msg.create_time = int(payload.get("createTime", payload.get("create_time", 0)))
        msg.msg_type = payload.get("msgType", payload.get("msg_type", "text"))
        msg.content = payload.get("content", "")
        msg.media_id = payload.get("mediaId", payload.get("media_id", ""))
        msg.file_name = payload.get("fileName", payload.get("file_name", ""))
        msg.file_size = payload.get("fileSize", payload.get("file_size", ""))
        msg.agent_id = int(payload.get("agentId", payload.get("agent_id", 0)))
        msg.chat_id = payload.get("chatId", payload.get("chat_id", ""))
        msg.chat_type = payload.get("chatType", payload.get("chat_type", "single"))
        msg.is_redo = payload.get("isRedact", payload.get("is_redo", False))

        if msg.chat_id:
            msg.chat_type = "group"

        if msg.msg_type == "link":
            msg.link = payload.get("link", {})

        return msg
