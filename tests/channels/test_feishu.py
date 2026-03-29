"""飞书消息通道测试

覆盖：
- 消息解析
- 会话映射
- 消息去重
- 权限检查
- 消息发送
"""
import pytest
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

from src.channels.feishu.session_mapper import (
    FeishuSessionMapper,
    FeishuSessionRef,
    get_feishu_session_mapper,
    reset_feishu_session_mapper,
)
from src.channels.feishu.config import FeishuChannelConfig
from src.channels.feishu.sender import FeishuSender
from src.channels.feishu.message_handler import (
    FeishuMessageHandler,
    FeishuMessage,
    MessageType,
    ChatType,
    create_message_handler,
)


class TestFeishuSessionMapper:
    """会话映射器测试"""

    def setup_method(self):
        """每个测试方法前重置"""
        reset_feishu_session_mapper()
        self.mapper = FeishuSessionMapper(ttl_seconds=3600, max_per_user=5)

    def teardown_method(self):
        reset_feishu_session_mapper()

    def test_create_session(self):
        """创建新会话"""
        session_id = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_789",
        )
        assert session_id is not None
        assert len(session_id) == 36  # UUID格式

    def test_get_existing_session(self):
        """获取已存在的会话"""
        session_id = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_789",
        )
        # 再次获取同一会话
        session_id2 = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_aaa",
        )
        assert session_id == session_id2

    def test_different_user_different_session(self):
        """不同用户不同会话"""
        session_id1 = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_789",
        )
        session_id2 = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_abc",
            feishu_message_id="msg_xyz",
        )
        assert session_id1 != session_id2

    def test_different_chat_different_session(self):
        """不同群组不同会话"""
        session_id1 = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_789",
        )
        session_id2 = self.mapper.get_or_create_session(
            feishu_chat_id="chat_abc",
            feishu_user_id="user_456",
            feishu_message_id="msg_xyz",
        )
        assert session_id1 != session_id2

    def test_thread_isolation(self):
        """线程隔离"""
        session_id1 = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_789",
            is_thread=False,
        )
        session_id2 = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_aaa",
            is_thread=True,
            thread_id="thread_123",
        )
        assert session_id1 != session_id2

    def test_user_session_limit(self):
        """用户会话数限制"""
        # 创建5个会话（达到限制）
        sessions = []
        for i in range(5):
            sid = self.mapper.get_or_create_session(
                feishu_chat_id=f"chat_{i}",
                feishu_user_id="user_limited",
                feishu_message_id=f"msg_{i}",
            )
            sessions.append(sid)

        # 再创建一个，会触发清理
        new_sid = self.mapper.get_or_create_session(
            feishu_chat_id="chat_new",
            feishu_user_id="user_limited",
            feishu_message_id="msg_new",
        )

        # 新会话应该不同
        assert new_sid not in sessions

    def test_clear_session(self):
        """清除会话"""
        session_id = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_789",
        )
        assert self.mapper.clear_session(session_id) is True
        assert self.mapper.get_session("chat_123", "user_456") is None

    def test_get_ref(self):
        """获取会话引用"""
        session_id = self.mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_789",
            metadata={"key": "value"},
        )
        ref = self.mapper.get_ref(session_id)
        assert ref is not None
        assert ref.feishu_chat_id == "chat_123"
        assert ref.feishu_user_id == "user_456"
        assert ref.metadata.get("key") == "value"

    def test_cleanup_expired(self):
        """清理过期会话"""
        mapper = FeishuSessionMapper(ttl_seconds=1, max_per_user=10)
        session_id = mapper.get_or_create_session(
            feishu_chat_id="chat_123",
            feishu_user_id="user_456",
            feishu_message_id="msg_789",
        )
        # 等待过期
        time.sleep(1.5)
        cleaned = mapper.cleanup_expired()
        assert cleaned >= 1
        assert mapper.get_session("chat_123", "user_456") is None

    def test_get_stats(self):
        """统计信息"""
        self.mapper.get_or_create_session(
            feishu_chat_id="chat_1",
            feishu_user_id="user_1",
            feishu_message_id="msg_1",
        )
        self.mapper.get_or_create_session(
            feishu_chat_id="chat_2",
            feishu_user_id="user_2",
            feishu_message_id="msg_2",
        )
        stats = self.mapper.get_stats()
        assert stats["total_sessions"] >= 2
        assert stats["active_users"] >= 2
        assert stats["active_chats"] >= 2


