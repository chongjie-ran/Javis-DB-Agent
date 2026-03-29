"""Email Message Handler - 邮件消息处理器"""
import logging
import time
import uuid
import sqlite3
import os
from typing import Optional
from dataclasses import dataclass, field

from src.channels.base import BaseChannel, ChannelMessage, ChannelResponse
from src.channels.email.client import EmailClient
from src.channels.email.models import EmailMessage, EmailThread

logger = logging.getLogger(__name__)


# ==================== 配置 ====================

@dataclass
class EmailChannelConfig:
    """邮箱通道配置"""
    # IMAP配置
    imap_host: str = "imap.example.com"
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    use_ssl: bool = True

    # SMTP配置
    smtp_host: str = "smtp.example.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = True

    # Bot配置
    bot_address: str = ""           # Bot邮箱地址
    allowed_senders: list[str] = field(default_factory=list)  # 允许的发件人白名单，空=全部允许
    bot_name: str = "zCloud Agent"  # Bot显示名称

    # 轮询配置
    poll_interval: int = 30         # 轮询间隔（秒）
    batch_size: int = 20            # 每次最多处理邮件数
    mark_seen: bool = True         # 是否标记已读

    # 会话配置
    session_db_path: str = "data/email_sessions.db"  # 线程-会话映射数据库

    @classmethod
    def from_env(cls) -> "EmailChannelConfig":
        """从环境变量加载配置"""
        import os
        return cls(
            imap_host=os.getenv("EMAIL_IMAP_HOST", ""),
            imap_port=int(os.getenv("EMAIL_IMAP_PORT", "993")),
            imap_user=os.getenv("EMAIL_IMAP_USER", ""),
            imap_password=os.getenv("EMAIL_IMAP_PASSWORD", ""),
            smtp_host=os.getenv("EMAIL_SMTP_HOST", ""),
            smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "465")),
            smtp_user=os.getenv("EMAIL_SMTP_USER", ""),
            smtp_password=os.getenv("EMAIL_SMTP_PASSWORD", ""),
            bot_address=os.getenv("EMAIL_BOT_ADDRESS", os.getenv("EMAIL_SMTP_USER", "")),
            allowed_senders=[
                s.strip()
                for s in os.getenv("EMAIL_ALLOWED_SENDERS", "").split(",")
                if s.strip()
            ],
            bot_name=os.getenv("EMAIL_BOT_NAME", "zCloud Agent"),
            poll_interval=int(os.getenv("EMAIL_POLL_INTERVAL", "30")),
            batch_size=int(os.getenv("EMAIL_BATCH_SIZE", "20")),
            session_db_path=os.getenv("EMAIL_SESSION_DB", "data/email_sessions.db"),
        )


# ==================== 线程-会话映射管理器 ====================

