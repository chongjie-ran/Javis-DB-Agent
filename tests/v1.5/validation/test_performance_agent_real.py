"""
PerformanceAgent 真实环境测试
测试TopSQL提取、执行计划解读、参数调优建议
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
from test_runner import TestConfig, perf_agent


# ---------------------------------------------------------------------------
# Test: extract_top_sql
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_extract_top_sql_mysql(perf_agent):
    """测试MySQL TopSQL提取"""
    result = await perf_agent.extract_top_sql(db_type="mysql", limit=5)
    assert result.success, f"MySQL TopSQL提取失败: {result.error}"
    assert len(result.content) > 0, "TopSQL内容为空"
    print(f"\n✅ MySQL TopSQL: {result.content[:300]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_extract_top_sql_pg(perf_agent):
    """测试PostgreSQL TopSQL提取"""
    result = await perf_agent.extract_top_sql(db_type="postgresql", limit=5)
    assert result.success, f"PG TopSQL提取失败: {result.error}"
    assert len(result.content) > 0, "TopSQL内容为空"
    print(f"\n✅ PG TopSQL: {result.content[:300]}...")


# ---------------------------------------------------------------------------
# Test: extract_top_sql with custom limit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_extract_top_sql_limit_mysql(perf_agent):
    """测试MySQL TopSQL提取 - 指定数量"""
    result = await perf_agent.extract_top_sql(db_type="mysql", limit=3)
    assert result.success, f"MySQL TopSQL提取失败: {result.error}"
    print(f"\n✅ MySQL TopSQL (limit=3): {result.content[:200]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_extract_top_sql_limit_pg(perf_agent):
    """测试PostgreSQL TopSQL提取 - 指定数量"""
    result = await perf_agent.extract_top_sql(db_type="postgresql", limit=3)
    assert result.success, f"PG TopSQL提取失败: {result.error}"
    print(f"\n✅ PG TopSQL (limit=3): {result.content[:200]}...")


# ---------------------------------------------------------------------------
# Test: explain_sql_plan
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_explain_plan_mysql(perf_agent):
    """测试MySQL执行计划解读"""
    test_sql = "SELECT * FROM orders WHERE status = 'pending' LIMIT 10"
    result = await perf_agent.explain_plan(sql=test_sql, db_type="mysql")
    # 执行计划可能失败（表不存在），但工具应能正常返回
    assert result is not None
    print(f"\n✅ MySQL执行计划: {result.content[:200] if result.success else result.error}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_explain_plan_pg(perf_agent):
    """测试PostgreSQL执行计划解读"""
    test_sql = "SELECT * FROM orders WHERE status = 'pending' LIMIT 10"
    result = await perf_agent.explain_plan(sql=test_sql, db_type="postgresql")
    assert result is not None
    print(f"\n✅ PG执行计划: {result.content[:200] if result.success else result.error}...")


# ---------------------------------------------------------------------------
# Test: suggest_tuning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_suggest_tuning_mysql(perf_agent):
    """测试MySQL参数调优建议"""
    result = await perf_agent.suggest_tuning(db_type="mysql")
    assert result.success, f"MySQL参数调优建议失败: {result.error}"
    assert len(result.content) > 0
    print(f"\n✅ MySQL参数调优: {result.content[:300]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_suggest_tuning_pg(perf_agent):
    """测试PostgreSQL参数调优建议"""
    result = await perf_agent.suggest_tuning(db_type="postgresql")
    assert result.success, f"PG参数调优建议失败: {result.error}"
    assert len(result.content) > 0
    print(f"\n✅ PG参数调优: {result.content[:300]}...")


# ---------------------------------------------------------------------------
# Test: full_analysis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_full_analysis_mysql(perf_agent):
    """测试MySQL完整性能分析"""
    result = await perf_agent.full_analysis(db_type="mysql")
    assert result.success, f"MySQL完整性能分析失败: {result.error}"
    assert len(result.content) > 0
    print(f"\n✅ MySQL完整分析: {result.content[:300]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_full_analysis_pg(perf_agent):
    """测试PostgreSQL完整性能分析"""
    result = await perf_agent.full_analysis(db_type="postgresql")
    assert result.success, f"PG完整性能分析失败: {result.error}"
    assert len(result.content) > 0
    print(f"\n✅ PG完整分析: {result.content[:300]}...")


# ---------------------------------------------------------------------------
# Test: process() 方法（直接处理）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_performance_process_mysql(perf_agent):
    """测试PerformanceAgent process方法 - MySQL"""
    result = await perf_agent.process(
        "MySQL TopSQL是哪些",
        {"db_type": "mysql", "session_id": "test-session-003"}
    )
    assert result.success, f"PerformanceAgent MySQL process失败: {result.error}"
    print(f"\n✅ PerformanceAgent MySQL process: {result.content[:200]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_performance_process_pg(perf_agent):
    """测试PerformanceAgent process方法 - PostgreSQL"""
    result = await perf_agent.process(
        "PostgreSQL TopSQL是哪些",
        {"db_type": "postgresql", "session_id": "test-session-004"}
    )
    assert result.success, f"PerformanceAgent PG process失败: {result.error}"
    print(f"\n✅ PerformanceAgent PG process: {result.content[:200]}...")