class TestFeishuChannelConfig:
    """配置测试"""

    def test_default_config(self):
        """默认配置"""
        config = FeishuChannelConfig()
        assert config.connection_mode == "websocket"
        assert config.session_ttl_seconds == 86400
        assert config.max_sessions_per_user == 10
        assert config.dedup_ttl_ms == 5000
        assert config.allow_from_all is True

    def test_is_configured(self):
        """配置完整性检查"""
        config = FeishuChannelConfig(app_id="", app_secret="")
        assert config.is_configured is False

        config = FeishuChannelConfig(app_id="app_123", app_secret="secret_456")
        assert config.is_configured is True

    def test_connection_mode(self):
        """连接模式"""
        config = FeishuChannelConfig(connection_mode="websocket")
        assert config.is_websocket_mode is True
        assert config.is_webhook_mode is False

        config = FeishuChannelConfig(connection_mode="webhook", webhook_port=8080)
        assert config.is_webhook_mode is True
        assert config.is_websocket_mode is False


class TestFeishuSender:
    """消息发送器测试"""

    def test_build_text_card(self):
        """构建文本卡片"""
        card = FeishuSender.build_text_card("Hello World")
        assert card["schema"] == "2.0"
        assert "body" in card
        assert "elements" in card["body"]

    def test_build_markdown_card(self):
        """构建Markdown卡片"""
        card = FeishuSender.build_markdown_card("**Bold** and *italic*")
        assert card["schema"] == "2.0"
        assert "body" in card

    def test_build_streaming_card(self):
        """构建流式卡片"""
        card = FeishuSender.build_streaming_card("Loading...")
        assert card["schema"] == "2.0"
        assert card["config"]["update_multi"] is True

    def test_build_alert_card(self):
        """构建告警卡片"""
        card = FeishuSender.build_alert_card(
            title="CPU告警",
            level="critical",
            content="CPU使用率超过90%",
        )
        assert card["schema"] == "2.0"
        assert "body" in card
        elements = card["body"]["elements"]
        # 第一个元素应该是标题
        assert "text" in elements[0]

    def test_build_agent_response_card(self):
        """构建Agent响应卡片"""
        card = FeishuSender.build_agent_response_card(
            "这是Agent的回复",
            metadata={"agent": "orchestrator", "intent": "diagnose"},
        )
        assert card["schema"] == "2.0"


class TestFeishuMessage:
    """消息结构测试"""

    def test_message_creation(self):
        """创建消息"""
        msg = FeishuMessage(
            message_id="msg_123",
            chat_id="chat_456",
            chat_type=ChatType.P2P,
            sender_id="user_789",
            sender_type="user",
            message_type=MessageType.TEXT,
            content="Hello",
            create_time="1234567890",
        )
        assert msg.message_id == "msg_123"
        assert msg.feishu_user_id == "user_789"
        assert msg.is_p2p is True
        assert msg.is_group is False
        assert msg.is_bot_message is False

    def test_group_message(self):
        """群组消息"""
        msg = FeishuMessage(
            message_id="msg_123",
            chat_id="chat_456",
            chat_type=ChatType.GROUP,
            sender_id="user_789",
            sender_type="user",
            message_type=MessageType.TEXT,
            content="Hello",
            create_time="1234567890",
        )
        assert msg.is_group is True
        assert msg.is_p2p is False


