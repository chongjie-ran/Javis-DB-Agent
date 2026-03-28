"""
第三轮测试：Session 持久化
测试会话重启后恢复能力
"""
import pytest
import os
import time
import tempfile
import shutil
from src.gateway.persistent_session import (
    PersistentSessionManager,
    Session,
    Message,
    SessionManager,
    get_session_manager,
    reset_session_manager,
)


class TestPersistentSession:
    """持久化会话测试"""
    
    @pytest.fixture
    def temp_db_path(self):
        """创建临时数据库路径"""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_sessions.db")
        yield db_path
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def session_manager(self, temp_db_path):
        """创建会话管理器"""
        manager = PersistentSessionManager(
            db_path=temp_db_path,
            ttl_seconds=3600,  # 1小时
        )
        yield manager
        # 清理
        manager.cleanup_all()
    
    def test_create_session(self, session_manager):
        """测试创建会话"""
        session = session_manager.create_session(
            user_id="test_user",
            metadata={"source": "test"},
        )
        
        assert session is not None
        assert session.session_id != ""
        assert session.user_id == "test_user"
        assert session.metadata.get("source") == "test"
    
    def test_get_session(self, session_manager):
        """测试获取会话"""
        # 创建会话
        created = session_manager.create_session("test_user")
        
        # 获取会话
        retrieved = session_manager.get_session(created.session_id)
        
        assert retrieved is not None
        assert retrieved.session_id == created.session_id
        assert retrieved.user_id == created.user_id
    
    def test_session_not_found(self, session_manager):
        """测试会话不存在"""
        result = session_manager.get_session("non_existent_id")
        assert result is None
    
    def test_save_session(self, session_manager):
        """测试保存会话"""
        session = session_manager.create_session("test_user")
        
        # 更新上下文
        session.set_context_value("instance_id", "INS-001")
        session.set_context_value("alert_id", "ALT-001")
        
        # 保存
        session_manager.save_session(session)
        
        # 重新获取
        retrieved = session_manager.get_session(session.session_id)
        
        assert retrieved is not None
        assert retrieved.get_context_value("instance_id") == "INS-001"
        assert retrieved.get_context_value("alert_id") == "ALT-001"
    
    def test_delete_session(self, session_manager):
        """测试删除会话"""
        session = session_manager.create_session("test_user")
        session_id = session.session_id
        
        # 删除
        result = session_manager.delete_session(session_id)
        assert result == True
        
        # 验证删除
        retrieved = session_manager.get_session(session_id)
        assert retrieved is None
    
    def test_list_user_sessions(self, session_manager):
        """测试列出用户会话"""
        # 创建多个会话
        session_manager.create_session("user1")
        session_manager.create_session("user1")
        session_manager.create_session("user2")
        
        # 列出 user1 的会话
        sessions = session_manager.list_user_sessions("user1")
        assert len(sessions) == 2
        
        # 列出 user2 的会话
        sessions = session_manager.list_user_sessions("user2")
        assert len(sessions) == 1
    
    def test_add_message(self, session_manager):
        """测试添加消息"""
        session = session_manager.create_session("test_user")
        
        # 添加用户消息
        msg1 = session_manager.add_message(
            session_id=session.session_id,
            role="user",
            content="查询INS-001的状态",
        )
        assert msg1 is not None
        assert msg1.role == "user"
        assert msg1.content == "查询INS-001的状态"
        
        # 添加助手消息
        msg2 = session_manager.add_message(
            session_id=session.session_id,
            role="assistant",
            content="INS-001状态正常",
        )
        assert msg2 is not None
        assert msg2.role == "assistant"
        
        # 验证消息已保存
        messages = session_manager.get_messages(session.session_id)
        assert len(messages) == 2
    
    def test_get_messages_with_limit(self, session_manager):
        """测试获取消息（带限制）"""
        session = session_manager.create_session("test_user")
        
        # 添加多条消息
        for i in range(10):
            session_manager.add_message(
                session_id=session.session_id,
                role="user",
                content=f"消息 {i}",
            )
        
        # 获取最后5条
        messages = session_manager.get_messages(session.session_id, limit=5)
        assert len(messages) == 5


