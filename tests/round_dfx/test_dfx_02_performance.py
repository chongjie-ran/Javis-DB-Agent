"""
DFX-02: 性能测试（Performance）
==================================
覆盖范围：
- PERF-01: 并发会话压力测试
- PERF-02: TTL过期清理性能
- PERF-03: Hook执行开销
- PERF-04: Webhook回调延迟

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round_dfx/test_dfx_02_performance.py -v --tb=short
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
from src.gateway.approval import ApprovalGate
from src.gateway.hooks import HookEvent, HookContext, HookRule, HookAction
from src.gateway.hooks import HookEngine


# ============================================================================
# PERF-01: 并发会话压力测试
# ============================================================================

class TestConcurrentSessionStress:
    """并发会话压力测试"""

    def test_concurrent_session_creation_throughput(self, temp_db_path):
        """PERF-01: 并发会话创建吞吐量"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=500)
        
        num_sessions = 100
        start = time.time()
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(mgr.create_session, f"user_{i}")
                for i in range(num_sessions)
            ]
            results = [f.result() for f in as_completed(futures)]
        
        elapsed = time.time() - start
        throughput = num_sessions / elapsed
        
        print(f"\nPERF-01: 创建 {num_sessions} 会话耗时 {elapsed:.3f}s, 吞吐量 {throughput:.1f} ops/s")
        
        assert len(results) == num_sessions
        assert all(r is not None for r in results)
        
        # 吞吐量至少 50 ops/s
        assert throughput > 50, f"吞吐量 {throughput:.1f} 低于预期 50 ops/s"
        
        mgr.cleanup_all()

    def test_concurrent_session_access_latency(self, temp_db_path):
        """PERF-02: 并发会话访问延迟"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=100)
        
        # 创建50个会话
        sessions = [mgr.create_session(f"user_{i}") for i in range(50)]
        sids = [s.session_id for s in sessions]
        
        latencies = []
        
        def access_session(sid):
            start = time.time()
            mgr.get_session(sid)
            return time.time() - start
        
        start = time.time()
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(access_session, sid) for sid in sids for _ in range(10)]
            latencies = [f.result() for f in as_completed(futures)]
        
        total_time = time.time() - start
        avg_latency = sum(latencies) / len(latencies) * 1000  # ms
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)] * 1000
        
        print(f"\nPERF-02: {len(latencies)} 次访问，平均延迟 {avg_latency:.2f}ms, P99 {p99_latency:.2f}ms")
        
        # 平均延迟应该小于 10ms
        assert avg_latency < 10, f"平均延迟 {avg_latency:.2f}ms 超过 10ms"
        
        mgr.cleanup_all()

    def test_high_concurrency_session_count_limit(self, temp_db_path):
        """PERF-03: 高并发会话数上限"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=300, max_sessions=200)
        
        num_sessions = 250  # 超过上限
        
        with ThreadPoolExecutor(max_workers=25) as executor:
            futures = [
                executor.submit(mgr.create_session, f"user_{i}")
                for i in range(num_sessions)
            ]
            results = [f.result() for f in as_completed(futures)]
        
        # 应该限制在 max_sessions
        all_sessions = list(mgr._cache.values())
        assert len(all_sessions) <= 200
        
        mgr.cleanup_all()


# ============================================================================
# PERF-02: TTL过期清理性能
# ============================================================================

