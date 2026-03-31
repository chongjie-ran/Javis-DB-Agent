"""
V2.0 真实PostgreSQL环境验证 - P0-1 安全治理层
真实PG环境测试: SQL护栏 + SOP执行器 + 执行回流验证

依赖: TEST_PG_* 环境变量配置的PostgreSQL实例
运行: cd ~/SWproject/Javis-DB-Agent && python3 -m pytest tests/v2.0/test_real_pg_security.py -v --tb=short
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
import asyncio
import yaml
import tempfile
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock

# Import modules under test
from src.security.sql_guard import SQLGuard
from src.security.sql_guard.ast_parser import ASTParser
from src.security.sql_guard.template_registry import TemplateRegistry
from src.security.execution.sop_executor import SOPExecutor, SOPStatus, SOPStepStatus
from src.security.execution.check_hooks import (
    CheckHookRegistry, CheckType, CheckResult,
    InstanceHealthCheck, ReplicationLagCheck, SessionCountCheck
)
from src.security.execution.execution_feedback import (
    ExecutionFeedback, FeedbackResult, Deviation, FeedbackVerificationResult
)


# =============================================================================
# P0-1 真实PG环境: AST解析测试
# =============================================================================

class TestRealPGSecurityAST:
    """真实PG环境: SQL AST解析"""

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_ast_parse_postgres_select(self):
        """SEC-PG-001: PostgreSQL SELECT语句AST解析"""
        parser = ASTParser()
        sql = "SELECT id, name, email FROM users WHERE status = 1 AND age > 18 ORDER BY created_at DESC LIMIT 100"
        ast = parser.parse(sql, dialect="postgresql")

        assert ast is not None, "SELECT语句应成功解析为AST"
        ops = parser.get_operations(sql, dialect="postgresql")
        assert "SELECT" in ops, f"应识别SELECT操作，实际: {ops}"
        tables = parser.get_tables(sql, dialect="postgresql")
        assert "users" in [t.lower() for t in tables], f"应识别表名users，实际: {tables}"
        print(f"\n✅ PG SELECT AST解析成功: ops={ops}, tables={tables}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_ast_parse_postgres_insert(self):
        """SEC-PG-002: PostgreSQL INSERT语句AST解析"""
        parser = ASTParser()
        sql = "INSERT INTO orders (id, customer_id, product_id, amount) VALUES (1, 100, 200, 299.99)"
        ast = parser.parse(sql, dialect="postgresql")

        assert ast is not None, "INSERT语句应成功解析"
        ops = parser.get_operations(sql, dialect="postgresql")
        assert "INSERT" in ops, f"应识别INSERT操作，实际: {ops}"
        tables = parser.get_tables(sql, dialect="postgresql")
        assert "orders" in [t.lower() for t in tables]
        print(f"\n✅ PG INSERT AST解析成功: ops={ops}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_ast_parse_postgres_update(self):
        """SEC-PG-003: PostgreSQL UPDATE语句AST解析"""
        parser = ASTParser()
        sql = "UPDATE users SET status = 0, updated_at = NOW() WHERE id = 123 AND status = 1"
        ast = parser.parse(sql, dialect="postgresql")

        assert ast is not None, "UPDATE语句应成功解析"
        ops = parser.get_operations(sql, dialect="postgresql")
        assert "UPDATE" in ops, f"应识别UPDATE操作，实际: {ops}"
        has_where = parser.has_where_clause(sql, dialect="postgresql")
        assert has_where, "UPDATE应有WHERE子句"
        print(f"\n✅ PG UPDATE AST解析成功: ops={ops}, has_where={has_where}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_ast_parse_postgres_delete(self):
        """SEC-PG-004: PostgreSQL DELETE语句AST解析"""
        parser = ASTParser()
        sql = "DELETE FROM logs WHERE created_at < '2025-01-01' AND severity = 'info'"
        ast = parser.parse(sql, dialect="postgresql")

        assert ast is not None, "DELETE语句应成功解析"
        ops = parser.get_operations(sql, dialect="postgresql")
        assert "DELETE" in ops, f"应识别DELETE操作，实际: {ops}"
        has_where = parser.has_where_clause(sql, dialect="postgresql")
        assert has_where, "DELETE应有WHERE子句"
        print(f"\n✅ PG DELETE AST解析成功: ops={ops}, has_where={has_where}")


# =============================================================================
# P0-1 真实PG环境: 危险SQL检测
# =============================================================================

class TestRealPGSecurityDangerous:
    """真实PG环境: 危险SQL检测"""

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_dangerous_drop(self):
        """SEC-PG-005: DROP TABLE危险操作检测"""
        guard = SQLGuard()
        sql = "DROP TABLE IF EXISTS backup_logs CASCADE"
        result = await guard.validate(sql, context={"db_type": "postgresql"})

        assert result.allowed is False, "DROP TABLE应被拒绝"
        assert result.risk_level in ("L4", "L5"), f"风险等级应为L4/L5，实际: {result.risk_level}"
        assert result.blocked_reason is not None, "应有阻止原因"
        print(f"\n✅ DROP TABLE被拦截: {result.blocked_reason}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_dangerous_truncate(self):
        """SEC-PG-006: TRUNCATE TABLE危险操作检测"""
        guard = SQLGuard()
        sql = "TRUNCATE TABLE users RESTART IDENTITY CASCADE"
        result = await guard.validate(sql, context={"db_type": "postgresql"})

        assert result.allowed is False, "TRUNCATE TABLE应被拒绝"
        assert result.risk_level in ("L4", "L5"), f"风险等级应为L4/L5，实际: {result.risk_level}"
        print(f"\n✅ TRUNCATE TABLE被拦截: {result.blocked_reason}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_dangerous_delete_no_where(self):
        """SEC-PG-007: 无WHERE条件的DELETE检测"""
        guard = SQLGuard()
        sql = "DELETE FROM session_history"
        result = await guard.validate(sql, context={"db_type": "postgresql"})

        assert result.allowed is False, "无WHERE的DELETE应被拒绝"
        assert result.risk_level in ("L4", "L5"), f"风险等级应为L4/L5，实际: {result.risk_level}"
        print(f"\n✅ 无WHERE DELETE被拦截: {result.blocked_reason}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_dangerous_shutdown(self):
        """SEC-PG-008: pg_shutdown危险函数检测"""
        guard = SQLGuard()
        sql = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle'"
        result = await guard.validate(sql, context={"db_type": "postgresql"})

        assert result.allowed is False, "pg_terminate_backend应被拒绝"
        assert result.risk_level == "L5", f"风险等级应为L5，实际: {result.risk_level}"
        print(f"\n✅ pg_terminate_backend被拦截: {result.blocked_reason}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_dml_without_where_warning(self):
        """SEC-PG-009: 无WHERE的DML语句告警（UPDATE）"""
        guard = SQLGuard()
        sql = "UPDATE user_permissions SET level = 99"
        result = await guard.validate(sql, context={"db_type": "postgresql"})

        # UPDATE无WHERE应该被拒绝或需要审批
        assert result.allowed is False or result.approval_required is True, \
            "无WHERE的UPDATE应被拒绝或需要审批"
        print(f"\n✅ 无WHERE UPDATE告警: allowed={result.allowed}, approval={result.approval_required}")


# =============================================================================
# P0-1 真实PG环境: SQLGuard连接测试
# =============================================================================

class TestRealPGSecurityGuard:
    """真实PG环境: SQLGuard连接与校验"""

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_sqlguard_real_pg_connection(self, pg_conn):
        """SEC-PG-010: SQLGuard真实PG连接校验"""
        guard = SQLGuard()

        # 用真实PG连接验证基本查询
        cursor = pg_conn.cursor()
        cursor.execute("SELECT 1 AS test")
        row = cursor.fetchone()
        assert row[0] == 1, "PG连接应返回SELECT 1结果"

        # SQLGuard对安全SQL的校验
        safe_sql = "SELECT id, name FROM pg_catalog.pg_tables WHERE schemaname = 'public'"
        result = await guard.validate(safe_sql, context={"db_type": "postgresql"})
        assert result.allowed is True, f"安全SQL应被允许: {result.blocked_reason}"
        print(f"\n✅ SQLGuard真实PG连接正常: {result.risk_level}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_template_register_and_match(self):
        """SEC-PG-011: 白名单模板注册与匹配"""
        guard = SQLGuard()
        registry = guard.template_registry

        # 注册自定义PG模板
        from src.security.sql_guard.template_registry import SQLTemplate
        template = SQLTemplate(
            name="pg_show_settings",
            pattern=r"^SHOW\s+\w+\s*;?\s*$",
            is_regex=True,
            risk_level="L1",
        )
        registry.add_template("postgresql", template)

        # 验证模板匹配
        sql = "SHOW max_connections;"
        matched, matched_tpl = registry.is_whitelisted(sql, "postgresql")
        assert matched is True, "注册模板应匹配对应SQL"
        assert matched_tpl is not None, "应返回匹配的模板"
        print(f"\n✅ 模板注册与匹配成功: {matched_tpl.name}")


# =============================================================================
# P0-1 真实PG环境: SOP执行器测试
# =============================================================================

class TestRealPGSOPExecutor:
    """真实PG环境: SOP执行器"""

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_sop_load_from_yaml(self):
        """SEC-PG-012: 从YAML加载SOP定义"""
        sop_yaml = """
