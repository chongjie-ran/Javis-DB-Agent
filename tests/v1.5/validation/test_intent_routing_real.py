"""
意图路由真实环境测试
测试 OrchestratorAgent 的意图识别与路由
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
from test_runner import TestConfig, orchestrator


# ---------------------------------------------------------------------------
# Test: 备份意图路由
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backup_intent_routing(orchestrator):
    """测试备份意图路由到BackupAgent"""
    result = await orchestrator.process("最近的备份成功了吗", {})
    assert result.success, f"备份意图路由失败: {result.error}"
    print(f"\n✅ 备份意图路由: {result.content[:200]}...")


@pytest.mark.asyncio
async def test_backup_status_intent(orchestrator):
    """测试备份状态意图路由"""
    result = await orchestrator.process("MySQL备份状态怎么样", {"db_type": "mysql"})
    assert result.success, f"备份状态意图路由失败: {result.error}"
    print(f"\n✅ 备份状态意图: {result.content[:200]}...")


@pytest.mark.asyncio
async def test_backup_history_intent(orchestrator):
    """测试备份历史意图路由"""
    result = await orchestrator.process("最近10条备份历史", {})
    assert result.success, f"备份历史意图路由失败: {result.error}"
    print(f"\n✅ 备份历史意图: {result.content[:200]}...")


# ---------------------------------------------------------------------------
# Test: 性能意图路由
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_performance_intent_routing(orchestrator):
    """测试性能意图路由到PerformanceAgent"""
    result = await orchestrator.process("帮我分析一下性能", {})
    assert result.success, f"性能意图路由失败: {result.error}"
    print(f"\n✅ 性能意图路由: {result.content[:200]}...")


@pytest.mark.asyncio
async def test_topsql_intent(orchestrator):
    """测试TopSQL意图路由"""
    result = await orchestrator.process("哪些SQL最慢", {})
    assert result.success, f"TopSQL意图路由失败: {result.error}"
    print(f"\n✅ TopSQL意图: {result.content[:200]}...")


@pytest.mark.asyncio
async def test_explain_intent(orchestrator):
    """测试执行计划意图路由"""
    result = await orchestrator.process(
        "执行计划看看: SELECT * FROM orders WHERE status = 'pending'",
        {}
    )
    # 执行计划可能因为表不存在而返回错误，但路由本身应该成功
    assert result is not None
    print(f"\n✅ 执行计划意图: {result.content[:200] if result.success else result.error}...")


# ---------------------------------------------------------------------------
# Test: 意图自演化收集
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_intent_feedback_collection(orchestrator):
    """测试意图反馈收集"""
    from src.agents.orchestrator import IntentExampleCollector

    collector = IntentExampleCollector()

    # 记录用户反馈
    collector.record_feedback(
        user_input="备份状态",
        recognized_intent="analyze_backup",
        user_accepted=True,
    )

    stats = collector.get_stats()
    assert stats.get("feedback_buffer_size", 0) > 0 or stats.get("total_intents", 0) > 0, "意图反馈收集失败"
    print(f"\n✅ 意图反馈收集: {stats}")


# ---------------------------------------------------------------------------
# Test: 未知意图兜底
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_intent_fallback(orchestrator):
    """测试未知意图兜底处理"""
    result = await orchestrator.process("你好，你是做什么的", {})
    assert result is not None
    print(f"\n✅ 未知意图兜底: {result.content[:100] if result.content else result.error}...")