class TestTTLCleanupPerformance:
    """TTL过期清理性能测试"""

    def test_cleanup_many_expired_sessions(self, temp_db_path):
        """PERF-04: 大量过期会话清理性能"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=1, max_sessions=500)
        
        # 创建100个会话
        for i in range(100):
            mgr.create_session(f"user_{i}")
        
        # 等待全部过期
        time.sleep(2)
        
        # 清理性能测试
        before = len(mgr._cache)
        start = time.time()
        mgr._cleanup_expired()
        elapsed = time.time() - start
        cleaned = before - len(mgr._cache)
        
        print(f"\nPERF-04: 清理 {cleaned} 个过期会话耗时 {elapsed*1000:.2f}ms")
        
        assert cleaned == 100
        assert elapsed < 1.0  # 应该在1秒内完成
        
        mgr.cleanup_all()

    def test_cleanup_while_accessing(self, temp_db_path):
        """PERF-05: 清理与访问并发"""
        mgr = PersistentSessionManager(temp_db_path, ttl_seconds=1, max_sessions=100)
        
        # 创建50个会话
        sessions = [mgr.create_session(f"user_{i}") for i in range(50)]
        sids = [s.session_id for s in sessions]
        
        time.sleep(1.5)  # 全部过期
        
        errors = []
        
        def access():
            try:
                for sid in sids[:10]:
                    mgr.get_session(sid)
            except Exception as e:
                errors.append(e)
        
        def cleanup():
            try:
                mgr._cleanup_expired()
            except Exception as e:
                errors.append(e)
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            fut_access = [executor.submit(access) for _ in range(10)]
            fut_cleanup = [executor.submit(cleanup) for _ in range(5)]
            
            for f in fut_access + fut_cleanup:
                f.result()
        
        assert len(errors) == 0, f"并发清理+访问出现错误: {errors}"
        
        mgr.cleanup_all()


# ============================================================================
# PERF-03: Hook执行开销
# ============================================================================

class TestHookExecutionOverhead:
    """Hook执行开销测试"""

    @pytest.fixture
    def engine_with_rules(self):
        """预置规则的HookEngine"""
        import src.gateway.hooks.hook_registry as hr_module
        hr_module._registry = None
        engine = HookEngine()
        
        # 注册10条规则
        for i in range(10):
            async def handler(ctx):
                ctx.set(f"field_{i}", f"value_{i}")
                return ctx
            
            engine.register_rule(HookRule(
                name=f"rule_{i}",
                event=HookEvent.TOOL_BEFORE_EXECUTE,
                conditions=[],
                action=HookAction.LOG,
                handler=handler
            ))
        
        yield engine
        
        import src.gateway.hooks.hook_registry as hr_module
        hr_module._registry = None

    @pytest.mark.asyncio
    async def test_hook_execution_latency(self, engine_with_rules):
        """PERF-06: Hook执行延迟"""
        engine = engine_with_rules
        
        # 预热
        await engine.emit(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={"tool": "test"},
            session_id="warmup",
            user_id="user1"
        )
        
        # 测量
        latencies = []
        for _ in range(100):
            start = time.time()
            await engine.emit(
                HookEvent.TOOL_BEFORE_EXECUTE,
                payload={"tool": "test"},
                session_id="sess1",
                user_id="user1"
            )
            latencies.append(time.time() - start)
        
        avg_latency = sum(latencies) / len(latencies) * 1000
        p99_latency = sorted(latencies)[99] * 1000
        
        print(f"\nPERF-06: Hook执行平均延迟 {avg_latency:.2f}ms, P99 {p99_latency:.2f}ms")
        
        # 单次Hook执行应该小于5ms
        assert avg_latency < 5, f"Hook执行平均延迟 {avg_latency:.2f}ms 超过 5ms"

    @pytest.mark.asyncio
    async def test_hook_parallel_execution(self, engine_with_rules):
        """PERF-07: Hook并行执行"""
        engine = engine_with_rules
        
        async def run_hook(i):
            return await engine.emit(
                HookEvent.TOOL_BEFORE_EXECUTE,
                payload={"tool": "test", "index": i},
                session_id=f"sess_{i}",
                user_id=f"user_{i}"
            )
        
        start = time.time()
        results = await asyncio.gather(*[run_hook(i) for i in range(100)])
        elapsed = time.time() - start
        
        print(f"\nPERF-07: 100次并行Hook执行耗时 {elapsed*1000:.2f}ms")
        
        assert len(results) == 100
        assert elapsed < 1.0  # 应该在1秒内完成


# ============================================================================
# PERF-04: Webhook回调延迟
# ============================================================================

class TestWebhookCallbackPerformance:
    """Webhook回调延迟测试"""

    @pytest.mark.asyncio
    async def test_webhook_callback_latency(self, approval_gate_normal):
        """PERF-08: Webhook回调延迟"""
        gate = approval_gate_normal
        
        callback_times = []
        
        async def timed_callback(request):
            callback_times.append(time.time())
        
        # 先创建真实审批请求
        result = await gate.request_approval(
            action="test",
            context={"user_id": "perf_user"},
            params={"sql": "SELECT 1"}
        )
        real_id = result.request_id
        
        gate.register_callback(real_id, timed_callback)
        
        # 测量回调延迟
        trigger_start = time.time()
        await gate._trigger_callback(real_id)
        trigger_end = time.time()
        
        callback_delay = (callback_times[0] - trigger_start) * 1000 if callback_times else 0
        
        print(f"\nPERF-08: Webhook回调延迟 {callback_delay:.2f}ms")
        
        assert len(callback_times) == 1
        assert callback_delay < 10  # 回调延迟应该小于10ms
        
        gate.unregister_callback(real_id)

    @pytest.mark.asyncio
    async def test_webhook_many_callbacks(self, approval_gate_normal):
        """PERF-09: 批量Webhook回调"""
        gate = approval_gate_normal
        
        num_callbacks = 50
        # 创建真实审批请求并注册回调
        for i in range(num_callbacks):
            async def cb(request):
                pass
            result = await gate.request_approval(
                action=f"perf_test_{i}",
                context={"user_id": f"user_{i}"},
                params={"sql": f"SELECT {i}"}
            )
            gate._webhook_callbacks[result.request_id] = cb
        
        start = time.time()
        
        for req_id in list(gate._webhook_callbacks.keys()):
            await gate._trigger_callback(req_id)
        
        elapsed = time.time() - start
        throughput = num_callbacks / elapsed
        
        print(f"\nPERF-09: {num_callbacks} 个Webhook回调吞吐量 {throughput:.1f} callbacks/s")
        
        # 吞吐量应该大于 1000 callbacks/s
        assert throughput > 1000


# ============================================================================
# PERF-05: 审批Gate性能
# ============================================================================

class TestApprovalGatePerformance:
    """审批Gate性能测试"""

    @pytest.mark.asyncio
    async def test_approval_request_throughput(self, approval_gate_normal):
        """PERF-10: 审批请求吞吐量"""
        gate = approval_gate_normal
        
        num_requests = 100
        
        async def request_approval(i):
            result = await gate.request_approval(
                action=f"sql_{i}",
                context={"user_id": f"user_{i}"},
                params={"statement": f"SELECT {i}"}
            )
            return result
        
        start = time.time()
        results = await asyncio.gather(*[request_approval(i) for i in range(num_requests)])
        elapsed = time.time() - start
        
        throughput = num_requests / elapsed
        
        print(f"\nPERF-10: {num_requests} 个审批请求吞吐量 {throughput:.1f} req/s")
        
        assert all(r.success for r in results)
        assert throughput > 50  # 至少 50 req/s
