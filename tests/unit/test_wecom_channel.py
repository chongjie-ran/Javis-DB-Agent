"""企业微信(wecom)通道测试"""
import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from src.channels.wecom.models import WecomIncomingMessage, WecomMessage
from src.channels.wecom.message_handler import WecomMessageHandler
from src.channels.wecom.wecom_channel import WecomChannel
from src.channels.wecom.config import WecomChannelConfig
from src.channels.base import ChannelMessage


# ==================== helpers ====================

def _xml_body(content: str) -> bytes:
    """将XML字符串编码为bytes（兼容Python 3.14）"""
    return content.encode("utf-8")


# ==================== fixtures ====================

@pytest.fixture
def wecom_config() -> WecomChannelConfig:
    return WecomChannelConfig(
        corp_id="test-corp-id",
        agent_id=1000001,
        corp_secret="test-secret",
        callback_token="test-token",
        callback_aes_key="",
        callback_url="http://localhost:8000/api/v1/channels/wecom/callback",
        api_base_url="https://qyapi.weixin.qq.com",
        enabled=True,
        alert_target="test-chat-id",
        alert_push_enabled=True,
        session_enabled=True,
        auto_create_session=True,
        max_message_length=2048,
    )


@pytest.fixture
def wecom_handler(wecom_config) -> WecomMessageHandler:
    return WecomMessageHandler(wecom_config)


@pytest.fixture
def wecom_channel(wecom_config) -> WecomChannel:
    return WecomChannel(wecom_config)


# ==================== WecomMessage 测试 ====================

class TestWecomMessage:
    """WecomMessage 构造测试"""

    def test_text_message_creation(self):
        msg = WecomMessage.text_message(
            chatid="user-001",
            content="Hello, Javis-DB-Agent!",
            chat_type=1,
        )
        assert msg.chat_type == 1
        assert msg.chatid == "user-001"
        assert msg.msgtype == "text"
        assert msg.text["content"] == "Hello, Javis-DB-Agent!"

    def test_markdown_message_creation(self):
        msg = WecomMessage.markdown_message(
            chatid="group-001",
            content="## Diagnosis Report\n\n- CPU: OK\n- Memory: OK",
            chat_type=2,
        )
        assert msg.chat_type == 2
        assert msg.msgtype == "markdown"
        assert "## Diagnosis Report" in msg.text["content"]

    def test_image_message_creation(self):
        msg = WecomMessage.image_message(
            chatid="user-001",
            media_id="MEDIA_ID_xxx",
            chat_type=1,
        )
        assert msg.msgtype == "image"
        assert msg.text["media_id"] == "MEDIA_ID_xxx"

    def test_api_payload_text(self):
        msg = WecomMessage.text_message(chatid="user-001", content="test")
        payload = msg.to_api_payload()
        assert payload["chat_type"] == 1
        assert payload["chatid"] == "user-001"
        assert payload["msgtype"] == "text"
        assert payload["text"]["content"] == "test"


# ==================== WecomIncomingMessage 测试 ====================