class TestFeishuMessageHandler:
    """消息处理器测试"""

    def setup_method(self):
        """每个测试前设置"""
        self.config = FeishuChannelConfig(
            app_id="test_app_id",
            app_secret="test_app_secret",
            allow_from_all=True,
        )
        self.mock_client = MagicMock()
        self.mock_client.get_tenant_access_token = AsyncMock(
            return_value="test_token"
        )
        self.mock_client.send_text = AsyncMock(
            return_value=MagicMock(message_id="sent_msg_123", chat_id="chat_123")
        )
        self.mock_client.send_post = AsyncMock(
            return_value=MagicMock(message_id="sent_msg_123", chat_id="chat_123")
        )
        self.mock_client.send_interactive = AsyncMock(
            return_value=MagicMock(message_id="sent_msg_123", chat_id="chat_123")
        )
        self.mapper = FeishuSessionMapper()
        self.handler = create_message_handler(
            client=self.mock_client,
            config=self.config,
            session_mapper=self.mapper,
        )

    def test_parse_text_message(self):
        """解析文本消息"""
        event_data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "message": {"message_id": "msg_123"},
                "chat_id": "chat_456",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "Hello World"}),
                "sender": {
                    "sender": {
                        "open_id": "user_789",
                        "sender_type": "user",
                    }
                },
                "create_time": "1234567890",
            },
        }

        msg = self.handler.parse_message(event_data)
        assert msg is not None
        assert msg.message_id == "msg_123"
        assert msg.chat_id == "chat_456"
        assert msg.content == "Hello World"
        assert msg.message_type == MessageType.TEXT
        assert msg.chat_type == ChatType.P2P

    def test_parse_group_message(self):
        """解析群组消息"""
        event_data = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "message": {"message_id": "msg_123"},
                "chat_id": "chat_456",
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": "Hello Group"}),
                "sender": {
                    "sender": {
                        "open_id": "user_789",
                        "sender_type": "user",
                    }
                },
                "create_time": "1234567890",
            },
        }

        msg = self.handler.parse_message(event_data)
        assert msg is not None
        assert msg.chat_type == ChatType.GROUP
        assert msg.is_group is True

    def test_parse_unsupported_event(self):
        """解析不支持的事件"""
        event_data = {
            "header": {"event_type": "im.message.message_read_v1"},
            "event": {},
        }
        msg = self.handler.parse_message(event_data)
        assert msg is None

    def test_is_duplicate(self):
        """消息去重"""
        msg_id = "msg_dedup_test"
        # 第一次不是重复
        assert self.handler.is_duplicate(msg_id) is False
        # 第二次是重复
        assert self.handler.is_duplicate(msg_id) is True

    def test_check_permission_all_allowed(self):
        """权限检查-允许所有"""
        msg = FeishuMessage(
            message_id="msg_123",
            chat_id="chat_456",
            chat_type=ChatType.P2P,
            sender_id="any_user",
            sender_type="user",
            message_type=MessageType.TEXT,
            content="Hello",
            create_time="1234567890",
        )
        assert self.handler.check_permission(msg) is True

    def test_check_permission_whitelist(self):
        """权限检查-白名单"""
        config = FeishuChannelConfig(
            app_id="test_app_id",
            app_secret="test_app_secret",
            allow_from_all=False,
            allow_from=["user_allowed"],
        )
        handler = create_message_handler(
            client=self.mock_client,
            config=config,
            session_mapper=self.mapper,
        )

        # 允许的用户
        msg_allowed = FeishuMessage(
            message_id="msg_1",
            chat_id="chat_456",
            chat_type=ChatType.P2P,
            sender_id="user_allowed",
            sender_type="user",
            message_type=MessageType.TEXT,
            content="Hello",
            create_time="1234567890",
        )
        assert handler.check_permission(msg_allowed) is True

        # 不允许的用户
        msg_denied = FeishuMessage(
            message_id="msg_2",
            chat_id="chat_456",
            chat_type=ChatType.P2P,
            sender_id="user_denied",
            sender_type="user",
            message_type=MessageType.TEXT,
            content="Hello",
            create_time="1234567890",
        )
        assert handler.check_permission(msg_denied) is False

    def test_get_stats(self):
        """统计信息"""
        self.handler.is_duplicate("msg_stats_1")
        self.handler.is_duplicate("msg_stats_2")
        stats = self.handler.get_stats()
        assert "dedup_cache_size" in stats
        assert "session_mapper" in stats


class TestFeishuSessionMapperIntegration:
    """会话映射器集成测试"""

    def setup_method(self):
        reset_feishu_session_mapper()

    def teardown_method(self):
        reset_feishu_session_mapper()

    def test_singleton(self):
        """单例模式"""
        mapper1 = get_feishu_session_mapper()
        mapper2 = get_feishu_session_mapper()
        assert mapper1 is mapper2

    def test_reset(self):
        """重置"""
        mapper1 = get_feishu_session_mapper()
        mapper1.get_or_create_session(
            feishu_chat_id="chat_1",
            feishu_user_id="user_1",
            feishu_message_id="msg_1",
        )
        reset_feishu_session_mapper()
        mapper2 = get_feishu_session_mapper()
        assert mapper1 is not mapper2
        # 新实例应该没有之前的会话
        assert mapper2.get_stats()["total_sessions"] == 0
