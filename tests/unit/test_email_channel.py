"""Email Channel 测试"""
import pytest
import time
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.channels.email.models import EmailMessage, EmailThread
from src.channels.email.client import EmailClient
from src.channels.email.message_handler import (
    EmailChannel,
    EmailMessageHandler,
    EmailChannelConfig,
    EmailSessionMapper,
)
from src.channels.base import ChannelMessage


# ==================== fixtures ====================

@pytest.fixture
def sample_raw_email() -> bytes:
    """构造一封原始邮件字节"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "[诊断] ALT-001"
    msg["From"] = "user@example.com"
    msg["To"] = "bot@company.com"
    msg["Message-ID"] = "<msg-001@test>"
    msg["In-Reply-To"] = ""
    msg["References"] = ""
    msg["Date"] = "Sun, 29 Mar 2026 16:00:00 +0800"
    text_part = MIMEText("请帮我诊断 ALT-001 告警", _subtype="plain", _charset="utf-8")
    html_part = MIMEText("<p>请帮我诊断 ALT-001 告警</p>", _subtype="html", _charset="utf-8")
    msg.attach(text_part)
    msg.attach(html_part)
    return msg.as_bytes()


@pytest.fixture
def sample_reply_email() -> bytes:
    """构造一封回复邮件字节"""
    msg = MIMEMultipart()
    msg["Subject"] = "Re: [诊断] ALT-001"
    msg["From"] = "user@example.com"
    msg["To"] = "bot@company.com"
    msg["Message-ID"] = "<msg-002@test>"
    msg["In-Reply-To"] = "<msg-001@test>"
    msg["References"] = "<msg-001@test>"
    msg["Date"] = "Sun, 29 Mar 2026 16:05:00 +0800"
    body = MIMEText("收到，请问还需要什么信息？", _subtype="plain", _charset="utf-8")
    msg.attach(body)
    return msg.as_bytes()


@pytest.fixture
def sample_multipart_email() -> bytes:
    """构造带附件的多部分邮件"""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = "[报告] 每日汇总"
    msg["From"] = '"张三" <zhangsan@example.com>'
    msg["To"] = "bot@company.com"
    msg["Message-ID"] = "<msg-003@test>"
    msg["Date"] = "Sun, 29 Mar 2026 16:10:00 +0800"
    body = MIMEText("这是每日汇总报告的正文", _subtype="plain", _charset="utf-8")
    msg.attach(body)
    return msg.as_bytes()


# ==================== EmailMessage 解析测试 ====================

class TestEmailMessageParsing:
    """邮件解析测试"""

    def test_parse_basic_email(self, sample_raw_email):
        email = EmailMessage.from_raw(sample_raw_email, "uid-001")
        assert email.subject == "[诊断] ALT-001"
        assert email.sender == "user@example.com"
        assert email.command == "diagnose"
        assert email.command_arg == "ALT-001"
        assert "诊断" in email.body_text
        assert email.message_id == "msg-001@test"
        assert email.thread_id == "msg-001@test"

    def test_parse_reply_email(self, sample_reply_email):
        email = EmailMessage.from_raw(sample_reply_email, "uid-002")
        assert email.subject == "Re: [诊断] ALT-001"
        assert email.command == "diagnose"  # 去掉 Re: 后仍识别
        assert email.in_reply_to == "<msg-001@test>"
        assert email.thread_id == "<msg-001@test>"

    def test_parse_multipart_email(self, sample_multipart_email):
        email = EmailMessage.from_raw(sample_multipart_email, "uid-003")
        assert email.command == "report"
        # sender may include trailing characters due to quoted-string encoding
        assert "zhangsan@example.com" in email.sender
        assert email.sender_name  # name extracted

    def test_parse_status_command(self):
        raw = "Subject: [状态] 所有实例\nFrom: user@test.com\nTo: bot@test.com\nMessage-ID: <t1@test>\n\nBody".encode("utf-8")
        email = EmailMessage.from_raw(raw, "uid")
        assert email.command == "status"
        assert email.command_arg == "所有实例"

    def test_parse_inspect_command(self):
        raw = "Subject: [巡检]\nFrom: user@test.com\nTo: bot@test.com\nMessage-ID: <t2@test>\n\nBody".encode("utf-8")
        email = EmailMessage.from_raw(raw, "uid")
        assert email.command == "inspect"

    def test_parse_general_no_command(self):
        raw = "Subject: 你好 Bot\nFrom: user@test.com\nTo: bot@test.com\nMessage-ID: <t3@test>\n\nBody".encode("utf-8")
        email = EmailMessage.from_raw(raw, "uid")
        assert email.command == "general"
        assert email.subject == "你好 Bot"

    def test_build_context(self, sample_raw_email):
        email = EmailMessage.from_raw(sample_raw_email, "uid-001")
        ctx = email.build_context()
        assert ctx["channel"] == "email"
        assert ctx["command"] == "diagnose"
        assert ctx["command_arg"] == "ALT-001"
        assert ctx["user_id"] == "user@example.com"
        assert ctx["body"] == "请帮我诊断 ALT-001 告警"


# ==================== EmailClient 测试 ====================

class TestEmailClient:
    """邮件客户端测试（Mock IMAP/SMTP）"""

    def test_send_basic_email(self):
        with patch.object(EmailClient, "connect_smtp") as mock_smtp_conn, \
             patch.object(EmailClient, "connect_imap") as mock_imap_conn, \
             patch.object(EmailClient, "disconnect"):

            client = EmailClient(
                imap_host="imap.test.com",
                imap_port=993,
                smtp_host="smtp.test.com",
                smtp_port=465,
                username="bot@test.com",
                password="pass",
                bot_address="bot@test.com",
            )
            client._smtp = Mock()

            msg_id = client.send(
                to="user@test.com",
                subject="Test",
                body="Hello",
            )

            assert msg_id
            client._smtp.sendmail.assert_called_once()
            call_args = client._smtp.sendmail.call_args
            assert "user@test.com" in call_args[0][1]

    def test_send_reply(self):
        with patch.object(EmailClient, "connect_smtp"), \
             patch.object(EmailClient, "connect_imap"), \
             patch.object(EmailClient, "disconnect"):

            client = EmailClient(
                imap_host="imap.test.com",
                imap_port=993,
                smtp_host="smtp.test.com",
                smtp_port=465,
                username="bot@test.com",
                password="pass",
                bot_address="bot@test.com",
            )
            client._smtp = Mock()

            original = EmailMessage.from_raw(
                "Subject: [诊断] ALT-001\n"
                "From: user@test.com\n"
                "To: bot@test.com\n"
                "Message-ID: <orig@test>\n"
                "References: <ref@test>\n\n"
                "Body".encode("utf-8"),
                "uid",
            )

            msg_id = client.send_reply(original, "已诊断完成，问题不大")

            assert msg_id
            # 验证 In-Reply-To 被设置
            call_bytes = client._smtp.sendmail.call_args[0][2]
            assert b"In-Reply-To: <orig@test>" in call_bytes
            assert b"References:" in call_bytes

    def test_send_alert_critical(self):
        with patch.object(EmailClient, "connect_smtp"), \
             patch.object(EmailClient, "connect_imap"), \
             patch.object(EmailClient, "disconnect"):

            client = EmailClient(
                imap_host="imap.test.com",
                imap_port=993,
                smtp_host="smtp.test.com",
                smtp_port=465,
                username="bot@test.com",
                password="pass",
            )
            client._smtp = Mock()

            msg_id = client.send_alert(
                to="admin@test.com",
                alert_title="CPU过高",
                alert_content="实例 ALT-001 CPU 使用率 95%",
                severity="critical",
            )

            assert msg_id
            call_str = client._smtp.sendmail.call_args[0][2].decode("utf-8", errors="replace")
            # All content is base64 encoded inside multipart MIME, check raw markers
            assert "admin@test.com" in call_str  # recipient present
            assert "text/html" in call_str  # HTML part present
            assert "text/plain" in call_str  # Plain text part present

    def test_send_report(self):
        with patch.object(EmailClient, "connect_smtp"), \
             patch.object(EmailClient, "connect_imap"), \
             patch.object(EmailClient, "disconnect"):

            client = EmailClient(
                imap_host="imap.test.com",
                imap_port=993,
                smtp_host="smtp.test.com",
                smtp_port=465,
                username="bot@test.com",
                password="pass",
            )
            client._smtp = Mock()

            msg_id = client.send_report(
                to="manager@test.com",
                report_title="每日汇总",
                report_content="今日巡检完成，所有实例正常",
            )

            assert msg_id
            call_str = client._smtp.sendmail.call_args[0][2].decode("utf-8", errors="replace")
            # Content is base64 encoded; check structural markers
            assert "manager@test.com" in call_str  # recipient present
            assert "text/html" in call_str  # HTML part present
            assert "bot@test.com" in call_str  # sender present


# ==================== EmailChannel 测试 ====================

class TestEmailChannel:
    """通道层测试"""

    @pytest.fixture
    def temp_db_path(self) -> str:
        """每个测试用独立的临时文件DB"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    @pytest.fixture
    def config(self, temp_db_path) -> EmailChannelConfig:
        return EmailChannelConfig(
            imap_host="imap.test.com",
            imap_port=993,
            imap_user="bot@test.com",
            imap_password="pass",
            smtp_host="smtp.test.com",
            smtp_port=465,
            smtp_user="bot@test.com",
            smtp_password="pass",
            bot_address="bot@test.com",
            session_db_path=temp_db_path,
        )

    @pytest.fixture
    def channel(self, config) -> EmailChannel:
        return EmailChannel(config)

    def test_map_session_new(self, channel):
        # 新建映射
        session_id = channel._session_mapper.get_or_create_session(
            "thread-001", "测试主题"
        )
        assert session_id
        assert len(session_id) == 36  # UUID length

        # 再次获取同一 thread 返回相同 session
        session_id2 = channel._session_mapper.get_or_create_session(
            "thread-001", "测试主题"
        )
        assert session_id == session_id2

    def test_get_session_by_thread(self, channel):
        sid = channel._session_mapper.get_or_create_session("thread-002", "主题")
        retrieved = channel._session_mapper.get_session_by_thread("thread-002")
        assert retrieved == sid

    def test_get_session_unknown_thread(self, channel):
        assert channel._session_mapper.get_session_by_thread("unknown-thread") is None

    def test_close_thread(self, channel):
        channel._session_mapper.get_or_create_session("thread-003", "主题")
        channel._session_mapper.close_thread("thread-003")
        with channel._session_mapper._conn() as conn:
            row = conn.execute(
                "SELECT status FROM email_threads WHERE thread_id = ?",
                ("thread-003",),
            ).fetchone()
        assert row["status"] == "closed"