class TestWecomIncomingMessage:
    """WecomIncomingMessage 解析测试"""

    def test_parse_text_message(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[test-corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[Please diagnose ALT-001]]></Content>"
            "<MsgId>1234567890</MsgId>"
            "<AgentID>1000001</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.from_user_name == "user-001"
        assert msg.msg_type == "text"
        assert msg.content == "Please diagnose ALT-001"
        assert msg.msg_id == "1234567890"
        assert msg.agent_id == 1000001
        assert msg.is_text is True
        assert msg.is_group is False

    def test_parse_group_message(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[test-corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-002]]></FromUserName>"
            "<CreateTime>1711700001</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[@Javis-DB-Agent check status]]></Content>"
            "<MsgId>1234567891</MsgId>"
            "<AgentID>1000001</AgentID>"
            "<ChatId><![CDATA[group-001]]></ChatId>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.is_group is True
        assert msg.chat_id == "group-001"
        assert msg.chat_type == "group"

    def test_parse_image_message(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[test-corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700002</CreateTime>"
            "<MsgType><![CDATA[image]]></MsgType>"
            "<PicUrl><![CDATA[http://xxx.jpg]]></PicUrl>"
            "<MediaId><![CDATA[MEDIA_ID_ABC]]></MediaId>"
            "<MsgId>1234567892</MsgId>"
            "<AgentID>1000001</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.msg_type == "image"
        assert msg.media_id == "MEDIA_ID_ABC"

    def test_parse_file_message(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[test-corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700003</CreateTime>"
            "<MsgType><![CDATA[file]]></MsgType>"
            "<MediaId><![CDATA[MEDIA_ID_FILE]]></MediaId>"
            "<FileName><![CDATA[report.pdf]]></FileName>"
            "<FileSize><![CDATA[102400]]></FileSize>"
            "<MsgId>1234567893</MsgId>"
            "<AgentID>1000001</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.msg_type == "file"
        assert msg.file_name == "report.pdf"
        assert msg.file_size == "102400"

    def test_parse_link_message(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[test-corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700004</CreateTime>"
            "<MsgType><![CDATA[link]]></MsgType>"
            "<Title><![CDATA[Monitoring Report]]></Title>"
            "<Description><![CDATA[This is a monitoring report]]></Description>"
            "<Url><![CDATA[https://example.com/report]]></Url>"
            "<MsgId>1234567894</MsgId>"
            "<AgentID>1000001</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.msg_type == "link"
        assert msg.link["title"] == "Monitoring Report"
        assert msg.link["url"] == "https://example.com/report"

    def test_to_content_text(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[Diagnose ALT-001]]></Content>"
            "<MsgId>999</MsgId>"
            "<AgentID>1</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.to_content() == "Diagnose ALT-001"

    def test_to_content_image(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[image]]></MsgType>"
            "<MediaId><![CDATA[xxx]]></MediaId>"
            "<MsgId>999</MsgId>"
            "<AgentID>1</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.to_content() == "[图片消息]"

    def test_to_content_file(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[file]]></MsgType>"
            "<MediaId><![CDATA[xxx]]></MediaId>"
            "<FileName><![CDATA[log.txt]]></FileName>"
            "<MsgId>999</MsgId>"
            "<AgentID>1</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.to_content() == "[文件: log.txt]"

    def test_is_alert_true(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[Alert: CPU usage over 90%]]></Content>"
            "<MsgId>999</MsgId>"
            "<AgentID>1</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.is_alert is True

    def test_is_alert_false(self):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[Hello, please check status]]></Content>"
            "<MsgId>999</MsgId>"
            "<AgentID>1</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.is_alert is False

    def test_parse_json_payload(self):
        payload = {
            "msgId": "1234567890",
            "toUserName": "test-corp",
            "fromUserName": "user-001",
            "createTime": 1711700000,
            "msgType": "text",
            "content": "Test message",
            "agentId": 1000001,
        }
        msg = WecomIncomingMessage.from_json_payload(payload)
        assert msg.msg_id == "1234567890"
        assert msg.content == "Test message"
        assert msg.msg_type == "text"


# ==================== WecomMessageHandler 测试 ====================

class TestWecomMessageHandler:
    """消息处理器测试"""

    def test_parse_callback_text(self, wecom_handler):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[Test]]></Content>"
            "<MsgId>999</MsgId>"
            "<AgentID>1000001</AgentID>"
            "</xml>"
        )
        msg = wecom_handler.parse_callback(_xml_body(xml), {})
        assert msg is not None
        assert msg.from_user_name == "user-001"
        assert msg.content == "Test"

    def test_parse_callback_invalid(self, wecom_handler):
        body = b"not xml at all"
        msg = wecom_handler.parse_callback(body, {})
        assert msg is None

    def test_session_mapping_single_chat(self, wecom_handler):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[test]]></Content>"
            "<MsgId>999</MsgId>"
            "<AgentID>1</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))

        # 无session时应返回None
        assert wecom_handler.get_session_id(msg) is None

        # 设置映射
        wecom_handler.set_session_id(msg, "session-123")

        # 获取映射
        assert wecom_handler.get_session_id(msg) == "session-123"

    def test_session_mapping_group_chat(self, wecom_handler):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[test]]></Content>"
            "<MsgId>999</MsgId>"
            "<AgentID>1</AgentID>"
            "<ChatId><![CDATA[group-001]]></ChatId>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        assert msg.is_group is True

        wecom_handler.set_session_id(msg, "session-group-456")
        assert wecom_handler.get_session_id(msg) == "session-group-456"

    def test_remove_session(self, wecom_handler):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[test]]></Content>"
            "<MsgId>999</MsgId>"
            "<AgentID>1</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        wecom_handler.set_session_id(msg, "session-789")
        assert wecom_handler.get_session_id(msg) == "session-789"

        wecom_handler.remove_session(msg)
        assert wecom_handler.get_session_id(msg) is None

    def test_to_channel_message(self, wecom_handler):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[Diagnose ALT-001]]></Content>"
            "<MsgId>msg-001</MsgId>"
            "<AgentID>1000001</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        channel_msg = wecom_handler.to_channel_message(msg)

        assert isinstance(channel_msg, ChannelMessage)
        assert channel_msg.channel == "wecom"
        assert channel_msg.user_id == "user-001"
        assert channel_msg.content == "Diagnose ALT-001"
        assert channel_msg.message_id == "msg-001"
        assert channel_msg.metadata["agent_id"] == 1000001

    @pytest.mark.asyncio
    async def test_get_access_token_success(self, wecom_handler):
        mock_response = {
            "errcode": 0,
            "errmsg": "ok",
            "access_token": "test-access-token-xxx",
            "expires_in": 7200,
        }

        mock_json_response = Mock()
        mock_json_response.json = Mock(return_value=mock_response)

        with patch("httpx.AsyncClient") as mock_client_class:
            # Build a proper async mock client
            mock_instance = MagicMock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock()

            # Make post return a coroutine that yields the mock response
            async def mock_get(*args, **kwargs):
                return mock_json_response
            mock_instance.get = mock_get

            mock_client_class.return_value = mock_instance

            token = await wecom_handler.get_access_token()
            assert token == "test-access-token-xxx"

    @pytest.mark.asyncio
    async def test_send_text(self, wecom_handler):
        mock_send_response = {"errcode": 0, "errmsg": "ok"}

        with patch.object(wecom_handler, "get_access_token", new_callable=AsyncMock) as mock_token, \
             patch("httpx.AsyncClient") as mock_client_class:
            mock_token.return_value = "test-token"

            mock_response_obj = MagicMock()
            mock_response_obj.__aenter__ = AsyncMock()
            mock_response_obj.__aexit__ = AsyncMock()
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                return_value=MagicMock(json=Mock(return_value=mock_send_response))
            )
            mock_response_obj.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_response_obj

            result = await wecom_handler.send_text("user-001", "Test message", chat_type=1)
            assert result["errcode"] == 0


