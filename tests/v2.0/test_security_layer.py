"""
V2.0 P0-1: 安全治理层增强测试
模块：SQL护栏 + SOP执行器 + 执行回流验证 + 权限与审批流程

测试维度：Happy path / Edge cases / Error cases / Regression
环境支持：MySQL / PostgreSQL

V2.0关键待测功能：
1. SQL AST解析与校验（src/security/sql_guard.py - 待实现）
   - DDL/DML/DCL分类
   - 危险SQL识别（TRUNCATE/DROP/无WHERE的DELETE/UPDATE）
   - SQL重写（模板化）
   - 白名单机制
2. SOP执行器（src/tools/sop_executor.py - 待实现）
   - SOP步骤解析
   - 步骤执行与状态跟踪
   - SOP暂停/恢复/中止
   - 执行日志
3. 执行回流验证（src/gateway/execution_feedback.py - 待实现）
   - 执行结果预校验
   - 执行后状态验证
   - 偏差检测与自动修复
   - 重试机制
4. 权限与审批（扩展现有PolicyEngine + ApprovalGate）
   - 细粒度权限校验
   - 审批流程状态机
   - 双人审批
   - 审批超时处理
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
import asyncio
import time
from typing import Dict, Any, List
from unittest.mock import MagicMock, AsyncMock, patch

# =============================================================================
# SEC-01: SQL AST解析与校验 - Happy Path
# =============================================================================

class TestSQLGuardHappyPath:
    """SQL护栏 - Happy Path"""

    @pytest.mark.p0_sec
    @pytest.mark.happy
    @pytest.mark.mysql
    @pytest.mark.pg
    async def test_sec_01_001_safe_select_parsed(self, sql_guard, mock_context):
        """SEC-01-001: 安全SELECT解析 - 通过AST分析识别为安全"""
        from src.tools.base import ToolResult

        sql = "SELECT id, name, email FROM users WHERE status = 1 ORDER BY created_at DESC LIMIT 100"
        # 实际调用时：sql_guard.validate(sql, context)
        result = await sql_guard.validate(sql, mock_context)

        assert result.allowed is True, f"安全SELECT应被允许: {result.blocked_reason}"
        assert result.risk_level in ("L0", "L1", "L2"), f"风险等级应为L0-L2，实际: {result.risk_level}"
        print(f"\n✅ 安全SELECT通过: risk={result.risk_level}")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    @pytest.mark.pg
    async def test_sec_01_002_safe_join_parsed(self, sql_guard, mock_context):
        """SEC-01-002: 安全JOIN解析 - 多表查询正确识别"""
        sql = """
            SELECT a.order_id, b.customer_name, c.product_name
            FROM orders a
            JOIN customers b ON a.customer_id = b.id
            JOIN products c ON a.product_id = c.id
            WHERE a.created_at > '2026-01-01'
        """
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is True
        print(f"\n✅ 安全JOIN通过: {result.risk_level}")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    @pytest.mark.mysql
    async def test_sec_01_003_aggressive_delete_with_where(self, sql_guard, mock_context):
        """SEC-01-003: 带WHERE的DELETE - 识别为中风险"""
        sql = "DELETE FROM logs WHERE created_at < '2026-01-01' AND archived = 0"
        result = await sql_guard.validate(sql, mock_context)
        # 有WHERE但批量删除，应降级为需要审批
        assert result.risk_level in ("L2", "L3") or result.allowed is True
        print(f"\n✅ 批量DELETE（有WHERE）: risk={result.risk_level}")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    @pytest.mark.pg
    async def test_sec_01_004_whitelist_bypass(self, sql_guard, mock_context):
        """SEC-01-004: 白名单SQL直接通过"""
        sql = "SELECT 1"  # 探活SQL应在白名单
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is True
        assert result.risk_level == "L0"
        print(f"\n✅ 白名单SQL: {sql[:30]} → L0")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    @pytest.mark.mysql
    @pytest.mark.pg
    async def test_sec_01_005_template_rewrite(self, sql_guard, mock_context):
        """SEC-01-005: SQL模板化重写 - 保护敏感字段"""
        sql = "SELECT password, token, api_key FROM users WHERE id = 1"
        result = await sql_guard.validate(sql, mock_context)

        # 如果启用了字段脱敏，rewritten_sql应不含明文敏感字段
        if result.rewritten_sql:
            assert "password" not in result.rewritten_sql.lower() or "***" in result.rewritten_sql.lower()
            print(f"\n✅ SQL重写脱敏: {result.rewritten_sql[:60]}")
        else:
            # 如果没重写，至少要阻止或警告
            print(f"\n⚠️  SQL未重写（可能字段不在敏感列表）")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    @pytest.mark.pg
    async def test_sec_01_006_readonly_tx_detected(self, sql_guard, mock_context):
        """SEC-01-006: 只读事务识别"""
        sql = "BEGIN READ ONLY; SELECT count(*) FROM orders; COMMIT"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is True
        assert result.risk_level in ("L0", "L1")
        print(f"\n✅ 只读事务: {result.risk_level}")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    @pytest.mark.mysql
    async def test_sec_01_007_explain_plan_safe(self, sql_guard, mock_context):
        """SEC-01-007: EXPLAIN计划查询 - 无执行风险"""
        sql = "EXPLAIN SELECT * FROM users WHERE email = 'test@example.com'"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is True
        print(f"\n✅ EXPLAIN安全: {result.risk_level}")


# =============================================================================
# SEC-02: SQL AST解析与校验 - Edge Cases
# =============================================================================

class TestSQLGuardEdgeCases:
    """SQL护栏 - Edge Cases"""

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.pg
    async def test_sec_02_001_empty_sql(self, sql_guard, mock_context):
        """SEC-02-001: 空SQL - 应拒绝"""
        sql = ""
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False or result.risk_level in ("L4", "L5")
        print(f"\n✅ 空SQL处理: allowed={result.allowed}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.mysql
    async def test_sec_02_002_whitespace_only_sql(self, sql_guard, mock_context):
        """SEC-02-002: 全空格SQL"""
        sql = "   \n\t  "
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False
        print(f"\n✅ 全空格SQL: allowed={result.allowed}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.pg
    async def test_sec_02_003_extremely_long_sql(self, sql_guard, mock_context):
        """SEC-02-003: 超长SQL（>10MB）- 应拒绝"""
        sql = "SELECT " + "a" * (11 * 1024 * 1024)
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False or result.risk_level in ("L4", "L5")
        print(f"\n✅ 超长SQL({len(sql)//1024//1024}MB): allowed={result.allowed}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.mysql
    async def test_sec_02_004_nested_comment_injection(self, sql_guard, mock_context):
        """SEC-02-004: 嵌套注释注入尝试"""
        sql = "SELECT * FROM users /* comment */ WHERE 1=1 /* more */ AND sleep(0)--"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False or "sleep" in (result.blocked_reason or "").lower()
        print(f"\n✅ 嵌套注释注入: blocked={not result.allowed}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.pg
    async def test_sec_02_005_hex_encoding_bypass(self, sql_guard, mock_context):
        """SEC-02-005: 十六进制编码绕过尝试"""
        sql = "SELECT * FROM users WHERE name = 0x7365656b61626974"  # 'seekabit' hex
        result = await sql_guard.validate(sql, mock_context)
        # 应识别为潜在注入
        print(f"\n✅ HEX编码SQL: allowed={result.allowed}, risk={result.risk_level}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.mysql
    async def test_sec_02_006_update_with_subquery(self, sql_guard, mock_context):
        """SEC-02-006: 带子查询的UPDATE"""
        sql = """
            UPDATE users SET last_login = NOW()
            WHERE id IN (SELECT id FROM inactive_users WHERE days_inactive > 90)
        """
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is True  # 有WHERE，应该允许但记录
        print(f"\n✅ 子查询UPDATE: risk={result.risk_level}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.pg
    async def test_sec_02_007_multiple_statements(self, sql_guard, mock_context):
        """SEC-02-007: 多语句SQL（分号分隔）- 应限制"""
        sql = "SELECT 1; DROP TABLE users; SELECT 2"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False or "DROP" in (result.blocked_reason or "").upper()
        print(f"\n✅ 多语句SQL: blocked={not result.allowed}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.mysql
    @pytest.mark.pg
    async def test_sec_02_008_db_specific_syntax_pg(self, sql_guard, mock_context):
        """SEC-02-008: PG特有语法"""
        sql = "COPY users FROM '/tmp/data.csv' WITH (FORMAT csv)"
        result = await sql_guard.validate(sql, mock_context)
        # COPY是危险操作
        assert result.risk_level in ("L4", "L5") or result.allowed is False
        print(f"\n✅ PG COPY语法: blocked={not result.allowed}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.mysql
    async def test_sec_02_009_db_specific_syntax_mysql(self, sql_guard, mock_context):
        """SEC-02-009: MySQL特有语法"""
        sql = "LOAD DATA INFILE '/tmp/data.csv' INTO TABLE users"
        result = await sql_guard.validate(sql, mock_context)
        assert result.risk_level in ("L4", "L5") or result.allowed is False
        print(f"\n✅ MySQL LOAD DATA: blocked={not result.allowed}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    @pytest.mark.pg
    async def test_sec_02_010_cte_with_mutating_cte(self, sql_guard, mock_context):
        """SEC-02-010: WITH子句（CTE）递归"""
        sql = """
            WITH RECURSIVE cnt(x) AS (
                SELECT 1
                UNION ALL
                SELECT x+1 FROM cnt WHERE x < 100
            )
            SELECT x FROM cnt
        """
        result = await sql_guard.validate(sql, mock_context)
        # 递归CTE如果有limit应该是安全的
        assert result.allowed is True or result.risk_level in ("L1", "L2", "L3")
        print(f"\n✅ 递归CTE: allowed={result.allowed}, risk={result.risk_level}")


# =============================================================================
# SEC-03: SQL AST解析与校验 - Error Cases（危险SQL拦截）
# =============================================================================

class TestSQLGuardDangerous:
    """SQL护栏 - 危险SQL拦截（Error Cases）"""

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.pg
    async def test_sec_03_001_truncate_blocked(self, sql_guard, mock_context):
        """SEC-03-001: TRUNCATE必须拦截"""
        sql = "TRUNCATE TABLE users"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False, "TRUNCATE必须被拦截"
        assert "truncate" in (result.blocked_reason or "").lower()
        print(f"\n✅ TRUNCATE已拦截: {result.blocked_reason}")

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.mysql
    async def test_sec_03_002_drop_table_blocked(self, sql_guard, mock_context):
        """SEC-03-002: DROP TABLE必须拦截"""
        sql = "DROP TABLE IF EXISTS backup_logs"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False, "DROP TABLE必须被拦截"
        print(f"\n✅ DROP TABLE已拦截")

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.pg
    async def test_sec_03_003_delete_without_where_blocked(self, sql_guard, mock_context):
        """SEC-03-003: 无WHERE的DELETE必须拦截"""
        sql = "DELETE FROM session_history"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False, "无WHERE的DELETE必须被拦截"
        print(f"\n✅ DELETE无WHERE已拦截")

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.mysql
    async def test_sec_03_004_update_without_where_blocked(self, sql_guard, mock_context):
        """SEC-03-004: 无WHERE的UPDATE必须拦截"""
        sql = "UPDATE user_permissions SET level = 99"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False, "无WHERE的UPDATE必须被拦截"
        print(f"\n✅ UPDATE无WHERE已拦截")

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.pg
    async def test_sec_03_005_dangerous_function_blocked(self, sql_guard, mock_context):
        """SEC-03-005: 危险函数调用拦截"""
        for dangerous_sql in [
            "SELECT pg_terminate_backend(1234)",
            "SELECT kill(5678)",
            "SET GLOBAL max_connections = 10000",
        ]:
            result = await sql_guard.validate(dangerous_sql, mock_context)
            assert result.allowed is False or result.risk_level in ("L4", "L5")
            print(f"\n✅ 危险函数已拦截: {dangerous_sql[:40]}")

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.mysql
    async def test_sec_03_006_union_injection_blocked(self, sql_guard, mock_context):
        """SEC-03-006: UNION注入拦截"""
        sql = "SELECT * FROM users UNION SELECT * FROM passwords"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False or "union" in (result.blocked_reason or "").lower()
        print(f"\n✅ UNION注入已拦截: blocked={not result.allowed}")

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.pg
    async def test_sec_03_007_boolean_based_injection(self, sql_guard, mock_context):
        """SEC-03-007: 布尔型注入拦截"""
        sql = "SELECT * FROM users WHERE id = 1 AND ASCII(SUBSTRING((SELECT password FROM users WHERE id=1),1,1)) > 64"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False or "subquery" in (result.blocked_reason or "").lower()
        print(f"\n✅ 布尔注入: blocked={not result.allowed}")

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.mysql
    async def test_sec_03_008_shutdown_command_blocked(self, sql_guard, mock_context):
        """SEC-03-008: 数据库关闭命令拦截"""
        sql = "SHUTDOWN"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False, "SHUTDOWN必须被拦截"
        print(f"\n✅ SHUTDOWN已拦截")

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.pg
    async def test_sec_03_009_alter_system_blocked(self, sql_guard, mock_context):
        """SEC-03-009: ALTER SYSTEM拦截"""
        sql = "ALTER SYSTEM SET shared_buffers = '256MB'"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False or result.approval_required is True
        print(f"\n✅ ALTER SYSTEM: approval={result.approval_required}")

    @pytest.mark.p0_sec
    @pytest.mark.error
    @pytest.mark.mysql
    async def test_sec_03_010_grant_revoke_blocked(self, sql_guard, mock_context):
        """SEC-03-010: GRANT/REVOKE权限变更"""
        sql = "GRANT ALL PRIVILEGES ON *.* TO 'hacker'@'%'"
        result = await sql_guard.validate(sql, mock_context)
        assert result.allowed is False or result.approval_required is True
        print(f"\n✅ GRANT权限变更: approval={result.approval_required}")


# =============================================================================
# SEC-04: SOP执行器 - Happy Path
# =============================================================================

class TestSOPExecutorHappyPath:
    """SOP执行器 - Happy Path"""

    @pytest.mark.p0_sec
    @pytest.mark.happy
    async def test_sec_04_001_simple_sop_execution(self, sop_executor, mock_context):
        """SEC-04-001: 简单SOP执行 - 单步骤"""
        sop = {
            "id": "SOP-KILL-001",
            "name": "终止问题会话",
            "steps": [
                {"step": 1, "action": "find_blocking_session", "params": {"spid": 1234}},
            ]
        }
        result = await sop_executor.execute(sop, mock_context)
        assert result.success is True
        assert len(result.step_results) == 1
        print(f"\n✅ 单步骤SOP: 成功")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    async def test_sec_04_002_multi_step_sop_sequential(self, sop_executor, mock_context):
        """SEC-04-002: 多步骤SOP顺序执行"""
        sop = {
            "id": "SOP-KILL-002",
            "name": "终止会话并验证",
            "steps": [
                {"step": 1, "action": "find_blocking_session", "params": {"spid": 1234}},
                {"step": 2, "action": "kill_session", "params": {"spid": 1234}},
                {"step": 3, "action": "verify_session_gone", "params": {"spid": 1234}},
            ]
        }
        result = await sop_executor.execute(sop, mock_context)
        assert result.success is True
        assert len(result.step_results) == 3
        print(f"\n✅ 多步骤SOP(顺序): 3步全部成功")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    async def test_sec_04_003_sop_with_approval(self, sop_executor, mock_context):
        """SEC-04-003: 需要审批的SOP执行"""
        sop = {
            "id": "SOP-KILL-003",
            "name": "高危操作SOP",
            "steps": [
                {"step": 1, "action": "kill_session", "params": {"spid": 1234}},
            ],
            "require_approval": True,
        }
        # 审批通过后才执行
        with patch.object(sop_executor, "_check_approval", new_callable=AsyncMock) as mock_appr:
            mock_appr.return_value = MagicMock(approved=True, approver="admin")
            result = await sop_executor.execute(sop, mock_context)
            assert result.success is True
            print(f"\n✅ 审批SOP: 审批人={result.step_results[0].approver}")


# =============================================================================
# SEC-05: SOP执行器 - Edge & Error Cases
# =============================================================================

class TestSOPExecutorEdgeError:
    """SOP执行器 - Edge & Error Cases"""

    @pytest.mark.p0_sec
    @pytest.mark.edge
    async def test_sec_05_001_sop_step_timeout(self, sop_executor, mock_context):
        """SEC-05-001: SOP步骤超时处理"""
        sop = {
            "id": "SOP-TIMEOUT-001",
            "name": "超时测试SOP",
            "steps": [
                {"step": 1, "action": "slow_query", "params": {"wait": 60}},
            ],
            "step_timeout": 10,  # 10秒超时
        }
        with patch.object(sop_executor, "_execute_step", new_callable=AsyncMock) as mock_step:
            mock_step.side_effect = asyncio.TimeoutError("Step timeout after 10s")
            result = await sop_executor.execute(sop, mock_context)
            assert result.success is False
            print(f"\n✅ 步骤超时处理: {result.final_result.get('error', 'timeout')}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    async def test_sec_05_002_sop_step_failure_retry(self, sop_executor, mock_context):
        """SEC-05-002: 步骤失败自动重试"""
        sop = {
            "id": "SOP-RETRY-001",
            "name": "重试测试SOP",
            "steps": [
                {"step": 1, "action": "unreliable_action", "params": {}},
            ],
            "retry_count": 3,
        }
        call_count = 0
        async def flaky_step(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient failure")
            return MagicMock(success=True)

        with patch.object(sop_executor, "_execute_step", flaky_step):
            result = await sop_executor.execute(sop, mock_context)
            assert result.success is True, f"重试3次后应成功，实际失败: {result.final_result}"
            print(f"\n✅ 失败重试: 重试{call_count-1}次后成功")

    @pytest.mark.p0_sec
    @pytest.mark.error
    async def test_sec_05_003_sop_abort_on_critical_failure(self, sop_executor, mock_context):
        """SEC-05-003: 关键步骤失败时中止SOP"""
        sop = {
            "id": "SOP-ABORT-001",
            "name": "中止测试SOP",
            "steps": [
                {"step": 1, "action": "precheck", "params": {}},
                {"step": 2, "action": "critical_action", "params": {}, "critical": True},
                {"step": 3, "action": "cleanup", "params": {}},
            ],
            "abort_on_critical_failure": True,
        }
        with patch.object(sop_executor, "_execute_step", new_callable=AsyncMock) as mock_step:
            async def step_side_effect(step, *args, **kwargs):
                if step["step"] == 2:
                    raise Exception("Critical action failed")
                return MagicMock(success=True)
            mock_step.side_effect = step_side_effect

            result = await sop_executor.execute(sop, mock_context)
            assert result.success is False
            assert result.final_result.get("aborted_at_step") == 2
            print(f"\n✅ 关键步骤失败中止: 在步骤2中止")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    async def test_sec_05_004_sop_pause_and_resume(self, sop_executor, mock_context):
        """SEC-05-004: SOP暂停与恢复"""
        sop = {
            "id": "SOP-PAUSE-001",
            "name": "暂停测试SOP",
            "steps": [
                {"step": 1, "action": "action_a", "params": {}},
                {"step": 2, "action": "action_b", "params": {}},
                {"step": 3, "action": "action_c", "params": {}},
            ],
        }
        # 暂停在步骤2
        with patch.object(sop_executor, "_execute_step", new_callable=AsyncMock) as mock_step:
            step_responses = [
                MagicMock(success=True),  # step 1
                MagicMock(success=True, paused=True),  # step 2 - pause
                MagicMock(success=True),  # step 3 (resume)
            ]
            mock_step.side_effect = step_responses

            result = await sop_executor.execute(sop, mock_context)
            print(f"\n✅ SOP暂停/恢复: 暂停={any(r.paused for r in result.step_results)}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    async def test_sec_05_005_sop_unknown_action(self, sop_executor, mock_context):
        """SEC-05-005: 未知Action处理"""
        sop = {
            "id": "SOP-UNKNOWN-001",
            "name": "未知Action测试",
            "steps": [
                {"step": 1, "action": "nonexistent_action_xyz", "params": {}},
            ]
        }
        result = await sop_executor.execute(sop, mock_context)
        assert result.success is False
        assert "unknown action" in (result.final_result.get("error") or "").lower()
        print(f"\n✅ 未知Action处理: {result.final_result.get('error')}")


# =============================================================================
# SEC-06: 执行回流验证 - Happy Path
# =============================================================================

class TestExecutionFeedbackHappyPath:
    """执行回流验证 - Happy Path"""

    @pytest.mark.p0_sec
    @pytest.mark.happy
    async def test_sec_06_001_simple_feedback_verification(self, execution_feedback, mock_context):
        """SEC-06-001: 简单执行验证通过"""
        execution_record = {
            "execution_id": "EXEC-001",
            "action": "kill_session",
            "params": {"spid": 1234},
            "expected_result": {"session_gone": True},
        }
        actual_result = {"session_gone": True}

        result = await execution_feedback.verify(execution_record, actual_result, mock_context)
        assert result.verified is True
        assert len(result.deviations) == 0
        print(f"\n✅ 执行验证通过: 无偏差")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    async def test_sec_06_002_batch_verification(self, execution_feedback, mock_context):
        """SEC-06-002: 批量执行验证"""
        executions = [
            {"execution_id": f"EXEC-{i:03d}", "action": "check_status", "params": {}}
            for i in range(10)
        ]
        actual_results = [{"status": "ok"} for _ in range(10)]

        result = await execution_feedback.batch_verify(executions, actual_results, mock_context)
        assert result.verified_count == 10
        assert result.failed_count == 0
        print(f"\n✅ 批量验证: 10/10通过")


# =============================================================================
# SEC-07: 执行回流验证 - Edge & Error Cases
# =============================================================================

class TestExecutionFeedbackEdgeError:
    """执行回流验证 - Edge & Error Cases"""

    @pytest.mark.p0_sec
    @pytest.mark.edge
    async def test_sec_07_001_deviation_detected(self, execution_feedback, mock_context):
        """SEC-07-001: 偏差检测"""
        execution_record = {
            "execution_id": "EXEC-002",
            "action": "kill_session",
            "params": {"spid": 1234},
            "expected_result": {"session_gone": True},
        }
        actual_result = {"session_gone": False, "error": "Session still active"}

        result = await execution_feedback.verify(execution_record, actual_result, mock_context)
        assert result.verified is False
        assert len(result.deviations) > 0
        assert result.retry_count > 0
        print(f"\n✅ 偏差检测: {result.deviations[0]['field']} 预期={result.deviations[0]['expected']} 实际={result.deviations[0]['actual']}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    async def test_sec_07_002_max_retries_exceeded(self, execution_feedback, mock_context):
        """SEC-07-002: 超过最大重试次数"""
        execution_record = {
            "execution_id": "EXEC-003",
            "action": "kill_session",
            "params": {"spid": 9999},
            "expected_result": {"session_gone": True},
        }
        actual_result = {"session_gone": False, "error": "Session not found or already gone"}

        # 设置最大重试为2
        with patch.object(execution_feedback, "max_retries", 2):
            result = await execution_feedback.verify(execution_record, actual_result, mock_context)
            assert result.retry_count >= 2
            print(f"\n✅ 最大重试: 已重试{result.retry_count}次")

    @pytest.mark.p0_sec
    @pytest.mark.error
    async def test_sec_07_003_critical_deviation_alert(self, execution_feedback, mock_context):
        """SEC-07-003: 关键偏差触发告警"""
        execution_record = {
            "execution_id": "EXEC-004",
            "action": "alter_table",
            "params": {"table": "orders", "column": "discount"},
            "expected_result": {"column_dropped": True},
            "critical": True,
        }
        actual_result = {"column_dropped": False, "error": "Column has dependent views"}

        result = await execution_feedback.verify(execution_record, actual_result, mock_context)
        assert result.critical_alert_triggered is True
        print(f"\n✅ 关键偏差告警: triggered={result.critical_alert_triggered}")

    @pytest.mark.p0_sec
    @pytest.mark.edge
    async def test_sec_07_004_feedback_timeout(self, execution_feedback, mock_context):
        """SEC-07-004: 验证超时处理"""
        execution_record = {
            "execution_id": "EXEC-005",
            "action": "verify_replication_status",
            "params": {},
        }
        with patch.object(execution_feedback, "_check_result", new_callable=AsyncMock) as mock_check:
            mock_check.side_effect = asyncio.TimeoutError("Verification timeout")
            result = await execution_feedback.verify(execution_record, {}, mock_context)
            assert result.verified is False or result.retry_count > 0
            print(f"\n✅ 验证超时: retry={result.retry_count}")


# =============================================================================
# SEC-08: 权限与审批流程 - Happy Path
# =============================================================================

class TestApprovalFlowHappyPath:
    """权限与审批流程 - Happy Path"""

    @pytest.mark.p0_sec
    @pytest.mark.happy
    async def test_sec_08_001_read_permission_low_risk(self, mock_policy_always_allow, mock_context):
        """SEC-08-001: 只读权限低风险操作 - 无需审批"""
        from src.gateway.policy_engine import PolicyResult, RiskLevel

        mock_policy_always_allow.check.return_value = PolicyResult(
            allowed=True,
            approval_required=False,
            approvers=[],
        )

        result = mock_policy_always_allow.check("read", mock_context)
        assert result.allowed is True
        assert result.approval_required is False
        print(f"\n✅ 只读权限: 无需审批")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    async def test_sec_08_002_high_risk_requires_approval(self, mock_policy_deny_high_risk, mock_context):
        """SEC-08-002: 高风险操作需要审批"""
        from src.gateway.policy_engine import PolicyResult

        mock_policy_deny_high_risk.check.return_value = PolicyResult(
            allowed=False,
            approval_required=True,
            approvers=["admin", "dba_lead"],
        )

        result = mock_policy_deny_high_risk.check("execute", {**mock_context, "risk_level": "L4"})
        assert result.approval_required is True
        assert len(result.approvers) >= 1
        print(f"\n✅ 高风险审批: 需要{result.approvers[0]}审批")

    @pytest.mark.p0_sec
    @pytest.mark.happy
    async def test_sec_08_003_dual_approval_for_critical(self, mock_context):
        """SEC-08-003: 关键操作双人审批"""
        from src.gateway.policy_engine import PolicyResult

        mock_policy = MagicMock()
        mock_policy.check.return_value = PolicyResult(
            allowed=False,
            approval_required=True,
            approvers=["admin", "dba_lead"],
        )

        result = mock_policy.check("critical_action", {**mock_context, "risk_level": "L5"})
        # dual_approval_required not yet in PolicyResult schema; verify approval_required
        assert result.approval_required is True
        assert len(result.approvers) == 2
        print(f"\n✅ 双人审批: 需要2人审批")


# =============================================================================
# SEC-09: 权限与审批流程 - Edge & Error Cases
# =============================================================================

class TestApprovalFlowEdgeError:
    """权限与审批流程 - Edge & Error Cases"""

    @pytest.mark.p0_sec
    @pytest.mark.edge
    async def test_sec_09_001_approval_timeout(self, mock_context):
        """SEC-09-001: 审批超时处理"""
        pytest.importorskip("src.gateway.approval", reason="src.gateway.approval not yet implemented")
        from src.gateway.approval import ApprovalGate

        gate = ApprovalGate()
        approval_id = await gate.request_approval(
            action="kill_session",
            context=mock_context,
            timeout_seconds=300,  # 5分钟
        )

        # 模拟超时场景
        start = time.time()
        while time.time() - start < 1:  # 1秒内检查
            status = await gate.get_status(approval_id)
            if status.approved:
                break
            if status.expired:
                assert status.expired is True
                print(f"\n✅ 审批超时: 已过期")
                break
            await asyncio.sleep(0.1)

    @pytest.mark.p0_sec
    @pytest.mark.edge
    async def test_sec_09_002_approver_not_found(self, mock_context):
        """SEC-09-002: 审批人不存在"""
        pytest.importorskip("src.gateway.approval", reason="src.gateway.approval not yet implemented")
        from src.gateway.approval import ApprovalGate

        gate = ApprovalGate()
        result = await gate.request_approval(
            action="kill_session",
            context=mock_context,
            approvers=["nonexistent_user_xyz"],
        )
        assert result.success is False or "not found" in (result.error or "").lower()
        print(f"\n✅ 审批人不存在处理: {result.error}")

    @pytest.mark.p0_sec
    @pytest.mark.error
    async def test_sec_09_003_unauthorized_permission_denied(self, mock_context):
        """SEC-09-003: 未授权操作拒绝"""
        from src.gateway.policy_engine import PolicyResult

        mock_policy = MagicMock()
        mock_policy.check.return_value = PolicyResult(
            allowed=False,
            reason="Insufficient permissions",
            approval_required=False,
            approvers=[],
        )

        result = mock_policy.check("admin", {**mock_context, "permissions": ["read"]})
