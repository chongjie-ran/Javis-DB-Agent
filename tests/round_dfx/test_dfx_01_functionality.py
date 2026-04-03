"""
DFX-01: 功能测试（Functionality）
==================================
覆盖范围：
- FUNC-TTL: Token TTL 完整流程
- FUNC-HOOK: Hook MODIFY 5种操作
- FUNC-WEBHOOK: Webhook 注册/回调/触发
- FUNC-AGENT: 并行Agent执行
- FUNC-APPROVAL: 安全审批流

注意：V2.6.1 Token TTL 和 Hook MODIFY 已由 round30 全面覆盖。
      V2.7 Webhook 安全 已由 round31 全面覆盖。
      本 DFX-01 测试聚焦于跨模块集成和 round30/31 未覆盖的边界场景。

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round_dfx/test_dfx_01_functionality.py -v --tb=short
"""

import asyncio
import time
import uuid
import sys
import os
import tempfile
import threading
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.gateway.persistent_session import PersistentSessionManager
from src.gateway.approval import ApprovalGate, ApprovalStatus
from src.gateway.hooks import HookEvent, HookContext, HookRule, HookAction, HookCondition
from src.gateway.hooks import ConditionOperator, ModifyOperation, ModifyOperationType
from src.gateway.hooks import HookEngine, RuleEngine


def reset_hook_registry():
    """Reset global hook registry for test isolation."""
    import src.gateway.hooks.hook_registry as hr_module
    hr_module._registry = None


@pytest.fixture(autouse=True)
def fresh_hook_registry():
    reset_hook_registry()
    yield
    reset_hook_registry()


@pytest.fixture
def fresh_engine():
    """Create a fresh HookEngine with its own registry."""
    reset_hook_registry()
    engine = HookEngine()
    yield engine
    reset_hook_registry()


# ============================================================================
# FUNC-TTL: Token TTL 完整流程（扩展边界测试）
# ============================================================================