# ==================== WecomChannel 测试 ====================

class TestWecomChannel:
    """通道层测试"""

    def test_channel_initialization(self, wecom_channel):
        assert wecom_channel.channel_name == "wecom"
        assert wecom_channel.config.enabled is True

    @pytest.mark.asyncio
    async def test_channel_send_disabled(self, wecom_config):
        wecom_config.enabled = False
        channel = WecomChannel(wecom_config)
        response = await channel.send("user-001", "test")
        assert response.success is False
        assert "disabled" in response.error

    @pytest.mark.asyncio
    async def test_handle_callback_invalid_body(self, wecom_channel):
        with pytest.raises(ValueError):
            await wecom_channel.handle_callback(b"not xml", {})

    @pytest.mark.asyncio
    async def test_handle_callback_text_message(self, wecom_channel):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[Diagnose ALT-001]]></Content>"
            "<MsgId>msg-123</MsgId>"
            "<AgentID>1000001</AgentID>"
            "</xml>"
        )

        mock_orch = Mock()
        mock_response = Mock()
        mock_response.success = True
        mock_response.content = "Diagnosis complete."
        mock_orch.handle_chat = AsyncMock(return_value=mock_response)

        # Set _orchestrator directly (bypass property)
        wecom_channel._orchestrator = mock_orch

        with patch.object(wecom_channel.handler, "get_access_token", new_callable=AsyncMock) as mock_token, \
             patch.object(wecom_channel.handler, "send_text", new_callable=AsyncMock) as mock_send:
            mock_token.return_value = "test-token"
            mock_send.return_value = {"errcode": 0}

            channel_msg = await wecom_channel.handle_callback(_xml_body(xml), {})

            assert channel_msg.channel == "wecom"
            assert channel_msg.user_id == "user-001"
            assert channel_msg.content == "Diagnose ALT-001"

    @pytest.mark.asyncio
    async def test_handle_callback_non_text_ignored(self, wecom_channel):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[image]]></MsgType>"
            "<MediaId><![CDATA[xxx]]></MediaId>"
            "<MsgId>img-123</MsgId>"
            "<AgentID>1000001</AgentID>"
            "</xml>"
        )

        channel_msg = await wecom_channel.handle_callback(_xml_body(xml), {})
        assert channel_msg.content == "[图片消息]"
        assert channel_msg.metadata["msg_type"] == "image"

    @pytest.mark.asyncio
    async def test_push_alert(self, wecom_channel):
        with patch.object(wecom_channel.handler, "send_alert", new_callable=AsyncMock) as mock_alert:
            mock_alert.return_value = {"errcode": 0, "errmsg": "ok"}

            result = await wecom_channel.push_alert(
                content="CPU Alert: ALT-001 usage 95%",
                alert_level="critical",
            )

            assert result.success is True
            mock_alert.assert_called_once()

    def test_map_session(self, wecom_channel):
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-001]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[test]]></Content>"
            "<MsgId>999</MsgId>"
            "<AgentID>1</AgentID>"
            "</xml>"
        )
        msg = WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
        wecom_channel.handler.set_session_id(msg, "session-abc")

        found = wecom_channel.map_session("user:user-001")
        assert found == "session-abc"

    def test_save_mapping(self, wecom_channel):
        wecom_channel.save_mapping("user:user-002", "session-xyz")
        found = wecom_channel.map_session("user:user-002")
        assert found == "session-xyz"


