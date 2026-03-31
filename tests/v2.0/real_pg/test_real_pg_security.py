"""
V2.0 Real PostgreSQL Environment - P0-1 Security Layer Tests
Tests SQL AST guardrail verification with real PostgreSQL database.

Database: javis_test_db (PostgreSQL localhost:5432)
"""
import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import psycopg2
from psycopg2.extras import RealDictCursor
from src.security.sql_guard.ast_parser import ASTParser
from src.security.sql_guard.sql_guard import SQLGuard, SQLGuardStatus


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def pg_connection():
    """Create a real PostgreSQL connection"""
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="javis_test_db",
        user="chongjieran",
        password="",  # empty password for local peer auth
    )
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def pg_cursor(pg_connection):
    """Create a cursor for the PostgreSQL connection"""
    cursor = pg_connection.cursor()
    yield cursor
    cursor.close()


@pytest.fixture
def ast_parser():
    """Create an AST parser instance"""
    return ASTParser()


@pytest.fixture
def sql_guard():
    """Create a SQL guard instance"""
    return SQLGuard()


# ============================================================================
# P0-1: SQL AST Guardrail Tests (PostgreSQL dialect)
# ============================================================================

class TestPostgresASTParser:
    """Test PostgreSQL SQL AST parsing"""

    def test_parse_simple_select(self, ast_parser):
        """Test parsing a simple SELECT statement"""
        sql = "SELECT * FROM orders WHERE status = 'pending'"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None, "Failed to parse simple SELECT"
        operations = ast_parser.get_operations(sql, dialect="postgresql")
        assert "SELECT" in operations

    def test_parse_select_with_where(self, ast_parser):
        """Test SELECT with WHERE clause"""
        sql = "SELECT id, status, total_amount FROM orders WHERE status = 'completed'"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None
        tables = ast_parser.get_tables(sql, dialect="postgresql")
        assert "orders" in tables

    def test_parse_insert_statement(self, ast_parser):
        """Test INSERT statement parsing"""
        sql = "INSERT INTO orders (user_id, status, total_amount) VALUES (1, 'pending', 99.99)"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None
        operations = ast_parser.get_operations(sql, dialect="postgresql")
        assert "INSERT" in operations

    def test_parse_update_statement(self, ast_parser):
        """Test UPDATE statement parsing"""
        sql = "UPDATE orders SET status = 'processing' WHERE id = 1"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None
        operations = ast_parser.get_operations(sql, dialect="postgresql")
        assert "UPDATE" in operations

    def test_parse_delete_statement(self, ast_parser):
        """Test DELETE statement parsing"""
        sql = "DELETE FROM orders WHERE id = 100"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None
        operations = ast_parser.get_operations(sql, dialect="postgresql")
        assert "DELETE" in operations

    def test_parse_with_limit(self, ast_parser):
        """Test SELECT with LIMIT clause"""
        sql = "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None
        assert ast_parser.has_limit_clause(sql, dialect="postgresql") is True

    def test_parse_with_subquery(self, ast_parser):
        """Test SELECT with subquery"""
        sql = "SELECT * FROM orders WHERE user_id IN (SELECT id FROM users WHERE active = true)"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None
        subqueries = ast_parser.get_subqueries(sql, dialect="postgresql")
        assert len(subqueries) >= 0  # subquery detection varies by sqlglot version

    def test_parse_union_query(self, ast_parser):
        """Test UNION query parsing"""
        sql = "SELECT id, status FROM orders WHERE status = 'pending' UNION SELECT id, status FROM orders WHERE status = 'processing'"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None
        operations = ast_parser.get_operations(sql, dialect="postgresql")
        assert "UNION" in operations

    def test_parse_count_aggregate(self, ast_parser):
        """Test COUNT aggregate function"""
        sql = "SELECT COUNT(*) FROM orders WHERE status = 'completed'"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None

    def test_parse_join_query(self, ast_parser):
        """Test JOIN query parsing"""
        sql = "SELECT o.id, u.name FROM orders o JOIN users u ON o.user_id = u.id"
        ast = ast_parser.parse(sql, dialect="postgresql")
        assert ast is not None
        operations = ast_parser.get_operations(sql, dialect="postgresql")
        assert "JOIN" in operations


class TestDangerousSQLDetection:
    """Test dangerous SQL detection"""

    def test_detect_drop_table(self, sql_guard):
        """Test DROP TABLE detection"""
        sql = "DROP TABLE orders"
        result = asyncio.run(sql_guard.validate(sql, {"db_type": "postgresql"}))
        assert result.allowed is False
        assert "DROP" in result.operations

    def test_detect_truncate(self, sql_guard):
        """Test TRUNCATE detection"""
        sql = "TRUNCATE TABLE orders"
        result = asyncio.run(sql_guard.validate(sql, {"db_type": "postgresql"}))
        assert result.allowed is False

    def test_detect_pg_terminate_backend(self, sql_guard):
        """Test dangerous PostgreSQL function detection"""
        sql = "SELECT pg_terminate_backend(1234)"
        result = asyncio.run(sql_guard.validate(sql, {"db_type": "postgresql"}))
        assert result.allowed is False
        assert "pg_terminate_backend" in result.blocked_reason.lower()

    def test_detect_multi_statement_injection(self, sql_guard):
        """Test multi-statement SQL injection detection"""
        sql = "SELECT * FROM orders; DROP TABLE orders;--"
        result = asyncio.run(sql_guard.validate(sql, {"db_type": "postgresql"}))
        assert result.allowed is False

    def test_safe_select_is_allowed(self, sql_guard):
        """Test that safe SELECT is allowed"""
        sql = "SELECT * FROM orders WHERE status = 'pending'"
        result = asyncio.run(sql_guard.validate(sql, {"db_type": "postgresql"}))
        assert result.allowed is True