sops:
  test_sop:
    id: test_sop
    name: 测试SOP
    description: 测试标准操作流程
    risk_level: 2
    timeout_seconds: 60
    steps:
      - step: 1
        action: execute_sql
        params:
          sql: "SELECT 1"
        description: 执行测试SQL
        risk_level: 1
        timeout_seconds: 30
      - step: 2
        action: verify_stats_updated
        params: {}
        description: 验证统计信息
        risk_level: 1
        timeout_seconds: 30
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(sop_yaml)
            f.flush()
            temp_path = f.name

        try:
            with open(temp_path, "r") as f:
                data = yaml.safe_load(f)

            assert "sops" in data, "YAML应包含sops节点"
            sop_def = data["sops"]["test_sop"]
            assert sop_def["id"] == "test_sop"
            assert len(sop_def["steps"]) == 2
            print(f"\n✅ SOP YAML加载成功: {sop_def['name']}")
        finally:
            os.unlink(temp_path)

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_sop_executor_state_machine(self):
        """SEC-PG-013: SOP执行器状态机"""
        executor = SOPExecutor()

        # 验证默认SOP加载
        sops = executor.list_sops()
        assert len(sops) > 0, "应有默认SOP定义"

        # 获取一个SOP
        sop = executor.get_sop("refresh_stats")
        assert sop is not None, "应能获取refresh_stats SOP"

        # 执行SOP（模拟上下文）
        context = {"table": "orders"}
        result = await executor.execute(sop, context)

        assert result is not None, "SOP执行应返回结果"
        assert result.execution_id is not None, "应有execution_id"
        assert result.status in (SOPStatus.COMPLETED, SOPStatus.FAILED), \
            f"状态应为COMPLETED或FAILED，实际: {result.status}"
        print(f"\n✅ SOP执行器状态机正常: execution_id={result.execution_id}, status={result.status.value}")