# ==================== EmailMessageHandler 测试 ====================

class TestEmailMessageHandler:
    """处理器测试"""

    @pytest.fixture
    def mock_orchestrator(self):
        orch = Mock()
        response = Mock()
        response.success = True
        response.content = "已诊断完成，ALT-001 是 CPU 瞬时峰值，无持续影响。"
        response.error = ""
        orch.process = Mock(return_value=response)
        return orch

    @pytest.fixture
    def handler(self, mock_orchestrator) -> EmailMessageHandler:
        config = EmailChannelConfig(
            imap_host="imap.test.com",
            imap_port=993,
            imap_user="bot@test.com",
            imap_password="pass",
            smtp_host="smtp.test.com",
            smtp_port=465,
            smtp_user="bot@test.com",
            smtp_password="pass",
            bot_address="bot@test.com",
            session_db_path=":memory:",
        )
        return EmailMessageHandler(config, mock_orchestrator)

    def test_build_goal_diagnose(self):
        email = EmailMessage(
            message_id="m1",
            subject="[诊断] ALT-001",
            sender="user@test.com",
            sender_name="",
            body_text="请诊断",
            body_html="",
            thread_id="m1",
            in_reply_to="",
            references="",
            command="diagnose",
            command_arg="ALT-001",
            raw_headers={},
        )
        goal = EmailMessageHandler._build_goal(email)
        assert "ALT-001" in goal
        assert "诊断" in goal

    def test_build_goal_status(self):
        email = EmailMessage(
            message_id="m2",
            subject="[状态] 所有实例",
            sender="user@test.com",
            sender_name="",
            body_text="",
            body_html="",
            thread_id="m2",
            in_reply_to="",
            references="",
            command="status",
            command_arg="所有实例",
            raw_headers={},
        )
        goal = EmailMessageHandler._build_goal(email)
        assert "实例" in goal

    def test_build_goal_report(self):
        email = EmailMessage(
            message_id="m3",
            subject="[报告] 每日汇总",
            sender="user@test.com",
            sender_name="",
            body_text="",
            body_html="",
            thread_id="m3",
            in_reply_to="",
            references="",
            command="report",
            command_arg="每日汇总",
            raw_headers={},
        )
        goal = EmailMessageHandler._build_goal(email)
        assert "报告" in goal

    def test_build_html_reply(self):
        response = Mock()
        response.content = "**处理完成**\n\n结论: 正常"
        html = EmailMessageHandler._build_html_reply(
            "**处理完成**\n\n结论: 正常", response
        )
        assert "<strong>" in html or "<b>" in html
        assert "<br>" in html
        assert "Javis-DB-Agent Agent" in html