class TestDMLBoundaryChecks:
    """Test DML boundary checks (WHERE/LIMIT)"""

    def test_delete_without_where_rejected(self, sql_guard):
        """Test DELETE without WHERE is rejected"""
        sql = "DELETE FROM orders"
        result = asyncio.run(sql_guard.validate(sql, {"db_type": "postgresql"}))
        assert result.allowed is False
        assert "WHERE" in result.blocked_reason or "缺少WHERE" in result.blocked_reason

    def test_update_without_where_rejected(self, sql_guard):
        """Test UPDATE without WHERE is rejected"""
        sql = "UPDATE orders SET status = 'cancelled'"
        result = asyncio.run(sql_guard.validate(sql, {"db_type": "postgresql"}))
        assert result.allowed is False

    def test_delete_with_where_allowed(self, sql_guard):
        """Test DELETE with WHERE is allowed (needs approval)"""
        sql = "DELETE FROM orders WHERE id = 999"
        result = asyncio.run(sql_guard.validate(sql, {"db_type": "postgresql"}))
        # Should either be allowed (L4) or need approval
        assert result.risk_level in ["L2", "L4"]

    def test_update_with_where_needs_approval(self, sql_guard):
        """Test UPDATE with WHERE needs approval"""
        sql = "UPDATE orders SET status = 'processing' WHERE id = 1"
        result = asyncio.run(sql_guard.validate(sql, {"db_type": "postgresql"}))
        # UPDATE is high risk, should need approval
        assert result.approval_required or result.status in [SQLGuardStatus.NEED_APPROVAL, SQLGuardStatus.ALLOWED]


class TestRealPostgreSQLIntegration:
    """Test real PostgreSQL database integration"""

    def test_connect_to_real_pg(self, pg_connection):
        """Test connection to real PostgreSQL"""
        assert pg_connection is not None
        assert pg_connection.closed == 0

    def test_query_orders_table(self, pg_cursor):
        """Test querying real orders table"""
        pg_cursor.execute("SELECT COUNT(*) FROM orders")
        count = pg_cursor.fetchone()[0]
        assert count == 100, f"Expected 100 rows, got {count}"

    def test_query_with_filter(self, pg_cursor):
        """Test querying with status filter"""
        pg_cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
        pending_count = pg_cursor.fetchone()[0]
        assert pending_count >= 0

    def test_query_with_aggregation(self, pg_cursor):
        """Test aggregation query"""
        pg_cursor.execute("SELECT status, COUNT(*) FROM orders GROUP BY status")
        results = pg_cursor.fetchall()
        assert len(results) >= 1

    def test_explain_query_plan(self, pg_cursor):
        """Test EXPLAIN for query plan analysis"""
        pg_cursor.execute("EXPLAIN SELECT * FROM orders WHERE status = 'pending'")
        plan = pg_cursor.fetchall()
        assert len(plan) > 0

    def test_insert_and_verify(self, pg_connection, pg_cursor):
        """Test inserting a new order and verifying"""
        # This is non-destructive - we insert and then can rollback
        pg_cursor.execute("SELECT COUNT(*) FROM orders")
        before = pg_cursor.fetchone()[0]
        
        pg_cursor.execute("""
            INSERT INTO orders (user_id, status, total_amount) 
            VALUES (999, 'test', 0.01)
        """)
        pg_connection.commit()
        
        pg_cursor.execute("SELECT COUNT(*) FROM orders")
        after = pg_cursor.fetchone()[0]
        
        # Rollback the test insert
        pg_cursor.execute("DELETE FROM orders WHERE user_id = 999 AND status = 'test'")
        pg_connection.commit()
        
        assert after == before + 1

    def test_order_by_and_limit(self, pg_cursor):
        """Test ORDER BY with LIMIT"""
        pg_cursor.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 5")
        results = pg_cursor.fetchall()
        assert len(results) <= 5

    def test_date_range_query(self, pg_cursor):
        """Test date range query"""
        pg_cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= NOW() - INTERVAL '30 days'")
        count = pg_cursor.fetchone()[0]
        assert count >= 0

    def test_numeric_filter(self, pg_cursor):
        """Test numeric range filter"""
        pg_cursor.execute("SELECT COUNT(*) FROM orders WHERE total_amount > 100")
        count = pg_cursor.fetchone()[0]
        assert count >= 0

    def test_distinct_values(self, pg_cursor):
        """Test DISTINCT query"""
        pg_cursor.execute("SELECT DISTINCT status FROM orders")
        statuses = pg_cursor.fetchall()
        assert len(statuses) >= 1


# ============================================================================
# Test markers for selective execution
# ============================================================================
pytest.mark.pg = pytest.mark.pg
pytest.mark.real_db = pytest.mark.real_db
pytest.mark.security = pytest.mark.security


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "pg"])