class EmailSessionMapper:
    """
    邮件线程与会话ID的映射管理
    使用SQLite持久化存储
    """

    def __init__(self, db_path: str = "data/email_sessions.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._ensure_db()

    def _ensure_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS email_threads (
                    thread_id    TEXT PRIMARY KEY,
                    session_id   TEXT NOT NULL UNIQUE,
                    subject      TEXT,
                    created_at   REAL NOT NULL,
                    updated_at   REAL NOT NULL,
                    last_msg_id  TEXT,
                    msg_count    INTEGER DEFAULT 0,
                    status       TEXT DEFAULT 'active',
                    metadata     TEXT DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_threads_session ON email_threads(session_id);
            """)
            conn.commit()

    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def get_or_create_session(self, thread_id: str, subject: str = "") -> str:
        """
        获取或创建线程对应的会话ID

        Args:
            thread_id: 邮件线程ID
            subject: 线程主题

        Returns:
            str: session_id
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT session_id FROM email_threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()

            if row:
                # 更新活动时间
                conn.execute(
                    "UPDATE email_threads SET updated_at = ?, msg_count = msg_count + 1, last_msg_id = ? WHERE thread_id = ?",
                    (time.time(), "", thread_id),
                )
                conn.commit()
                return row["session_id"]

            # 新建会话
            session_id = str(uuid.uuid4())
            now = time.time()
            conn.execute(
                """INSERT INTO email_threads
                   (thread_id, session_id, subject, created_at, updated_at, msg_count)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (thread_id, session_id, subject, now, now),
            )
            conn.commit()
            logger.info(f"[Email] 新建邮件线程映射: thread={thread_id} -> session={session_id}")
            return session_id

    def get_thread_by_session(self, session_id: str) -> Optional[dict]:
        """通过session_id查找线程信息"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM email_threads WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_session_by_thread(self, thread_id: str) -> Optional[str]:
        """通过thread_id查找session_id"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT session_id FROM email_threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            return row["session_id"] if row else None

    def close_thread(self, thread_id: str):
        """关闭线程"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE email_threads SET status = 'closed', updated_at = ? WHERE thread_id = ?",
                (time.time(), thread_id),
            )
            conn.commit()


# ==================== EmailChannel ====================

class EmailChannel(BaseChannel):
    """
    邮箱消息通道
    集成到Orchestrator的消息入口
    """

    channel_name = "email"

    def __init__(self, config: EmailChannelConfig):
        self.config = config
        self._client: Optional[EmailClient] = None
        self._session_mapper = EmailSessionMapper(config.session_db_path)
        self._last_poll = 0.0

    @property
    def client(self) -> EmailClient:
        """获取邮件客户端（懒加载）"""
        if self._client is None:
            self._client = EmailClient(
                imap_host=self.config.imap_host,
                imap_port=self.config.imap_port,
                smtp_host=self.config.smtp_host,
                smtp_port=self.config.smtp_port,
                username=self.config.imap_user,
                password=self.config.imap_password,
                use_ssl=self.config.use_ssl,
                smtp_tls=self.config.smtp_tls,
                bot_address=self.config.bot_address,
            )
        return self._client

    def _is_allowed_sender(self, sender: str) -> bool:
        """检查发件人是否在白名单中"""
        if not self.config.allowed_senders:
            return True
        return any(
            allowed.lower() in sender.lower()
            for allowed in self.config.allowed_senders
        )

    # ==================== BaseChannel 实现 ====================

    async def receive(self) -> list[ChannelMessage]:
        """
        接收未读邮件，返回ChannelMessage列表

        Returns:
            list[ChannelMessage]: 消息列表
        """
        try:
            emails = self.client.fetch_unread(
                mark_seen=self.config.mark_seen,
                limit=self.config.batch_size,
            )
        except Exception as e:
            logger.error(f"[Email] 接收邮件失败: {e}")
            return []

        messages = []
        for email in emails:
            # 白名单检查
            if not self._is_allowed_sender(email.sender):
                logger.info(f"[Email] 忽略非白名单发件人: {email.sender}")
                continue

            # 获取或创建会话
            session_id = self._session_mapper.get_or_create_session(
                email.thread_id, email.subject
            )

            channel_msg = ChannelMessage(
                message_id=email.message_id,
                channel=self.channel_name,
                user_id=email.sender,
                session_id=session_id,
                content=email.body_text or email.subject,
                metadata={
                    "email": email,
                    "command": email.command,
                    "command_arg": email.command_arg,
                    "subject": email.subject,
                    "sender_name": email.sender_name,
                    "attachments": email.attachments,
                },
            )
            messages.append(channel_msg)
            subject_short = email.subject[:50]
            session_short = session_id[:8]
            logger.info(
                f"[Email] 收到邮件: from={email.sender} subject={subject_short} "
                f"cmd={email.command} session={session_short}"
            )

        self._last_poll = time.time()
        return messages

    async def send(
        self,
        user_id: str,
        content: str,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> ChannelResponse:
        """
        发送邮件

        Args:
            user_id: 收件人邮箱
            content: 邮件正文
            session_id: 会话ID（用于构建邮件线程）
            **kwargs: 额外参数 (subject/html_body/attachments/in_reply_to/...)

        Returns:
            ChannelResponse
        """
        try:
            subject = kwargs.get("subject", "zCloud Agent 回复")
            html_body = kwargs.get("html_body", "")
            attachments = kwargs.get("attachments", [])
            in_reply_to = kwargs.get("in_reply_to", "")
            references = kwargs.get("references", "")

            message_id = self.client.send(
                to=user_id,
                subject=subject,
                body=content,
                html_body=html_body,
                attachments=attachments if attachments else None,
                in_reply_to=in_reply_to,
                references=references,
            )

            return ChannelResponse(
                success=True,
                message=f"邮件已发送: {message_id}",
                data={"message_id": message_id},
                metadata={"to": user_id},
            )
        except Exception as e:
            logger.error(f"[Email] 发送邮件失败: {e}")
            return ChannelResponse(success=False, error=str(e))

    def map_session(self, channel_thread_id: str) -> Optional[str]:
        """映射邮件线程到会话ID"""
        return self._session_mapper.get_session_by_thread(channel_thread_id)

    def save_mapping(self, thread_id: str, session_id: str):
        """保存线程-会话映射"""
        with self._session_mapper._conn() as conn:
            now = time.time()
            conn.execute(
                """INSERT OR REPLACE INTO email_threads
                   (thread_id, session_id, updated_at)
                   VALUES (?, ?, ?)""",
                (thread_id, session_id, now),
            )
            conn.commit()


# ==================== EmailMessageHandler ====================

class EmailMessageHandler:
    """
    邮件消息处理器
    核心类：接收邮件 → 转发Orchestrator → 发送回复
    """

    def __init__(
        self,
        config: EmailChannelConfig,
        orchestrator,
    ):
        """
        Args:
            config: 邮箱通道配置
            orchestrator: OrchestratorAgent实例
        """
        self.channel = EmailChannel(config)
        self.orchestrator = orchestrator
        self._running = False

    async def process_emails(self) -> list[dict]:
        """
        处理所有未读邮件
        循环: receive → Orchestrator.process → send reply

        Returns:
            list[dict]: 处理结果列表
        """
        messages = await self.channel.receive()
        results = []

        for msg in messages:
            result = await self._process_single(msg)
            results.append(result)

        return results

    async def _process_single(self, msg: ChannelMessage) -> dict:
        """处理单封邮件"""
        email: EmailMessage = msg.metadata["email"]
        context = email.build_context()
        context["session_id"] = msg.session_id

        logger.info(
            f"[EmailHandler] 处理邮件: cmd={email.command} "
            f"arg={email.command_arg[:30] if email.command_arg else ''} "
            f"from={email.sender}"
        )

        try:
            # 调用 Orchestrator 处理
            if email.command != "general":
                goal = self._build_goal(email)
            else:
                goal = email.body_text or email.subject

            response = await self.orchestrator.process(goal, context)

            # 构建回复内容
            reply_text = response.content or "收到，已处理您的请求。"
            if not response.success:
                reply_text = f"处理失败: {response.error}"

            # 发送回复
            await self.channel.send(
                user_id=email.sender,
                content=reply_text,
                session_id=msg.session_id,
                subject=f"Re: {email.subject}",
                in_reply_to=email.message_id,
                references=(
                    f"{email.references} {email.message_id}"
                    if email.references
                    else email.message_id
                ),
                html_body=self._build_html_reply(reply_text, response),
            )

            return {
                "message_id": email.message_id,
                "success": response.success,
                "command": email.command,
                "response_preview": reply_text[:200],
            }

        except Exception as e:
            logger.error(f"[EmailHandler] 处理异常: {e}")
            # 发送错误回复
            try:
                await self.channel.send(
                    user_id=email.sender,
                    content=f"处理邮件时出错: {str(e)}",
                    subject=f"Re: {email.subject}",
                    in_reply_to=email.message_id,
                )
            except Exception:
                pass
            return {
                "message_id": email.message_id,
                "success": False,
                "error": str(e),
            }

    @staticmethod
    def _build_goal(email: EmailMessage) -> str:
        """根据命令类型构建发送给Orchestrator的目标"""
        cmd = email.command
        arg = email.command_arg

        if cmd == "diagnose":
            return f"请诊断告警 {arg}"
        elif cmd == "status":
            return "请查询所有实例状态"
        elif cmd == "report":
            return f"请生成报告: {arg}" if arg else "请生成每日汇总报告"
        elif cmd == "inspect":
            return "请进行健康巡检"
        elif cmd == "risk":
            return f"请评估风险: {arg}" if arg else "请评估当前系统风险"
        elif cmd == "sql_analyze":
            return f"请分析SQL: {arg}" if arg else email.body_text[:500]
        else:
            return email.body_text or email.subject

    @staticmethod
    def _build_html_reply(content: str, response) -> str:
        """构建HTML格式回复"""
        # 简单Markdown→HTML转换（处理粗体、代码块、换行）
        import re

        html_content = content
        # 代码块
        html_content = re.sub(r"```(\w*)\n(.*?)```", r"<pre><code>\2</code></pre>", html_content, flags=re.DOTALL)
        # 行内代码
        html_content = re.sub(r"`([^`]+)`", r"<code>\1</code>", html_content)
        # 粗体
        html_content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_content)
        # 换行
        html_content = html_content.replace("\n", "<br>")

        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 700px;">
            <div style="background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 16px 0;">
                <div style="white-space: pre-wrap; line-height: 1.8;">
                    {html_content}
                </div>
            </div>
            <p style="color: #888; font-size: 12px; border-top: 1px solid #eee; padding-top: 12px;">
                🤖 zCloud Agent 自动回复<br>
                时间: {time.strftime('%Y-%m-%d %H:%M:%S')}<br>
                <a href="#">查看历史对话</a>
            </p>
        </body>
        </html>
        """