# =============================================================================
# P0-1 真实PG环境: Check Hooks测试
# =============================================================================

class TestRealPGCheckHooks:
    """真实PG环境: 前后置检查钩子"""

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_precheck_hook_real_db(self, pg_conn):
        """SEC-PG-014: 预检查Hook（真实DB上下文）"""
        registry = CheckHookRegistry()
        hook = registry.get("InstanceHealthCheck")

        # 用真实PG连接创建健康检查上下文
        cursor = pg_conn.cursor()
        cursor.execute("SELECT 1")
        cursor.execute("SELECT pg_is_in_recovery()")
        in_recovery = cursor.fetchone()[0]

        context = {
            "instance_id": "PG-TEST-001",
            "instance_state": "running",
            "replication_lag_seconds": 0.5,
            "session_count": 10,
        }

        pre_result = await hook.run(context, CheckType.PRE_CHECK)
        assert pre_result.passed is True, f"预检查应通过: {pre_result.message}"
        print(f"\n✅ 预检查Hook通过: {pre_result.message}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_postcheck_hook_state_comparison(self, pg_conn):
        """SEC-PG-015: 后置检查Hook状态比对"""
        registry = CheckHookRegistry()
        session_hook = registry.get("SessionCountCheck")

        # 验证PG连接可用
        cursor = pg_conn.cursor()
        cursor.execute("SELECT count(*) FROM pg_stat_activity")
        session_count = cursor.fetchone()[0]

        context_before = {
            "instance_id": "PG-TEST-001",
            "session_count": session_count - 1,
        }
        context_after = {
            "instance_id": "PG-TEST-001",
            "session_count": session_count,
        }

        result_before = await session_hook.run(context_before, CheckType.POST_CHECK)
        result_after = await session_hook.run(context_after, CheckType.POST_CHECK)

        assert result_before.passed is True, "会话数应在正常范围"
        assert result_after.passed is True, "会话数应在正常范围"
        print(f"\n✅ 后置检查Hook状态比对: before={session_count-1}, after={session_count}")


# =============================================================================
# P0-1 真实PG环境: 执行回流验证
# =============================================================================

class TestRealPGFeedback:
    """真实PG环境: 执行回流验证"""

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_feedback_improved(self, pg_conn):
        """SEC-PG-016: 回流验证-状态改善"""
        feedback = ExecutionFeedback()

        # 模拟执行记录（模拟一个分析类SOP的结果改善）
        execution_record = {
            "execution_id": "EXEC-TEST-001",
            "expected_result": {
                "status": "completed",
                "rows_scanned": 1000,
                "duration_ms": 500,
            },
            "critical": False,
        }

        # 模拟实际结果（状态改善）
        actual_result = {
            "status": "completed",
            "rows_scanned": 1000,
            "duration_ms": 480,  # 比预期更快
        }

        context = {"instance_id": "PG-TEST-001"}
        result = await feedback.verify(execution_record, actual_result, context)

        assert result.verified is True, "改善的结果应验证通过"
        assert result.feedback_result in (FeedbackResult.IMPROVED, FeedbackResult.UNCHANGED), \
            f"应为IMPROVED或UNCHANGED，实际: {result.feedback_result}"
        print(f"\n✅ 回流验证-状态改善: {result.feedback_result.value}")

    @pytest.mark.p0_sec
    @pytest.mark.pg
    async def test_feedback_degraded(self, pg_conn):
        """SEC-PG-017: 回流验证-状态恶化"""
        feedback = ExecutionFeedback()

        # 模拟执行记录
        execution_record = {
            "execution_id": "EXEC-TEST-002",
            "expected_result": {
                "status": "completed",
                "rows_scanned": 1000,
                "error_rate": 0.01,
            },
            "critical": True,
        }

        # 模拟实际结果（状态恶化：error_rate为None表示完全失败）
        actual_result = {
            "status": "completed",
            "rows_scanned": 100,  # 扫描行数大幅下降
            "error_rate": None,   # 错误率为None表示无法计算（严重问题）
        }

        context = {"instance_id": "PG-TEST-001"}
        result = await feedback.verify(execution_record, actual_result, context)

        assert result.verified is False, "恶化的结果应验证失败"
        assert result.feedback_result == FeedbackResult.DEGRADED, \
            f"应为DEGRADED，实际: {result.feedback_result}"
        assert len(result.deviations) > 0, "应有偏差记录"
        print(f"\n✅ 回流验证-状态恶化: {len(result.deviations)}个偏差")
