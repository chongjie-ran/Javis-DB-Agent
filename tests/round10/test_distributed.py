"""测试 P0-2: 多节点部署验证"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


class TestDistributedSessionManager:
    """测试分布式会话管理器"""

    def test_redis_key_generation(self):
        """测试Redis key生成"""
        from src.gateway.distributed import DistributedSessionManager
        
        mgr = DistributedSessionManager.__new__(DistributedSessionManager)
        mgr._redis_ok = False
        mgr._ttl = 86400
        
        assert mgr._redis_key("sess-123") == "javis-db:session:sess-123"
        assert mgr._redis_user_key("user-abc") == "javis-db:user_sessions:user-abc"

    def test_is_distributed_returns_redis_status(self):
        """测试is_distributed属性"""
        from src.gateway.distributed import DistributedSessionManager
        
        # 当Redis不可用时
        mgr = DistributedSessionManager.__new__(DistributedSessionManager)
        mgr._redis = None
        mgr._redis_ok = False
        mgr._ttl = 86400
        
        assert mgr.is_distributed is False

    def test_verify_consistency_single_node(self):
        """测试单节点一致性检查（Redis不可用）"""
        from src.gateway.distributed import DistributedSessionManager
        
        mgr = DistributedSessionManager.__new__(DistributedSessionManager)
        mgr._redis_ok = False
        mgr._ttl = 86400
        mgr._local = None
        mgr._local_db_path = "/tmp/test_sessions.db"
        
        result = mgr.verify_consistency()
        
        assert result["redis_available"] is False
        assert result["consistent"] is True  # 单节点认为一致

    def test_deserialize_session(self):
        """测试会话反序列化"""
        from src.gateway.distributed import DistributedSessionManager
        
        mgr = DistributedSessionManager.__new__(DistributedSessionManager)
        
        data = {
            "session_id": "test-sid-123",
            "user_id": "user-456",
            "created_at": 1700000000.0,
            "updated_at": 1700000001.0,
            "context": "{}",
            "metadata": "{}",
            "messages": [
                {
                    "role": "user",
                    "content": "hello",
                    "tool_calls": "",
                    "tool_call_id": "",
                    "timestamp": 1700000000.5,
                },
                {
                    "role": "assistant",
                    "content": "hi there",
                    "tool_calls": "[]",
                    "tool_call_id": "",
                    "timestamp": 1700000001.0,
                },
            ],
        }
        
        session = mgr._deserialize_session(data)
        
        assert session.session_id == "test-sid-123"
        assert session.user_id == "user-456"
        assert len(session.messages) == 2
        assert session.messages[0].role == "user"
        assert session.messages[0].content == "hello"
        assert session.messages[1].role == "assistant"

    def test_deserialize_session_with_tool_calls(self):
        """测试带工具调用的会话反序列化"""
        from src.gateway.distributed import DistributedSessionManager
        
        mgr = DistributedSessionManager.__new__(DistributedSessionManager)
        
        data = {
            "session_id": "test-sid",
            "user_id": "user",
            "created_at": 1700000000.0,
            "updated_at": 1700000000.0,
            "context": "{}",
            "metadata": "{}",
            "messages": [
                {
                    "role": "tool",
                    "content": "query result",
                    "tool_calls": '[{"name": "query_db", "id": "call-123"}]',
                    "tool_call_id": "call-123",
                    "timestamp": 1700000000.5,
                },
            ],
        }
        
        session = mgr._deserialize_session(data)
        assert len(session.messages) == 1
        assert session.messages[0].tool_calls[0]["name"] == "query_db"


class TestDistributedApprovalManager:
    """测试分布式审批管理器"""

    def test_redis_key_generation(self):
        """测试Redis key生成"""
        from src.gateway.distributed import DistributedApprovalManager
        
        mgr = DistributedApprovalManager.__new__(DistributedApprovalManager)
        mgr._redis_ok = False
        mgr._store_path = "data/approvals.jsonl"
        
        assert mgr._redis_key("apr-123") == "javis-db:approval:apr-123"
        assert mgr._redis_pending_key() == "javis-db:approvals:pending"

    def test_verify_consistency_single_node(self):
        """测试单节点审批一致性检查"""
        from src.gateway.distributed import DistributedApprovalManager
        
        mgr = DistributedApprovalManager.__new__(DistributedApprovalManager)
        mgr._redis_ok = False
        mgr._local = None
        mgr._store_path = "/tmp/test_approvals.jsonl"
        
        result = mgr.verify_consistency()
        
        assert result["redis_available"] is False
        assert result["consistent"] is True


class TestMultiNodeHealthCheck:
    """测试多节点健康检查"""

    def test_check_multi_node_health_structure(self):
        """测试健康检查返回结构"""
        from src.gateway.distributed import check_multi_node_health
        
        result = check_multi_node_health()
        
        assert "redis" in result
        assert "sessions" in result
        assert "approvals" in result
        assert "audit_chain_valid" in result
        assert "overall" in result
        assert "checked_at" in result

    def test_health_overall_status(self):
        """测试综合健康状态"""
        from src.gateway.distributed import check_multi_node_health
        
        result = check_multi_node_health()
        
        # 单节点模式下应该返回healthy或degraded
        assert result["overall"] in ("healthy", "degraded", "unknown")


class TestClusterAPIEndpoints:
    """测试集群API端点结构"""

    def test_cluster_health_response_structure(self):
        """测试集群健康检查响应结构"""
        # 验证响应数据结构
        expected_keys = {"redis", "sessions", "approvals", "audit_chain_valid", "overall", "checked_at"}
        
        from src.gateway.distributed import check_multi_node_health
        result = check_multi_node_health()
        
        assert set(result.keys()) == expected_keys

    def test_session_verify_response_structure(self):
        """测试会话验证响应结构"""
        from src.gateway.distributed import DistributedSessionManager
        
        mgr = DistributedSessionManager.__new__(DistributedSessionManager)
        mgr._redis_ok = False
        
        result = mgr.verify_consistency()
        
        expected_keys = {"redis_available", "session_count_local", "session_count_redis", 
                        "missing_in_redis", "missing_in_local", "consistent", "checked_at"}
        assert set(result.keys()) == expected_keys

    def test_approval_verify_response_structure(self):
        """测试审批验证响应结构"""
        from src.gateway.distributed import DistributedApprovalManager
        
        mgr = DistributedApprovalManager.__new__(DistributedApprovalManager)
        # Manually set _redis_ok and initialize _local to None (lazy will work)
        object.__setattr__(mgr, '_redis_ok', False)
        object.__setattr__(mgr, '_store_path', '/tmp/test_approvals.jsonl')
        object.__setattr__(mgr, '_local', None)
        object.__setattr__(mgr, '_redis', None)
        
        result = mgr.verify_consistency()
        
        expected_keys = {"redis_available", "local_pending", "redis_pending", "consistent", "checked_at"}
        assert set(result.keys()) == expected_keys