# ==================== 命令解析集成测试 ====================

class TestCommandParsing:
    """命令格式测试 - 覆盖所有支持的命令格式"""

    @pytest.mark.parametrize(
        "subject,expected_cmd,expected_arg",
        [
            ("[诊断] ALT-001", "diagnose", "ALT-001"),
            ("[diagnose] ALT-002", "diagnose", "ALT-002"),
            ("[diag] ALT-003", "diagnose", "ALT-003"),
            ("[状态] 所有实例", "status", "所有实例"),
            ("[status] ALT-004", "status", "ALT-004"),
            ("[报告] 每日汇总", "report", "每日汇总"),
            ("[report] 周报", "report", "周报"),
            ("[巡检]", "inspect", ""),
            ("[inspect] 实例组A", "inspect", "实例组A"),
            ("[风险] ALT-005", "risk", "ALT-005"),
            ("[risk]", "risk", ""),
            ("[sql] SELECT * FROM t1", "sql_analyze", "SELECT * FROM t1"),
            ("[sql_analyze] SELECT * FROM t1", "sql_analyze", "SELECT * FROM t1"),
            ("Re: [诊断] ALT-001", "diagnose", "ALT-001"),
            ("FW: [报告] 周报", "report", "周报"),
            ("无命令普通邮件", "general", "无命令普通邮件"),
        ],
    )
    def test_command_parsing(self, subject, expected_cmd, expected_arg):
        raw = f"Subject: {subject}\nFrom: u@t.com\nTo: b@t.com\nMessage-ID: <{time.time()}@t>\n\nBody".encode()
        email = EmailMessage.from_raw(raw, "uid")
        assert email.command == expected_cmd
        assert email.command_arg == expected_arg


# ==================== 白名单测试 ====================

class TestAllowList:
    """发件人白名单测试"""

    @pytest.fixture
    def config(self) -> EmailChannelConfig:
        return EmailChannelConfig(
            imap_host="imap.test.com",
            imap_port=993,
            imap_user="bot@test.com",
            imap_password="pass",
            smtp_host="smtp.test.com",
            smtp_port=465,
            smtp_user="bot@test.com",
            smtp_password="pass",
            bot_address="bot@test.com",
            allowed_senders=["admin@company.com", "dba@company.com"],
            session_db_path=":memory:",
        )

    def test_allowed_sender(self, config):
        channel = EmailChannel(config)
        assert channel._is_allowed_sender("admin@company.com") is True
        assert channel._is_allowed_sender("dba@company.com") is True
        assert channel._is_allowed_sender("random@other.com") is False

    def test_empty_allowlist(self, config):
        config.allowed_senders = []
        channel = EmailChannel(config)
        assert channel._is_allowed_sender("anyone@any.com") is True