class TestSessionPersistenceRecovery:
    """会话持久化恢复测试"""
    
    @pytest.fixture
    def temp_db_path(self):
        """创建临时数据库路径"""
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_recovery.db")
        yield db_path
        shutil.rmtree(temp_dir)
    
    def test_recovery_after_restart(self, temp_db_path):
        """测试重启后恢复"""
        # 第一次会话
        manager1 = PersistentSessionManager(db_path=temp_db_path)
        session1 = manager1.create_session("test_user")
        
        # 添加消息
        manager1.add_message(session1.session_id, "user", "Hello")
        session1.set_context_value("key", "value")
        manager1.save_session(session1)
        
        # 获取会话ID
        session_id = session1.session_id
        
        # 关闭第一个管理器（模拟重启）
        del manager1
        
        # 第二个会话（模拟重启后恢复）
        manager2 = PersistentSessionManager(db_path=temp_db_path)
        
        # 恢复会话
        session2 = manager2.get_session(session_id)
        
        assert session2 is not None
        assert session2.user_id == "test_user"
        assert session2.get_context_value("key") == "value"
        
        # 验证消息已恢复
        messages = manager2.get_messages(session_id)
        assert len(messages) == 1
        assert messages[0].content == "Hello"
    
    def test_messages_persistence(self, temp_db_path):
        """测试消息持久化"""
        # 创建会话并添加消息
        manager1 = PersistentSessionManager(db_path=temp_db_path)
        session1 = manager1.create_session("test_user")
        
        # 添加不同类型的消息
        manager1.add_message(session1.session_id, "user", "用户消息1")
        manager1.add_message(session1.session_id, "assistant", "助手消息1")
        manager1.add_message(
            session1.session_id, 
            "tool", 
            "工具结果",
            tool_calls=[{"name": "test_tool", "arguments": {}}],
        )
        
        session_id = session1.session_id
        del manager1
        
        # 恢复并验证
        manager2 = PersistentSessionManager(db_path=temp_db_path)
        messages = manager2.get_messages(session_id)
        
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[2].role == "tool"
        assert len(messages[2].tool_calls) == 1


class TestSessionTTL:
    """会话TTL测试"""
    
    @pytest.fixture
    def temp_db_path(self):
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_ttl.db")
        yield db_path
        shutil.rmtree(temp_dir)
    
    def test_session_expiry(self, temp_db_path):
        """测试会话过期"""
        # 创建TTL很短的会话管理器
        manager = PersistentSessionManager(
            db_path=temp_db_path,
            ttl_seconds=1,  # 1秒TTL
        )
        
        session = manager.create_session("test_user")
        session_id = session.session_id
        
        # 验证会话存在
        retrieved = manager.get_session(session_id)
        assert retrieved is not None
        
        # 等待过期
        time.sleep(1.5)
        
        # 验证会话已过期
        retrieved = manager.get_session(session_id)
        assert retrieved is None
    
    def test_ttl_cleanup(self, temp_db_path):
        """测试TTL清理"""
        manager = PersistentSessionManager(
            db_path=temp_db_path,
            ttl_seconds=1,
        )
        
        # 创建多个会话
        for i in range(5):
            manager.create_session("test_user")
        
        # 等待过期
        time.sleep(1.5)
        
        # 触发清理
        manager._cleanup_expired()
        
        # 验证统计
        stats = manager.get_stats()
        assert stats["total_sessions"] == 0


class TestSessionManagerCompatibility:
    """SessionManager兼容层测试"""
    
    @pytest.fixture
    def temp_db_path(self):
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_compat.db")
        yield db_path
        shutil.rmtree(temp_dir)
    
    def test_session_manager_alias(self, temp_db_path):
        """测试SessionManager别名"""
        # SessionManager应该是PersistentSessionManager的别名
        manager = SessionManager(db_path=temp_db_path)
        
        session = manager.create_session("test_user")
        assert session is not None
        
        retrieved = manager.get_session(session.session_id)
        assert retrieved is not None


class TestSessionStats:
    """会话统计测试"""
    
    @pytest.fixture
    def temp_db_path(self):
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_stats.db")
        yield db_path
        shutil.rmtree(temp_dir)
    
    def test_get_stats(self, temp_db_path):
        """测试获取统计信息"""
        manager = PersistentSessionManager(db_path=temp_db_path)
        
        # 创建会话和消息
        session = manager.create_session("user1")
        manager.add_message(session.session_id, "user", "Hello")
        manager.add_message(session.session_id, "assistant", "Hi")
        
        session2 = manager.create_session("user2")
        manager.add_message(session2.session_id, "user", "World")
        
        # 获取统计
        stats = manager.get_stats()
        
        assert stats["total_sessions"] == 2
        assert stats["total_messages"] == 3
        assert stats["total_users"] == 2
        assert stats["db_path"] == temp_db_path


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
