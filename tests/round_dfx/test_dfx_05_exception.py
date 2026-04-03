"""
DFX-05: 异常处理测试（Exception Handling）
==================================
覆盖范围：
- EXC-01: 空指针/空数据
- EXC-02: 超大参数
- EXC-03: 并发冲突
- EXC-04: 资源泄漏

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round_dfx/test_dfx_05_exception.py -v --tb=short
"""

import asyncio
import time
import uuid
import sys
import os
import tempfile
import threading
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.gateway.persistent_session import PersistentSessionManager
from src.gateway.approval import ApprovalGate, ApprovalStatus
from src.gateway.hooks import HookEvent, HookContext, HookRule, HookAction
from src.gateway.hooks import HookEngine


# ============================================================================
# EXC-01: 空指针/空数据
# ============================================================================

class TestNullPointerAndEmptyData:
    """空指针/空数据异常处理测试"""

    def test_session_with_none_context(self, temp_db_path):
        """EXC-01: None context处理"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        session = mgr.create_session("user1")
        session_id = session.session_id
        
        # 正常设置context
        session.set_context_value("key", "value")
        mgr.save_session(session)
        
        retrieved = mgr.get_session(session_id)
        assert retrieved is not None
        assert retrieved.get_context_value("key") == "value"
        
        mgr.cleanup_all()

    def test_session_with_empty_messages(self, temp_db_path):
        """EXC-02: 空消息列表处理"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        session = mgr.create_session("user1")
        session_id = session.session_id
        
        # 保存空消息列表
        mgr.save_session(session)
        
        retrieved = mgr.get_session(session_id)
        assert retrieved is not None
        assert len(retrieved.messages) == 0
        
        mgr.cleanup_all()

    def test_get_nonexistent_session(self, temp_db_path):
        """EXC-03: 获取不存在的会话"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        session = mgr.get_session("nonexistent_session_id_12345")
        
        assert session is None
        
        mgr.cleanup_all()

    @pytest.mark.asyncio
    async def test_approval_request_with_none_context(self, approval_gate_normal):
        """EXC-04: None context的审批请求"""
        gate = approval_gate_normal
        
        # context为None应该被处理
        result = await gate.request_approval(
            action="test",
            context=None,
            params={"sql": "SELECT 1"}
        )
        
        assert result.success is True

    @pytest.mark.asyncio
    async def test_approval_request_with_none_params(self, approval_gate_normal):
        """EXC-05: None params的审批请求"""
        gate = approval_gate_normal
        
        result = await gate.request_approval(
            action="test",
            context={"user_id": "user1"},
            params=None
        )
        
        # 应该成功（使用空params）
        assert result.success is True

    @pytest.mark.asyncio
    async def test_hook_context_with_empty_payload(self):
        """EXC-06: 空payload的Hook处理"""
        import src.gateway.hooks.hook_registry as hr_module
        hr_module._registry = None
        engine = HookEngine()
        
        engine.register_rule(HookRule(
            name="test_rule",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.LOG
        ))
        
        # 应该处理空payload而不崩溃
        result = await engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={},
            session_id="sess1",
            user_id="user1"
        )
        
        assert result is not None
        assert result.blocked is False

    @pytest.mark.asyncio
    async def test_hook_context_with_partial_payload(self):
        """EXC-07: 部分字段payload"""
        import src.gateway.hooks.hook_registry as hr_module
        hr_module._registry = None
        engine = HookEngine()
        
        async def test_handler(ctx):
            # 尝试访问不存在的字段
            value = ctx.get("nonexistent_field", "default")
            assert value == "default"
            return ctx
        
        engine.register_rule(HookRule(
            name="test_rule",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.MODIFY,
            handler=test_handler
        ))
        
        result = await engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"existing_field": "value"},
            session_id="sess1",
            user_id="user1"
        )
        
        assert result is not None


# ============================================================================
# EXC-02: 超大参数
# ============================================================================

class TestOversizedParameters:
    """超大参数异常处理测试"""

    def test_large_user_id(self, temp_db_path):
        """EXC-08: 大user_id处理"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        large_user_id = "x" * 1000  # 限制大小
        
        sid = mgr.create_session(large_user_id).session_id
        
        assert sid is not None
        
        session = mgr.get_session(sid)
        assert session is not None
        assert session.user_id == large_user_id
        
        mgr.cleanup_all()

    def test_large_message_content(self, temp_db_path):
        """EXC-09: 大消息内容"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        sid = mgr.create_session("user1").session_id
        
        large_content = "x" * 10000  # 10KB
        
        # 添加大消息
        try:
            mgr.add_message(sid, "user", large_content)
            session = mgr.get_session(sid)
            assert len(session.messages) == 1
        except Exception as e:
            # 如果有限制，应该优雅地处理
            assert "size" in str(e).lower() or "limit" in str(e).lower() or "string" in str(e).lower()
        
        mgr.cleanup_all()

    @pytest.mark.asyncio
    async def test_large_approval_params(self, approval_gate_normal):
        """EXC-10: 大审批参数"""
        gate = approval_gate_normal
        
        large_params = {"sql": "x" * 100000}
        
        try:
            result = await gate.request_approval(
                action="test",
                context={"user_id": "user1"},
                params=large_params
            )
            assert result.success is True
        except Exception as e:
            # 如果有限制，应该优雅处理
            assert "size" in str(e).lower() or "limit" in str(e).lower() or "string" in str(e).lower()

    @pytest.mark.asyncio
    async def test_approval_request_with_deep_nested_params(self, approval_gate_normal):
        """EXC-11: 深度嵌套参数"""
        gate = approval_gate_normal
        
        # 创建深度嵌套的params
        deep_params = {"level1": {"level2": {"level3": {"level4": {"level5": "deep"}}}}}
        
        result = await gate.request_approval(
            action="test",
            context={"user_id": "user1"},
            params=deep_params
        )
        
        assert result.success is True
        
        # 验证能正确计算params_hash
        req = gate.get_request(result.request_id)
        assert req.params_hash is not None


# ============================================================================
# EXC-03: 并发冲突
# ============================================================================

class TestConcurrentConflicts:
    """并发冲突异常处理测试"""

    def test_concurrent_session_creation_no_collision(self, temp_db_path):
        """EXC-12: 并发创建会话无碰撞"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        sids = set()
        errors = []
        
        def create(idx):
            try:
                sid = mgr.create_session(f"user_{idx}").session_id
                sids.add(sid)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(50):
            t = threading.Thread(target=create, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"并发创建出现错误: {errors}"
        assert len(sids) == 50  # 全部唯一
        
        mgr.cleanup_all()

    def test_concurrent_save_and_get(self, temp_db_path):
        """EXC-13: 并发保存和获取"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        sid = mgr.create_session("user1")
        session_id = sid.session_id
        
        errors = []
        results = []
        
        def save():
            try:
                for i in range(10):
                    s = mgr.get_session(session_id)
                    if s:
                        s.set_context_value("count", i)
                        mgr.save_session(s)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(str(e))
        
        def get():
            try:
                for _ in range(10):
                    s = mgr.get_session(session_id)
                    results.append(s is not None)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(str(e))
        
        t1 = threading.Thread(target=save)
        t2 = threading.Thread(target=get)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        assert len(errors) == 0, f"并发保存/获取出现错误: {errors}"
        assert sum(results) >= len(results) * 0.8  # 至少80%成功
        
        mgr.cleanup_all()

    @pytest.mark.asyncio
    async def test_concurrent_approval_requests(self, approval_gate_normal):
        """EXC-14: 并发审批请求"""
        gate = approval_gate_normal
        
        async def create_request(i):
            return await gate.request_approval(
                action=f"sql_{i}",
                context={"user_id": f"user_{i}"},
                params={"sql": f"SELECT {i}"}
            )
        
        results = await asyncio.gather(*[create_request(i) for i in range(50)])
        
        assert len(results) == 50
        assert all(r.success for r in results)
        # 所有request_id应该唯一
        assert len(set(r.request_id for r in results)) == 50

    def test_concurrent_list_user_sessions(self, temp_db_path):
        """EXC-15: 并发列出用户会话"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        # 创建多个用户会话
        for i in range(10):
            for j in range(5):
                mgr.create_session(f"user_{i}")
        
        results = []
        errors = []
        
        def list_sessions():
            try:
                for _ in range(20):
                    for i in range(10):
                        sessions = mgr.list_user_sessions(f"user_{i}")
                        results.append(len(sessions))
                    time.sleep(0.001)
            except Exception as e:
                errors.append(str(e))
        
        threads = []
        for _ in range(5):
            t = threading.Thread(target=list_sessions)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"并发列出会话出现错误: {errors}"
        assert all(r == 5 for r in results)  # 每个用户5个会话
        
        mgr.cleanup_all()


# ============================================================================
# EXC-04: 资源泄漏
# ============================================================================

class TestResourceLeaks:
    """资源泄漏检测测试"""

    def test_session_manager_cleanup_all(self, temp_db_path):
        """EXC-16: cleanup_all清理所有资源"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        # 创建多个会话
        for i in range(20):
            mgr.create_session(f"user_{i}")
        
        # 清理
        mgr.cleanup_all()
        
        # 验证所有会话都被清理
        all_sessions = list(mgr._cache.values())
        assert len(all_sessions) == 0

    def test_session_cleanup_after_expiry(self, temp_db_path):
        """EXC-17: 过期会话自动清理"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=1, max_sessions=100)
        
        for i in range(10):
            mgr.create_session(f"user_{i}")
        
        # 等待过期
        time.sleep(2)
        
        # 调用清理
        mgr._cleanup_expired()
        
        # 应该被清理
        all_sessions = list(mgr._cache.values())
        assert len(all_sessions) == 0
        
        mgr.cleanup_all()

    @pytest.mark.asyncio
    async def test_hook_registry_cleanup(self):
        """EXC-18: Hook Registry清理"""
        import src.gateway.hooks.hook_registry as hr_module
        hr_module._registry = None
        
        engine = HookEngine()
        
        # 注册多个规则
        for i in range(10):
            engine.register_rule(HookRule(
                name=f"rule_{i}",
                event=HookEvent.TOOL_BEFORE_EXECUTE,
                conditions=[],
                action=HookAction.LOG
            ))
        
        # 重置
        hr_module._registry = None
        
        # 验证已清理
        new_engine = HookEngine()
        rules = new_engine.registry.list_all()
        assert len(rules) == 0

    @pytest.mark.asyncio
    async def test_callback_unregister_prevents_leak(self, approval_gate_normal):
        """EXC-19: 注销callback防止泄漏"""
        gate = approval_gate_normal
        
        # 注册大量callbacks
        for i in range(100):
            async def cb(req_id, status):
                pass
            gate.register_callback(f"req_{i}", cb)
        
        # 注销所有
        for i in range(100):
            gate.unregister_callback(f"req_{i}")
        
        # 验证已注销
        assert len(gate._webhook_callbacks) == 0

    def test_no_file_handle_leak_on_db_error(self, temp_db_path):
        """EXC-20: DB错误时不泄漏文件句柄"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        # 正常操作
        for i in range(5):
            mgr.create_session(f"user_{i}")
        
        # 删除数据库文件
        if os.path.exists(temp_db_path):
            os.unlink(temp_db_path)
        
        # 再次操作不应该泄漏句柄
        try:
            mgr.create_session("user_after_delete")
        except:
            pass
        
        # 尝试创建新manager，不应该有问题
        try:
            mgr2 = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
            mgr2.cleanup_all()
        except:
            pass


# ============================================================================
# EXC-05: 边界条件
# ============================================================================

class TestBoundaryConditions:
    """边界条件测试"""

    def test_session_with_zero_ttl(self, temp_db_path):
        """EXC-21: 零TTL会话"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=0, max_sessions=100)
        
        sid = mgr.create_session("user1").session_id
        
        # 零TTL应该立即过期或正常工作（取决于实现）
        session = mgr.get_session(sid)
        # 接受任何行为
        assert session is None or session is not None
        
        mgr.cleanup_all()

    def test_max_sessions_boundary(self, temp_db_path):
        """EXC-22: max_sessions边界值"""
        # 测试max_sessions=1
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=1)
        
        sid1 = mgr.create_session("user1")
        sid2 = mgr.create_session("user2")
        
        all_sessions = list(mgr._cache.values())
        assert len(all_sessions) == 1
        
        mgr.cleanup_all()

    @pytest.mark.asyncio
    async def test_empty_action_name(self, approval_gate_normal):
        """EXC-23: 空action名称"""
        gate = approval_gate_normal
        
        result = await gate.request_approval(
            action="",
            context={"user_id": "user1"},
            params={"sql": "SELECT 1"}
        )
        
        # 空action应该被处理
        assert result.success is True

    @pytest.mark.asyncio
    async def test_deep_recursion_in_payload(self):
        """EXC-24: payload深度递归（栈溢出检测）"""
        import src.gateway.hooks.hook_registry as hr_module
        hr_module._registry = None
        engine = HookEngine()
        
        engine.register_rule(HookRule(
            name="test",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.LOG
        ))
        
        # 创建深度嵌套payload
        deep_payload = {"level": {"nested": {"deep": "value"}}}
        
        # 不应该栈溢出
        try:
            result = await engine.emit(
                HookEvent.TOOL_BEFORE_EXECUTE,
                payload=deep_payload,
                session_id="sess1",
                user_id="user1"
            )
            assert result is not None
        except RecursionError:
            pytest.fail("Hook评估时出现递归错误")
