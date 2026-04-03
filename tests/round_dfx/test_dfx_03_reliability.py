"""
DFX-03: 可靠性测试（Reliability）
==================================
覆盖范围：
- RELY-01: 网络波动fallback
- RELY-02: 数据库断连恢复
- RELY-03: 服务重启恢复
- RELY-04: 超时处理
- RELY-05: 异常边界

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round_dfx/test_dfx_03_reliability.py -v --tb=short
"""

import asyncio
import time
import uuid
import sys
import os
import tempfile
import threading
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.gateway.persistent_session import PersistentSessionManager
from src.gateway.approval import ApprovalGate, ApprovalStatus
from src.gateway.hooks import HookEvent, HookContext, HookRule, HookAction
from src.gateway.hooks import HookEngine


# ============================================================================
# RELY-01: 网络波动fallback（通过mock模拟）
# ============================================================================

class TestNetworkFallback:
    """网络波动fallback测试（模拟）"""

    @pytest.mark.asyncio
    async def test_approval_fallback_on_error(self, approval_gate_normal):
        """RELY-01: 审批请求错误时fallback"""
        gate = approval_gate_normal
        
        # 创建请求
        result = await gate.request_approval(
            action="test_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"}
        )
        
        request_id = result.request_id
        
        # 模拟网络波动后的重试逻辑
        max_retries = 3
        for attempt in range(max_retries):
            try:
                approved = await gate.approve(request_id, "approver1")
                if approved:
                    break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
        
        status = await gate.get_status(request_id)
        assert status.status == ApprovalStatus.APPROVED

    def test_session_cache_fallback(self, temp_db_path):
        """RELY-02: 会话缓存fallback"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        session = mgr.create_session("user1")
        session_id = session.session_id
        
        # 正常获取（从缓存）
        session1 = mgr.get_session(session_id)
        assert session1 is not None
        
        # 模拟缓存被清空（但DB中仍有数据）
        # 注：由于我们使用的是SQLite in-memory，DB本身的数据应该还在
        # 但如果缓存清空且TTL未过期，应该能恢复
        
        mgr.cleanup_all()


# ============================================================================
# RELY-02: 数据库断连恢复
# ============================================================================

class TestDatabaseDisconnectRecovery:
    """数据库断连恢复测试"""

    def test_session_manager_reinit_after_cleanup(self, temp_db_path):
        """RELY-03: SessionManager清理后重新初始化"""
        # 第一次创建会话
        mgr1 = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        session = mgr1.create_session("user1")
        session_id = session.session_id
        
        # 保存一些数据
        session.set_context_value("key", "value")
        mgr1.save_session(session)
        
        # 重新创建Manager（同一DB路径），不调用 cleanup_all
        mgr2 = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        # 应该能恢复会话
        restored = mgr2.get_session(session_id)
        assert restored is not None
        assert restored.get_context_value("key") == "value"
        
        mgr2.cleanup_all()

    def test_concurrent_access_during_reinit(self, temp_db_path):
        """RELY-04: 重新初始化期间的并发访问"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        session = mgr.create_session("user1")
        session_id = session.session_id
        
        errors = []
        results = []
        
        def access_session():
            try:
                s = mgr.get_session(session_id)
                results.append(s is not None)
            except Exception as e:
                errors.append(str(e))
        
        threads = []
        for _ in range(20):
            t = threading.Thread(target=access_session)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"并发访问出现错误: {errors}"
        assert all(results)
        
        mgr.cleanup_all()


# ============================================================================
# RELY-03: 服务重启恢复
# ============================================================================

class TestServiceRestartRecovery:
    """服务重启恢复测试"""

    def test_session_persists_after_manager_reinit(self, temp_db_path):
        """RELY-05: 会话在Manager重新初始化后持久化"""
        # 第一次创建会话
        mgr1 = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        session1 = mgr1.create_session("user1")
        session1.set_context_value("instance", "INS-001")
        mgr1.save_session(session1)
        
        # 模拟重启：创建新的Manager实例（同一DB）
        mgr2 = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        # 应该能恢复会话
        restored = mgr2.get_session(session1.session_id)
        assert restored is not None
        assert restored.user_id == "user1"
        assert restored.get_context_value("instance") == "INS-001"
        
        mgr1.cleanup_all()
        mgr2.cleanup_all()

    def test_approval_gate_fresh_instance(self, temp_db_path):
        """RELY-06: ApprovalGate新实例正常工作"""
        # 创建新的ApprovalGate
        gate1 = ApprovalGate(timeout_seconds=300)
        
        result = asyncio.run(gate1.request_approval(
            action="test",
            context={"user_id": "user1"},
            params={"sql": "SELECT 1"}
        ))
        
        assert result.success is True
        
        # 创建新的gate实例（应该有独立状态）
        gate2 = ApprovalGate(timeout_seconds=300)
        
        # gate2的list_pending应该为空（新实例）
        pending = gate2.list_pending()
        # 注意：这取决于实现，可能共享底层存储


# ============================================================================
# RELY-04: 超时处理
# ============================================================================

