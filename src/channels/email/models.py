"""Email 数据模型"""
import time
import uuid
import re
from dataclasses import dataclass, field
from typing import Optional
from email.header import decode_header
from email.parser import BytesParser
from email.policy import default


# ==================== 命令解析 ====================

# 邮件主题命令格式: [类型] 内容
# 示例: [诊断] ALT-001, [状态] 所有实例, [报告] 每日汇总
SUBJECT_COMMAND_PATTERN = re.compile(r"^\[([^\]]+)\]\s*(.*)$")


@dataclass
class EmailMessage:
    """邮件消息"""
    message_id: str
    subject: str
    sender: str            # 发件人邮箱
    sender_name: str       # 发件人姓名
    body_text: str         # 纯文本正文
    body_html: str         # HTML正文
    thread_id: str         # 邮件线程ID (Message-ID)
    in_reply_to: str       # 回复目标Message-ID
    references: str         # References链
    command: str           # 解析出的命令类型 (diagnose/inspect/report/status/...)
    command_arg: str       # 命令参数 (如告警ID "ALT-001")
    raw_headers: dict      # 原始头部信息
    attachments: list[str] = field(default_factory=list)  # 附件文件名列表
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def from_raw(cls, raw_bytes: bytes, uid: str) -> "EmailMessage":
        """从原始邮件字节解析"""
        msg = BytesParser(policy=default).parsebytes(raw_bytes)

        # 解码头
        def decode_str(s):
            if not s:
                return "", ""
            parts = decode_header(s)
            decoded = []
            for part, charset in parts:
                if isinstance(part, bytes):
                    charset = charset or "utf-8"
                    try:
                        decoded.append(part.decode(charset, errors="replace"))
                    except (LookupError, TypeError):
                        decoded.append(part.decode("utf-8", errors="replace"))
                else:
                    decoded.append(part)
            return "".join(decoded), ""

        subject_raw = msg.get("Subject", "")
        subject, _ = decode_str(subject_raw)

        sender_raw = msg.get("From", "")
        # "User Name <user@example.com>" 或 "user@example.com"
        sender_name = ""
        sender_email = sender_raw
        if "<" in sender_raw:
            sender_name = sender_raw.split("<")[0].strip().strip('"')
            sender_email = sender_raw.split("<")[1].rstrip(">").strip()
        elif "@" in sender_raw:
            sender_email = sender_raw.strip()

        message_id = msg.get("Message-ID", f"<{uid}@email>").strip("<>")
        in_reply_to = msg.get("In-Reply-To", "").strip()
        references = msg.get("References", "").strip()
        thread_id = in_reply_to or message_id

        # 解析正文
        body_text = ""
        body_html = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = str(part.get("Content-Disposition", ""))
                if ct == "text/plain" and "attachment" not in cd:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        body_text = part.get_payload(decode=True).decode(charset, errors="replace")
                    except Exception:
                        body_text = part.get_payload(decode=True).decode("utf-8", errors="replace")
                elif ct == "text/html" and "attachment" not in cd:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        body_html = part.get_payload(decode=True).decode(charset, errors="replace")
                    except Exception:
                        body_html = part.get_payload(decode=True).decode("utf-8", errors="replace")
        else:
            charset = msg.get_content_charset() or "utf-8"
            try:
                raw_body = msg.get_payload(decode=True)
                if raw_body:
                    body = raw_body.decode(charset, errors="replace")
                else:
                    body = msg.get_payload()
            except Exception:
                body = msg.get_payload() or ""
            if msg.get_content_type() == "text/html":
                body_html = body
            else:
                body_text = body

        # 解析附件
        attachments = []
        for part in msg.walk():
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                fname = part.get_filename()
                if fname:
                    fn, _ = decode_str(fname)
                    attachments.append(fn)

        # 解析命令
        command, command_arg = cls._parse_command(subject)

        return cls(
            message_id=message_id,
            subject=subject,
            sender=sender_email,
            sender_name=sender_name,
            body_text=body_text.strip(),
            body_html=body_html,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
            command=command,
            command_arg=command_arg,
            raw_headers=dict(msg),
            attachments=attachments,
        )

    @staticmethod
    def _parse_command(subject: str) -> tuple[str, str]:
        """从主题解析命令"""
        # 清理主题中的 Re: FW: 等前缀
        clean = subject
        prefixes = ["Re:", "FW:", "Re[1]:", "RE:", "Fwd:"]
        for p in prefixes:
            if clean.startswith(p):
                clean = clean[len(p):].strip()

        match = SUBJECT_COMMAND_PATTERN.match(clean)
        if match:
            cmd = match.group(1).strip().lower()
            arg = match.group(2).strip()
            # 命令标准化
            cmd_map = {
                "诊断": "diagnose",
                "diagnose": "diagnose",
                "diag": "diagnose",
                "状态": "status",
                "status": "status",
                "stat": "status",
                "报告": "report",
                "report": "report",
                "巡检": "inspect",
                "inspect": "inspect",
                "风险": "risk",
                "risk": "risk",
                "sql": "sql_analyze",
                "sql_analyze": "sql_analyze",
            }
            return cmd_map.get(cmd, cmd), arg

        return "general", clean.strip()

    def build_context(self) -> dict:
        """构建发给Orchestrator的上下文"""
        return {
            "channel": "email",
            "message_id": self.message_id,
            "user_id": self.sender,
            "user_name": self.sender_name,
            "session_id": self.thread_id,
            "command": self.command,
            "command_arg": self.command_arg,
            "subject": self.subject,
            "body": self.body_text,
            "html_body": self.body_html,
            "attachments": self.attachments,
            "thread_id": self.thread_id,
            "in_reply_to": self.in_reply_to,
        }


@dataclass
class EmailThread:
    """邮件线程"""
    thread_id: str                  # 线程ID
    session_id: str                 # 对应的会话ID
    subject: str                   # 线程主题
    participants: list[str]        # 参与者邮箱列表
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_message_id: str = ""      # 最后一条消息ID
    message_count: int = 0          # 消息数量
    status: str = "active"         # active/closed
    metadata: dict = field(default_factory=dict)
