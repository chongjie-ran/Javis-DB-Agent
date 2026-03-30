"""
BackupAgent 真实环境测试
测试备份状态查询、历史查询、策略建议、异常告警
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
from test_runner import TestConfig, backup_agent


# ---------------------------------------------------------------------------
# Test: check_backup_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_backup_status_mysql(backup_agent):
    """测试MySQL备份状态查询"""
    result = await backup_agent.check_status(db_type="mysql")
    assert result.success, f"MySQL备份状态查询失败: {result.error}"
    assert len(result.content) > 0, "备份状态内容为空"
    print(f"\n✅ MySQL备份状态: {result.content[:200]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_backup_status_pg(backup_agent):
    """测试PostgreSQL备份状态查询"""
    result = await backup_agent.check_status(db_type="postgresql")
    assert result.success, f"PG备份状态查询失败: {result.error}"
    assert len(result.content) > 0, "备份状态内容为空"
    print(f"\n✅ PG备份状态: {result.content[:200]}...")


# ---------------------------------------------------------------------------
# Test: list_backup_history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_list_history_mysql(backup_agent):
    """测试MySQL备份历史查询"""
    result = await backup_agent.list_history(db_type="mysql", limit=10)
    assert result.success, f"MySQL备份历史查询失败: {result.error}"
    print(f"\n✅ MySQL备份历史: {result.content[:200]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_list_history_pg(backup_agent):
    """测试PostgreSQL备份历史查询"""
    result = await backup_agent.list_history(db_type="postgresql", limit=10)
    assert result.success, f"PG备份历史查询失败: {result.error}"
    print(f"\n✅ PG备份历史: {result.content[:200]}...")


# ---------------------------------------------------------------------------
# Test: suggest_strategy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_suggest_strategy_mysql(backup_agent):
    """测试MySQL备份策略建议"""
    result = await backup_agent.suggest_strategy(db_type="mysql")
    assert result.success, f"MySQL策略建议失败: {result.error}"
    assert len(result.content) > 0
    print(f"\n✅ MySQL策略建议: {result.content[:300]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_suggest_strategy_pg(backup_agent):
    """测试PostgreSQL备份策略建议"""
    result = await backup_agent.suggest_strategy(db_type="postgresql")
    assert result.success, f"PG策略建议失败: {result.error}"
    assert len(result.content) > 0
    print(f"\n✅ PG策略建议: {result.content[:300]}...")


# ---------------------------------------------------------------------------
# Test: check_alerts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_check_alerts_mysql(backup_agent):
    """测试MySQL备份告警检查"""
    result = await backup_agent.check_alerts(db_type="mysql")
    assert result.success, f"MySQL备份告警检查失败: {result.error}"
    print(f"\n✅ MySQL备份告警: {result.content[:200]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_check_alerts_pg(backup_agent):
    """测试PostgreSQL备份告警检查"""
    result = await backup_agent.check_alerts(db_type="postgresql")
    assert result.success, f"PG备份告警检查失败: {result.error}"
    print(f"\n✅ PG备份告警: {result.content[:200]}...")


# ---------------------------------------------------------------------------
# Test: estimate_restore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_estimate_restore_mysql(backup_agent):
    """测试MySQL恢复时间估算"""
    result = await backup_agent.estimate_restore(db_type="mysql")
    assert result.success, f"MySQL恢复时间估算失败: {result.error}"
    print(f"\n✅ MySQL恢复时间: {result.content[:200]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_estimate_restore_pg(backup_agent):
    """测试PostgreSQL恢复时间估算"""
    result = await backup_agent.estimate_restore(db_type="postgresql")
    assert result.success, f"PG恢复时间估算失败: {result.error}"
    print(f"\n✅ PG恢复时间: {result.content[:200]}...")


# ---------------------------------------------------------------------------
# Test: process() 方法（直接处理）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_mysql_available(), reason="MySQL不可用")
async def test_backup_process_mysql(backup_agent):
    """测试BackupAgent process方法 - MySQL"""
    result = await backup_agent.process(
        "查看MySQL备份状态",
        {"db_type": "mysql", "session_id": "test-session-001"}
    )
    assert result.success, f"BackupAgent MySQL process失败: {result.error}"
    print(f"\n✅ BackupAgent MySQL process: {result.content[:200]}...")


@pytest.mark.asyncio
@pytest.mark.skipif(not TestConfig.is_pg_available(), reason="PG不可用")
async def test_backup_process_pg(backup_agent):
    """测试BackupAgent process方法 - PostgreSQL"""
    result = await backup_agent.process(
        "查看PostgreSQL备份状态",
        {"db_type": "postgresql", "session_id": "test-session-002"}
    )
    assert result.success, f"BackupAgent PG process失败: {result.error}"
    print(f"\n✅ BackupAgent PG process: {result.content[:200]}...")