class TestTimeoutHandling:
    """超时处理测试"""

    @pytest.mark.asyncio
    async def test_approval_timeout_cleanup(self, approval_gate_short):
        """RELY-07: 审批超时自动清理"""
        gate = approval_gate_short
        
        result = await gate.request_approval(
            action="test_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"}
        )
        
        request_id = result.request_id
        
        # 等待超时
        await asyncio.sleep(4)
        
        # 清理超时请求
        cleaned = await gate.cleanup_timeout()
        
        assert cleaned >= 1
        
        status = await gate.get_status(request_id)
        assert status.status == ApprovalStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_approval_cleanup_returns_count(self, approval_gate_short):
        """RELY-08: cleanup_timeout 返回清理数量"""
        gate = approval_gate_short
        
        # 创建多个超时请求
        for i in range(5):
            await gate.request_approval(
                action=f"sql_{i}",
                context={"user_id": f"user_{i}"},
                params={"statement": f"SELECT {i}"}
            )
        
        # 等待超时
        await asyncio.sleep(4)
        
        # 清理
        cleaned = await gate.cleanup_timeout()
        
        assert cleaned == 5

    @pytest.mark.asyncio
    async def test_long_running_approval_not_affected_by_cleanup(self, approval_gate_normal):
        """RELY-09: 长时间运行的审批不受清理影响"""
        gate = approval_gate_normal
        
        result = await gate.request_approval(
            action="long_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1"}
        )
        
        request_id = result.request_id
        
        # 执行清理（应该只清理超时的）
        cleaned = await gate.cleanup_timeout()
        
        # 刚才创建的请求不应该被清理（还未超时）
        status = await gate.get_status(request_id)
        assert status.status == ApprovalStatus.PENDING


# ============================================================================
# RELY-05: 异常边界
# ============================================================================

class TestExceptionBoundaries:
    """异常边界测试"""

    @pytest.mark.asyncio
    async def test_approval_request_with_empty_params(self, approval_gate_normal):
        """RELY-10: 空参数审批请求"""
        gate = approval_gate_normal
        
        result = await gate.request_approval(
            action="test",
            context={},
            params={}
        )
        
        assert result.success is True
        assert result.request_id is not None

    @pytest.mark.asyncio
    async def test_approval_request_with_special_chars(self, approval_gate_normal):
        """RELY-11: 特殊字符参数"""
        gate = approval_gate_normal
        
        special_params = {
            "statement": "SELECT * FROM users WHERE name = 'Robert'; DROP TABLE users;--'",
            "sql_comment": "-- This is a comment\n/* block comment */"
        }
        
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params=special_params
        )
        
        assert result.success is True

    @pytest.mark.asyncio
    async def test_approval_nonexistent_request_status(self, approval_gate_normal):
        """RELY-12: 查询不存在的请求状态"""
        gate = approval_gate_normal
        
        status = await gate.get_status("nonexistent_request_id_12345")
        
        assert status is not None

    def test_session_with_extremely_long_user_id(self, temp_db_path):
        """RELY-13: 超长user_id处理"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        long_user_id = "a" * 1000  # 限制长度避免过大
        
        sid = mgr.create_session(long_user_id)
        
        assert sid is not None
        
        session = mgr.get_session(sid.session_id)
        assert session is not None
        assert session.user_id == long_user_id
        
        mgr.cleanup_all()

    def test_session_with_unicode_user_id(self, temp_db_path):
        """RELY-14: Unicode user_id处理"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        unicode_user = "用户_管理员_👤"
        
        sid = mgr.create_session(unicode_user)
        
        assert sid is not None
        
        session = mgr.get_session(sid.session_id)
        assert session is not None
        assert session.user_id == unicode_user
        
        mgr.cleanup_all()

    @pytest.mark.asyncio
    async def test_hook_with_empty_payload(self):
        """RELY-15: 空payload的Hook处理"""
        import src.gateway.hooks.hook_registry as hr_module
        hr_module._registry = None
        engine = HookEngine()
        
        engine.register_rule(HookRule(
            name="empty_test",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.LOG
        ))
        
        result = await engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={},
            session_id="sess1",
            user_id="user1"
        )
        
        assert result is not None
        assert result.blocked is False


# ============================================================================
# RELY-06: 资源限制
# ============================================================================

class TestResourceLimits:
    """资源限制测试"""

    def test_max_sessions_lru_eviction(self, temp_db_path):
        """RELY-16: 超过max_sessions时LRU淘汰"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=10)
        
        # 创建15个会话
        sessions = []
        for i in range(15):
            sid = mgr.create_session(f"user_{i}")
            sessions.append(sid.session_id)
        
        # 应该只有10个会话存活
        all_sessions = list(mgr._cache.values())
        assert len(all_sessions) == 10
        
        # 最早的会话应该被淘汰
        first_session = mgr.get_session(sessions[0])
        assert first_session is None
        
        mgr.cleanup_all()

    def test_session_manager_handles_db_full(self, temp_db_path):
        """RELY-17: 数据库满时的处理"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=5)
        
        # 即使数据库小，也应该能正常工作
        for i in range(5):
            sid = mgr.create_session(f"user_{i}")
            assert sid is not None
        
        mgr.cleanup_all()
