"""
V2.1 Round 2: V2.1 Bug修复验证测试
真显（测试者）编写

验证内容：
1. UNION注入Bug修复（union_count > union_all_count）
2. is_read_only()扩展（EXPLAIN/VACUUM/ANALYZE/EXPLAIN ANALYZE/SET）
3. 白名单正则改进（schema.table格式 + 带引号表名）
4. pg_explain正则（不强制要求FORMAT）

执行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/v2.0/test_v21_verification.py -v --tb=short
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from src.security.sql_guard import SQLGuard
from src.security.sql_guard.ast_parser import ASTParser


# ============================================================================
# V2.1 Bug修复验证 - UNION注入检测
# ============================================================================

class TestV21UNIONInjectionFix:
    """UNION注入Bug修复验证"""

    @pytest.fixture
    def guard(self):
        return SQLGuard()

    @pytest.fixture
    def ctx(self):
        return {"db_type": "postgresql", "instance_id": "test-v21"}

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_union_injection_blocked(self, guard, ctx):
        """UNION注入应被拒绝（不带ALL）"""
        sql = "SELECT 1 UNION SELECT password FROM users"
        result = await guard.validate(sql, ctx)
        assert result.allowed is False, \
            f"UNION注入应被拒绝，但allowed={result.allowed}, reason={result.blocked_reason}"
        assert "union" in (result.blocked_reason or "").lower()
        print(f"\n✅ UNION注入已拦截: {result.blocked_reason}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_union_all_allowed(self, guard, ctx):
        """UNION ALL应放行（安全）"""
        sql = "SELECT 1 UNION ALL SELECT 2 FROM users"
        result = await guard.validate(sql, ctx)
        # UNION ALL should be allowed (union_count == union_all_count)
        assert result.allowed is True or result.risk_level in ("L1", "L2"), \
            f"UNION ALL应放行，但allowed={result.allowed}, risk={result.risk_level}"
        print(f"\n✅ UNION ALL已放行: allowed={result.allowed}, risk={result.risk_level}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_union_multiple_blocked(self, guard, ctx):
        """多个UNION（无ALL）应被拒绝"""
        sql = "SELECT 1 UNION SELECT 2 UNION SELECT 3 FROM users"
        result = await guard.validate(sql, ctx)
        assert result.allowed is False, \
            f"多个UNION应被拒绝，但allowed={result.allowed}"
        print(f"\n✅ 多个UNION已拦截: {result.blocked_reason}")


# ============================================================================
# V2.1 Bug修复验证 - is_read_only()扩展
# ============================================================================

class TestV21ReadOnlyExtension:
    """is_read_only()扩展验证"""

    @pytest.fixture
    def parser(self):
        return ASTParser()

    @pytest.mark.v21
    @pytest.mark.pg
    def test_readonly_explain(self, parser):
        """EXPLAIN应识别为只读"""
        sql = "EXPLAIN SELECT * FROM orders"
        is_ro = parser.is_read_only(sql, "postgresql")
        assert is_ro is True, \
            f"EXPLAIN应识别为只读，但is_read_only={is_ro}"
        print(f"\n✅ EXPLAIN识别为只读: {is_ro}")

    @pytest.mark.v21
    @pytest.mark.pg
    def test_readonly_vacuum(self, parser):
        """VACUUM应识别为只读"""
        sql = "VACUUM orders"
        is_ro = parser.is_read_only(sql, "postgresql")
        assert is_ro is True, \
            f"VACUUM应识别为只读，但is_read_only={is_ro}"
        print(f"\n✅ VACUUM识别为只读: {is_ro}")

    @pytest.mark.v21
    @pytest.mark.pg
    def test_readonly_analyze(self, parser):
        """ANALYZE应识别为只读"""
        sql = "ANALYZE orders"
        is_ro = parser.is_read_only(sql, "postgresql")
        assert is_ro is True, \
            f"ANALYZE应识别为只读，但is_read_only={is_ro}"
        print(f"\n✅ ANALYZE识别为只读: {is_ro}")

    @pytest.mark.v21
    @pytest.mark.pg
    def test_readonly_explain_analyze_not(self, parser):
        """EXPLAIN ANALYZE不应识别为只读（实际执行）"""
        sql = "EXPLAIN ANALYZE SELECT * FROM orders"
        is_ro = parser.is_read_only(sql, "postgresql")
        assert is_ro is False, \
            f"EXPLAIN ANALYZE不应识别为只读，但is_read_only={is_ro}"
        print(f"\n✅ EXPLAIN ANALYZE识别为非只读: {is_ro}")

    @pytest.mark.v21
    @pytest.mark.pg
    def test_readonly_set_not(self, parser):
        """SET命令不应识别为只读"""
        sql = "SET work_mem = '256MB'"
        is_ro = parser.is_read_only(sql, "postgresql")
        assert is_ro is False, \
            f"SET命令不应识别为只读，但is_read_only={is_ro}"
        print(f"\n✅ SET识别为非只读: {is_ro}")


# ============================================================================
# V2.1 Bug修复验证 - 白名单正则改进
# ============================================================================

class TestV21WhitelistRegexImprovement:
    """白名单正则改进验证"""

    @pytest.fixture
    def guard(self):
        return SQLGuard()

    @pytest.fixture
    def ctx(self):
        return {"db_type": "postgresql", "instance_id": "test-v21"}

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_whitelist_schema_table(self, guard, ctx):
        """schema.table格式应匹配白名单"""
        sql = "SELECT * FROM public.orders"
        result = await guard.validate(sql, ctx)
        assert result.allowed is True, \
            f"schema.table格式应匹配白名单，但allowed={result.allowed}, reason={result.blocked_reason}"
        print(f"\n✅ schema.table格式匹配白名单: allowed={result.allowed}, risk={result.risk_level}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_whitelist_quoted_table(self, guard, ctx):
        """带引号表名应匹配白名单"""
        sql = 'SELECT * FROM "User"'
        result = await guard.validate(sql, ctx)
        assert result.allowed is True, \
            f"带引号表名应匹配白名单，但allowed={result.allowed}, reason={result.blocked_reason}"
        print(f"\n✅ 带引号表名匹配白名单: allowed={result.allowed}, risk={result.risk_level}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_whitelist_schema_table_with_where(self, guard, ctx):
        """schema.table带WHERE应匹配白名单"""
        sql = "SELECT * FROM schema.table WHERE id = 1"
        result = await guard.validate(sql, ctx)
        assert result.allowed is True, \
            f"schema.table带WHERE应匹配白名单，但allowed={result.allowed}, reason={result.blocked_reason}"
        print(f"\n✅ schema.table带WHERE匹配白名单: allowed={result.allowed}, risk={result.risk_level}")


# ============================================================================
# V2.1 Bug修复验证 - pg_explain正则
# ============================================================================

class TestV21PgExplainRegex:
    """pg_explain正则验证（不强制要求FORMAT）"""

    @pytest.fixture
    def guard(self):
        return SQLGuard()

    @pytest.fixture
    def ctx(self):
        return {"db_type": "postgresql", "instance_id": "test-v21"}

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_pg_explain_no_format(self, guard, ctx):
        """EXPLAIN不带FORMAT选项应匹配pg_explain白名单"""
        sql = "EXPLAIN SELECT * FROM orders"
        result = await guard.validate(sql, ctx)
        assert result.allowed is True, \
            f"EXPLAIN应匹配pg_explain白名单，但allowed={result.allowed}, reason={result.blocked_reason}"
        print(f"\n✅ EXPLAIN匹配pg_explain白名单: allowed={result.allowed}, risk={result.risk_level}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_pg_explain_with_analyze(self, guard, ctx):
        """EXPLAIN (ANALYZE)应匹配pg_explain白名单"""
        sql = "EXPLAIN (ANALYZE) SELECT * FROM orders"
        result = await guard.validate(sql, ctx)
        assert result.allowed is True, \
            f"EXPLAIN (ANALYZE)应匹配pg_explain白名单，但allowed={result.allowed}, reason={result.blocked_reason}"
        print(f"\n✅ EXPLAIN (ANALYZE)匹配白名单: allowed={result.allowed}, risk={result.risk_level}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_pg_explain_with_format_json(self, guard, ctx):
        """EXPLAIN (FORMAT JSON)应匹配pg_explain白名单"""
        sql = "EXPLAIN (FORMAT JSON) SELECT * FROM orders"
        result = await guard.validate(sql, ctx)
        assert result.allowed is True, \
            f"EXPLAIN (FORMAT JSON)应匹配pg_explain白名单，但allowed={result.allowed}, reason={result.blocked_reason}"
        print(f"\n✅ EXPLAIN (FORMAT JSON)匹配白名单: allowed={result.allowed}, risk={result.risk_level}")


# ============================================================================
# 回归测试：确保修复不破坏现有功能
# ============================================================================

class TestV21Regression:
    """回归测试：确保UNION修复不破坏现有功能"""

    @pytest.fixture
    def guard(self):
        return SQLGuard()

    @pytest.fixture
    def ctx(self):
        return {"db_type": "postgresql", "instance_id": "test-v21"}

    @pytest.fixture
    def ctx_mysql(self):
        return {"db_type": "mysql", "instance_id": "test-v21-mysql"}

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_regression_safe_select_still_allowed(self, guard, ctx):
        """回归：安全SELECT仍应放行"""
        sql = "SELECT id, name FROM users WHERE status = 1"
        result = await guard.validate(sql, ctx)
        assert result.allowed is True, f"安全SELECT应放行，但被拒绝: {result.blocked_reason}"
        print(f"\n✅ 回归-安全SELECT: allowed={result.allowed}, risk={result.risk_level}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_regression_truncate_still_blocked(self, guard, ctx):
        """回归：TRUNCATE仍应拒绝"""
        sql = "TRUNCATE TABLE users"
        result = await guard.validate(sql, ctx)
        assert result.allowed is False, "TRUNCATE应被拒绝"
        print(f"\n✅ 回归-TRUNCATE拦截: {result.blocked_reason}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_regression_drop_blocked(self, guard, ctx):
        """回归：DROP TABLE仍应拒绝"""
        sql = "DROP TABLE users"
        result = await guard.validate(sql, ctx)
        assert result.allowed is False, "DROP TABLE应被拒绝"
        print(f"\n✅ 回归-DROP拦截: {result.blocked_reason}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_regression_delete_no_where_blocked(self, guard, ctx):
        """回归：无WHERE的DELETE仍应拒绝"""
        sql = "DELETE FROM users"
        result = await guard.validate(sql, ctx)
        assert result.allowed is False, "无WHERE的DELETE应被拒绝"
        print(f"\n✅ 回归-无WHERE_DELETE拦截: {result.blocked_reason}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_regression_union_cte_safe(self, guard, ctx):
        """回归：CTE中的UNION ALL应安全"""
        sql = """
            WITH RECURSIVE cnt(x) AS (
                SELECT 1
                UNION ALL
                SELECT x+1 FROM cnt WHERE x < 100
            )
            SELECT x FROM cnt
        """
        result = await guard.validate(sql, ctx)
        # CTE with UNION ALL in recursive context is allowed
        assert result.allowed is True or result.risk_level in ("L1", "L2"), \
            f"CTE中UNION ALL应放行，但allowed={result.allowed}"
        print(f"\n✅ 回归-CTE_UNION_ALL: allowed={result.allowed}, risk={result.risk_level}")

    @pytest.mark.v21
    @pytest.mark.mysql
    @pytest.mark.asyncio
    async def test_regression_mysql_union_injection_blocked(self, guard, ctx_mysql):
        """回归：MySQL UNION注入也需拦截"""
        sql = "SELECT * FROM users UNION SELECT password FROM users"
        result = await guard.validate(sql, ctx_mysql)
        assert result.allowed is False, \
            f"MySQL UNION注入应被拒绝，但allowed={result.allowed}"
        print(f"\n✅ 回归-MySQL_UNION拦截: {result.blocked_reason}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_regression_pg_terminate_blocked(self, guard, ctx):
        """回归：pg_terminate_backend仍应拒绝"""
        sql = "SELECT pg_terminate_backend(1234)"
        result = await guard.validate(sql, ctx)
        assert result.allowed is False, "pg_terminate_backend应被拒绝"
        print(f"\n✅ 回归-pg_terminate拦截: {result.blocked_reason}")

    @pytest.mark.v21
    @pytest.mark.pg
    @pytest.mark.asyncio
    async def test_regression_explain_analyze_not_readonly(self, guard, ctx):
        """回归：EXPLAIN ANALYZE不应是只读（实际执行）"""
        sql = "EXPLAIN ANALYZE SELECT * FROM orders"
        result = await guard.validate(sql, ctx)
        # Should NOT be L1 (readonly) since EXPLAIN ANALYZE actually executes
        assert result.risk_level != "L1" or result.allowed is False, \
            f"EXPLAIN ANALYZE不应是L1只读，但risk={result.risk_level}, allowed={result.allowed}"
        print(f"\n✅ 回归-EXPLAIN_ANALYZE非只读: risk={result.risk_level}, allowed={result.allowed}")