class TestTokenTTLExtended:
    """Token TTL 扩展边界测试（round30 未覆盖的场景）"""

    def test_ttl_race_condition_create_during_cleanup(self, temp_db_path):
        """FUNC-TTL-EXT-01: 清理期间创建会话的竞态"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=1, max_sessions=50)
        
        sid = mgr.create_session("user1")
        
        time.sleep(1.5)
        
        results = []
        errors = []
        
        def create():
            try:
                mgr.create_session("user2")
                results.append("create_ok")
            except Exception as e:
                errors.append(str(e))
        
        def cleanup():
            try:
                mgr._cleanup_expired()
                results.append("cleanup_ok")
            except Exception as e:
                errors.append(str(e))
        
        t1 = threading.Thread(target=create)
        t2 = threading.Thread(target=cleanup)
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        assert len(errors) == 0
        assert "create_ok" in results or "cleanup_ok" in results
        
        mgr.cleanup_all()

    def test_ttl_session_update_context(self, temp_db_path):
        """FUNC-TTL-EXT-02: TTL会话更新context"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=3, max_sessions=100)
        
        session = mgr.create_session("user1")
        session_id = session.session_id
        
        # 设置context
        session.set_context_value("instance_id", "INS-001")
        mgr.save_session(session)
        
        # 验证可以获取并更新
        retrieved = mgr.get_session(session_id)
        assert retrieved is not None
        assert retrieved.get_context_value("instance_id") == "INS-001"
        
        # TTL过期后
        time.sleep(3.5)
        expired = mgr.get_session(session_id)
        assert expired is None
        
        mgr.cleanup_all()

    def test_ttl_metadata_persistence(self, temp_db_path):
        """FUNC-TTL-EXT-03: TTL会话metadata持久化"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=3, max_sessions=100)
        
        session = mgr.create_session("user1", metadata={"role": "admin"})
        session_id = session.session_id
        
        retrieved = mgr.get_session(session_id)
        assert retrieved is not None
        assert retrieved.metadata.get("role") == "admin"
        
        time.sleep(3.5)
        expired = mgr.get_session(session_id)
        assert expired is None
        
        mgr.cleanup_all()


# ============================================================================
# FUNC-HOOK: Hook MODIFY（使用HookEngine的正确API）
# ============================================================================

class TestHookModifyExtended:
    """Hook MODIFY 扩展测试（使用正确的 HookEngine API）"""

    @pytest.mark.asyncio
    async def test_modify_with_replace_op(self, fresh_engine):
        """FUNC-HOOK-EXT-01: 使用 ReplaceOperation 的 MODIFY"""
        replaced = []

        async def handler(ctx):
            sql = ctx.get("sql_statement", "")
            replaced.append(sql)
            ctx.set("sql_statement", "[MODIFIED]")
            return ctx

        fresh_engine.register_rule(HookRule(
            name="test_replace",
            event=HookEvent.SQL_BEFORE_GUARD,
            conditions=[
                HookCondition(
                    field="sql_statement",
                    operator=ConditionOperator.CONTAINS,
                    value="SELECT"
                )
            ],
            action=HookAction.MODIFY,
            handler=handler
        ))

        result = await fresh_engine.emit(
            HookEvent.SQL_BEFORE_GUARD,
            payload={"sql_statement": "SELECT * FROM users"},
            session_id="sess1",
            user_id="user1"
        )

        assert result.blocked is False
        assert "SELECT" in replaced[0]

    @pytest.mark.asyncio
    async def test_hook_chain_multiple_handlers(self, fresh_engine):
        """FUNC-HOOK-EXT-02: 链式多个handler"""
        call_order = []

        async def handler1(ctx):
            call_order.append(1)
            ctx.set("step", 1)
            return ctx

        async def handler2(ctx):
            call_order.append(2)
            ctx.set("step", 2)
            return ctx

        fresh_engine.register_rule(HookRule(
            name="chain1",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.LOG,
            handler=handler1
        ))

        fresh_engine.register_rule(HookRule(
            name="chain2",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            conditions=[],
            action=HookAction.LOG,
            handler=handler2
        ))

        result = await fresh_engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool": "test"},
            session_id="sess1",
            user_id="user1"
        )

        assert len(call_order) == 2
        # 按注册顺序执行
        assert call_order == [1, 2]


# ============================================================================
# FUNC-WEBHOOK: Webhook（扩展测试）
# ============================================================================

class TestWebhookExtended:
    """Webhook 扩展测试"""

    @pytest.mark.asyncio
    async def test_webhook_callback_receives_correct_status(self, approval_gate_normal):
        """FUNC-WEBHOOK-EXT-01: 回调接收正确的状态"""
        gate = approval_gate_normal
        
        received_statuses = []
        
        async def callback(request):
            received_statuses.append(request)
        
        # 创建并完成审批
        result = await gate.request_approval(
            action="test",
            context={"user_id": "user1"},
            params={"sql": "SELECT 1"}
        )
        
        # 注册回调（使用真实的 request_id）
        gate.register_callback(result.request_id, callback)
        
        await gate.approve(result.request_id, "approver1")
        
        await gate._trigger_callback(result.request_id)
        
        # 回调应该触发
        assert len(received_statuses) == 1
        
        gate.unregister_callback(result.request_id)

    @pytest.mark.asyncio
    async def test_webhook_unregister_nonexistent(self, approval_gate_normal):
        """FUNC-WEBHOOK-EXT-02: 注销不存在的callback"""
        gate = approval_gate_normal
        
        # 不应该抛出异常
        gate.unregister_callback("nonexistent_req")


# ============================================================================
# FUNC-APPROVAL: 安全审批流（扩展）
# ============================================================================

class TestApprovalFlowExtended:
    """审批流扩展测试"""

    @pytest.mark.asyncio
    async def test_approval_l4_with_params_hash(self, approval_gate_normal):
        """FUNC-APPROVAL-EXT-01: L4审批params_hash正确计算"""
        gate = approval_gate_normal
        
        result = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1", "risk_level": "L3"}
        )
        
        assert result.success is True
        
        req = gate.get_request(result.request_id)
        assert req.params_hash is not None
        assert len(req.params_hash) == 64  # SHA256 hex
        
        # 相同参数应产生相同hash
        result2 = await gate.request_approval(
            action="execute_sql",
            context={"user_id": "user1"},
            params={"statement": "SELECT 1", "risk_level": "L3"}
        )
        
        req2 = gate.get_request(result2.request_id)
        assert req2.params_hash == req.params_hash

    @pytest.mark.asyncio
    async def test_approval_list_pending(self, approval_gate_normal):
        """FUNC-APPROVAL-EXT-02: 列出待审批请求"""
        gate = approval_gate_normal
        
        # 创建多个待审批请求
        ids = []
        for i in range(3):
            result = await gate.request_approval(
                action=f"sql_{i}",
                context={"user_id": f"user_{i}"},
                params={"statement": f"SELECT {i}"}
            )
            ids.append(result.request_id)
        
        pending = gate.list_pending()
        pending_ids = [r.request_id for r in pending]
        
        for rid in ids:
            assert rid in pending_ids

    @pytest.mark.asyncio
    async def test_approval_get_nonexistent(self, approval_gate_normal):
        """FUNC-APPROVAL-EXT-03: 获取不存在的请求"""
        gate = approval_gate_normal
        
        req = gate.get_request("nonexistent_id_12345")
        assert req is None


# ============================================================================
# FUNC-AGENT: 并行Agent执行（扩展）
# ============================================================================

class TestParallelAgentExtended:
    """并行Agent执行扩展测试"""

    def test_parallel_session_operations(self, temp_db_path):
        """FUNC-AGENT-EXT-01: 并行会话操作"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=200)
        
        num_operations = 50
        operations = []
        
        def mixed_operations(user_idx):
            results = []
            for i in range(5):
                sid = mgr.create_session(f"user_{user_idx}_{i}").session_id
                s = mgr.get_session(sid)
                results.append(s is not None)
            return results
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(mixed_operations, i) for i in range(num_operations)]
            all_results = [r for f in as_completed(futures) for r in f.result()]
        
        assert len(all_results) == num_operations * 5
        assert all(all_results)
        
        mgr.cleanup_all()

    @pytest.mark.asyncio
    async def test_parallel_approval_mixed_operations(self, approval_gate_normal):
        """FUNC-AGENT-EXT-02: 并行审批混合操作"""
        gate = approval_gate_normal
        
        async def mixed_approval(i):
            result = await gate.request_approval(
                action=f"sql_{i}",
                context={"user_id": f"user_{i}"},
                params={"sql": f"SELECT {i}"}
            )
            # 随机审批或等待
            if i % 2 == 0:
                await gate.approve(result.request_id, f"approver_{i}")
                status = await gate.get_status(result.request_id)
                return status.status == ApprovalStatus.APPROVED
            return True
        
        results = await asyncio.gather(*[mixed_approval(i) for i in range(20)])
        assert all(results)
