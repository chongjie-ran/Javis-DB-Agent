"""Email Client - IMAP接收 + SMTP发送"""
import ssl
import time
import uuid
import imaplib
import smtplib
import logging
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

from src.channels.email.models import EmailMessage

logger = logging.getLogger(__name__)


class EmailClient:
    """
    企业邮箱客户端
    - IMAP: 接收邮件
    - SMTP: 发送邮件
    """

    def __init__(
        self,
        imap_host: str,
        imap_port: int,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
        smtp_tls: bool = True,
        bot_address: str = "",
    ):
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.smtp_tls = smtp_tls
        self.bot_address = bot_address or username

        self._imap: Optional[imaplib.IMAP4_SSL] = None
        self._smtp: Optional[smtplib.SMTP] = None

        # 已处理的消息ID集合（防止重复处理）
        self._processed_ids: set[str] = set()

    # ==================== 连接管理 ====================

    def connect_imap(self):
        """建立IMAP连接"""
        if self.use_ssl:
            self._imap = imaplib.IMAP4_SSL(
                host=self.imap_host,
                port=self.imap_port,
                ssl_context=ssl.create_default_context(),
            )
        else:
            self._imap = imaplib.IMAP4(self.imap_host, self.imap_port)

        self._imap.login(self.username, self.password)
        logger.info(f"[Email] IMAP连接成功: {self.imap_host}:{self.imap_port}")

    def connect_smtp(self):
        """建立SMTP连接"""
        self._smtp = smtplib.SMTP(self.smtp_host, self.smtp_port)
        if self.smtp_tls:
            self._smtp.starttls(context=ssl.create_default_context())
        self._smtp.login(self.username, self.password)
        logger.info(f"[Email] SMTP连接成功: {self.smtp_host}:{self.smtp_port}")

    def disconnect(self):
        """断开所有连接"""
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None
        if self._smtp:
            try:
                self._smtp.quit()
            except Exception:
                pass
            self._smtp = None

    def __enter__(self):
        self.connect_imap()
        self.connect_smtp()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False

    # ==================== 邮件接收 ====================

    def fetch_unread(
        self,
        mailbox: str = "INBOX",
        search_criteria: str = "UNSEEN",
        mark_seen: bool = True,
        limit: int = 50,
    ) -> list[EmailMessage]:
        """
        获取未读邮件

        Args:
            mailbox: 邮箱文件夹
            search_criteria: 搜索条件 (UNSEEN/ALL/UNFLAGGED)
            mark_seen: 是否标记为已读
            limit: 最大数量

        Returns:
            list[EmailMessage]: 邮件列表
        """
        if not self._imap:
            self.connect_imap()

        self._imap.select(mailbox)

        # 搜索邮件
        status, message_ids = self._imap.search(None, search_criteria)
        if status != "OK":
            logger.warning(f"[Email] IMAP搜索失败: {status}")
            return []

        ids = message_ids[0].split()
        if not ids:
            return []

        # 限制数量（取最新的）
        ids = ids[-limit:]
        messages = []

        for uid in ids:
            try:
                # 获取原始邮件
                status, raw_data = self._imap.fetch(uid, "(RFC822)")
                if status != "OK" or not raw_data or not raw_data[0]:
                    continue

                raw_bytes = raw_data[0][1]
                email_msg = EmailMessage.from_raw(raw_bytes, uid.decode())

                # 跳过已处理的消息
                if email_msg.message_id in self._processed_ids:
                    continue

                # 跳过Bot自己发送的邮件
                if email_msg.sender.lower() == self.bot_address.lower():
                    continue

                messages.append(email_msg)
                self._processed_ids.add(email_msg.message_id)

                # 标记为已读
                if mark_seen:
                    try:
                        self._imap.store(uid, "+FLAGS", "\\Seen")
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"[Email] 解析邮件失败 (UID={uid}): {e}")

        return messages

    def mark_processed(self, message_id: str):
        """标记消息已处理"""
        self._processed_ids.add(message_id)

    def get_thread_messages(
        self,
        thread_id: str,
        mailbox: str = "INBOX",
    ) -> list[EmailMessage]:
        """
        获取线程所有邮件

        Args:
            thread_id: 线程ID (Message-ID)
            mailbox: 邮箱文件夹

        Returns:
            list[EmailMessage]: 按时间排序的邮件列表
        """
        if not self._imap:
            self.connect_imap()

        self._imap.select(mailbox)

        # 通过 References 或 In-Reply-To 查找线程邮件
        # 使用 ALL 搜索再过滤
        status, message_ids = self._imap.search(None, "ALL")
        if status != "OK":
            return []

        messages = []
        for uid in message_ids[0].split():
            try:
                status, raw_data = self._imap.fetch(uid, "(RFC822)")
                if status != "OK" or not raw_data or not raw_data[0]:
                    continue

                raw_bytes = raw_data[0][1]
                email_msg = EmailMessage.from_raw(raw_bytes, uid.decode())

                # 判断是否属于该线程
                if (
                    thread_id in (email_msg.thread_id, email_msg.message_id)
                    or thread_id in email_msg.references
                ):
                    messages.append(email_msg)

            except Exception as e:
                logger.error(f"[Email] 解析线程邮件失败 (UID={uid}): {e}")

        # 按时间排序
        messages.sort(key=lambda m: m.timestamp)
        return messages

    # ==================== 邮件发送 ====================

    def send(
        self,
        to: str | list[str],
        subject: str,
        body: str = "",
        html_body: str = "",
        in_reply_to: str = "",
        references: str = "",
        attachments: list[str] | None = None,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> str:
        """
        发送邮件

        Args:
            to: 收件人
            subject: 主题
            body: 纯文本正文
            html_body: HTML正文
            in_reply_to: 回复目标Message-ID
            references: References链
            attachments: 附件路径列表
            cc: 抄送
            bcc: 密送

        Returns:
            str: 发送的Message-ID
        """
        if not self._smtp:
            self.connect_smtp()

        if isinstance(to, str):
            to = [to]
        if isinstance(cc, str):
            cc = [cc]
        if isinstance(bcc, str):
            bcc = [bcc]

        msg = MIMEMultipart("mixed")
        msg["From"] = self.bot_address
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg["Message-ID"] = f"<{uuid.uuid4().hex}@javis-db-agent>"

        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)

        # 正文
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))
            if body:
                msg.attach(MIMEText(body, "plain", "utf-8"))
        elif body:
            msg.attach(MIMEText(body, "plain", "utf-8"))

        # 附件
        if attachments:
            for filepath in attachments:
                path = Path(filepath)
                if not path.exists():
                    logger.warning(f"[Email] 附件不存在: {filepath}")
                    continue
                try:
                    with open(path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    # 防止附件名中文乱码
                    encoded_name = f"=?utf-8?b?{(path.name.encode('utf-8')).hex()}?="
                    # 简化处理
                    part.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=("utf-8", "", path.name),
                    )
                    msg.attach(part)
                except Exception as e:
                    logger.error(f"[Email] 添加附件失败: {filepath}: {e}")

        all_recipients = to[:]
        if cc:
            all_recipients.extend(cc)
        if bcc:
            all_recipients.extend(bcc)

        self._smtp.sendmail(self.bot_address, all_recipients, msg.as_bytes())
        message_id = msg["Message-ID"].strip("<>")
        logger.info(f"[Email] 发送成功: {message_id} -> {to}")
        return message_id

    def send_reply(
        self,
        original: EmailMessage,
        content: str,
        html_content: str = "",
        attachments: list[str] | None = None,
    ) -> str:
        """
        回复邮件

        Args:
            original: 原邮件
            content: 回复内容
            html_content: HTML内容
            attachments: 附件

        Returns:
            str: 发送的Message-ID
        """
        # 构建回复主题
        subject = original.subject
        if not subject.startswith("Re:"):
            subject = f"Re: {subject}"
        # 去掉已有的多重复Re
        while subject.count("Re:") > 1:
            subject = subject.replace("Re: ", "", 1)

        # 构建 In-Reply-To（需要保留 angle brackets）
        in_reply_to_id = original.message_id
        if not in_reply_to_id.startswith("<"):
            in_reply_to_id = f"<{in_reply_to_id}"
        if not in_reply_to_id.endswith(">"):
            in_reply_to_id = f"{in_reply_to_id}>"

        # 构建 References
        refs = original.references or original.message_id
        if original.message_id and original.message_id not in refs:
            refs = f"{refs} {original.message_id}" if refs else original.message_id

        return self.send(
            to=original.sender,
            subject=subject,
            body=content,
            html_body=html_content,
            in_reply_to=in_reply_to_id,
            references=refs,
            attachments=attachments,
        )

    def send_alert(
        self,
        to: str | list[str],
        alert_title: str,
        alert_content: str,
        severity: str = "warning",
        attachments: list[str] | None = None,
    ) -> str:
        """
        发送告警通知

        Args:
            to: 收件人
            alert_title: 告警标题
            alert_content: 告警内容
            severity: 严重程度 (info/warning/critical)
            attachments: 附件

        Returns:
            str: 发送的Message-ID
        """
        icons = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
            "error": "❌",
            "success": "✅",
        }
        icon = icons.get(severity.lower(), "ℹ️")

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px;">
            <div style="background: {'#fff3cd' if severity == 'warning' else '#f8d7da' if severity in ('critical', 'error') else '#d1ecf1'};
                        border-left: 4px solid {'#ffc107' if severity == 'warning' else '#dc3545' if severity in ('critical', 'error') else '#17a2b8'};
                        padding: 16px; margin: 16px 0; border-radius: 4px;">
                <h3 style="margin: 0 0 8px;">{icon} {alert_title}</h3>
                <div style="white-space: pre-wrap;">{alert_content}</div>
            </div>
            <p style="color: #666; font-size: 12px;">
                本邮件由 Javis-DB-Agent Agent 自动发送<br>
                时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
            </p>
        </body>
        </html>
        """

        text_body = f"{icon} {alert_title}\n\n{alert_content}\n\n--\nzCloud Agent 自动发送 | {time.strftime('%Y-%m-%d %H:%M:%S')}"

        return self.send(
            to=to,
            subject=f"[{severity.upper()}] {alert_title}",
            body=text_body,
            html_body=html_body,
            attachments=attachments,
        )

    def send_report(
        self,
        to: str | list[str],
        report_title: str,
        report_content: str,
        html_content: str = "",
        attachments: list[str] | None = None,
    ) -> str:
        """
        发送报告邮件

        Args:
            to: 收件人
            report_title: 报告标题
            report_content: 报告文本内容
            html_content: HTML内容
            attachments: 附件

        Returns:
            str: 发送的Message-ID
        """
        if not html_content:
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 800px;">
                <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 8px;">
                    📊 {report_title}
                </h2>
                <div style="white-space: pre-wrap; line-height: 1.6;">{report_content}</div>
                <hr style="margin-top: 24px;">
                <p style="color: #666; font-size: 12px;">
                    Javis-DB-Agent Agent 报告生成<br>
                    生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
                </p>
            </body>
            </html>
            """
        else:
            html_body = html_content

        return self.send(
            to=to,
            subject=f"[报告] {report_title}",
            body=report_content,
            html_body=html_body,
            attachments=attachments,
        )