# ==================== 集成测试 ====================

class TestWecomChannelIntegration:
    """通道集成测试"""

    @pytest.mark.asyncio
    async def test_full_message_flow(self, wecom_channel):
        """
        完整消息流程测试:
        1. 接收回调
        2. 解析消息
        3. 转发Orchestrator
        4. 发送响应
        """
        xml = (
            "<xml>"
            "<ToUserName><![CDATA[corp]]></ToUserName>"
            "<FromUserName><![CDATA[user-flow-test]]></FromUserName>"
            "<CreateTime>1711700000</CreateTime>"
            "<MsgType><![CDATA[text]]></MsgType>"
            "<Content><![CDATA[Please diagnose ALT-001]]></Content>"
            "<MsgId>flow-test-001</MsgId>"
            "<AgentID>1000001</AgentID>"
            "</xml>"
        )

        mock_response = Mock()
        mock_response.success = True
        mock_response.content = "Diagnosis complete: ALT-001 CPU peak, no sustained impact."

        mock_orch = Mock()
        mock_orch.handle_chat = AsyncMock(return_value=mock_response)

        # Set _orchestrator directly (bypass property)
        wecom_channel._orchestrator = mock_orch

        with patch.object(wecom_channel.handler, "get_access_token", new_callable=AsyncMock) as mock_token, \
             patch.object(wecom_channel.handler, "send_text", new_callable=AsyncMock) as mock_send:
            mock_token.return_value = "test-token"
            mock_send.return_value = {"errcode": 0}

            channel_msg = await wecom_channel.handle_callback(_xml_body(xml), {})

            assert channel_msg.content == "Please diagnose ALT-001"
            assert channel_msg.user_id == "user-flow-test"

            await asyncio.sleep(0.1)

            session_id = wecom_channel.handler.get_session_id(
                WecomIncomingMessage.from_wx_callback_xml(_xml_body(xml))
            )
            assert session_id is not None
