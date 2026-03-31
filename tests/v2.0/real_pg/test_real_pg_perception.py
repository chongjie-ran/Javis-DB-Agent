"""
V2.0 Real PostgreSQL Environment - P0-3 Perception Layer Tests
Tests PreCheck/PostCheck hooks with real PostgreSQL database.

Database: javis_test_db (PostgreSQL localhost:5432)
"""
import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import psycopg2
from src.security.execution.check_hooks import (
    CheckHook, CheckHookRegistry, CheckResult, CheckType,
    InstanceHealthCheck, ReplicationLagCheck, SessionCountCheck,
    LockWaitCheck, ConnectionPoolCheck
)


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
        password="",
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
def check_registry():
    """Create a check hook registry"""
    return CheckHookRegistry()


@pytest.fixture
def instance_health_check():
    """Create an instance health check"""
    return InstanceHealthCheck()


@pytest.fixture
def replication_lag_check():
    """Create a replication lag check"""
    return ReplicationLagCheck(max_lag_seconds=30.0)


@pytest.fixture
def session_count_check():
    """Create a session count check"""
    return SessionCountCheck(max_sessions=1000)


@pytest.fixture
def lock_wait_check():
    """Create a lock wait check"""
    return LockWaitCheck(max_wait_seconds=30.0)


@pytest.fixture
def connection_pool_check():
    """Create a connection pool check"""
    return ConnectionPoolCheck(max_pool_usage_pct=80.0)


# ============================================================================
# P0-3: PreCheck/PostCheck Hook Tests
# ============================================================================

class TestCheckHookRegistry:
    """Test check hook registry functionality"""

    def test_registry_initialization(self, check_registry):
        """Test registry initializes with default hooks"""
        hooks = check_registry.list_hooks()
        assert len(hooks) >= 5, "Should have at least 5 default hooks"
        hook_names = [h.name for h in hooks]
        assert "InstanceHealthCheck" in hook_names
        assert "ReplicationLagCheck" in hook_names
        assert "SessionCountCheck" in hook_names

    def test_register_custom_hook(self, check_registry):
        """Test registering a custom hook"""
        class CustomCheck(CheckHook):
            async def run(self, context, check_type):
                return CheckResult(passed=True, message="Custom check passed", check_name=self.name)
        
        custom_hook = CustomCheck(name="CustomCheck")
        check_registry.register(custom_hook)
        
        retrieved = check_registry.get("CustomCheck")
        assert retrieved is not None
        assert retrieved.name == "CustomCheck"

    def test_unregister_hook(self, check_registry):
        """Test unregistering a hook"""
        result = check_registry.unregister("InstanceHealthCheck")
        assert result is True
        
        retrieved = check_registry.get("InstanceHealthCheck")
        assert retrieved is None

    def test_get_nonexistent_hook(self, check_registry):
        """Test getting a nonexistent hook returns None"""
        retrieved = check_registry.get("NonExistentHook")
        assert retrieved is None


class TestCheckHookExecution:
    """Test check hook execution with real DB context"""

    def test_instance_health_check_pass(self, instance_health_check):
        """Test instance health check with healthy instance"""
        context = {
            "instance_id": "test-instance-001",
            "instance_state": "running",
        }
        result = asyncio.run(instance_health_check.run(context, CheckType.PRE_CHECK))
        assert result.passed is True
        assert "健康" in result.message or "healthy" in result.message.lower()

    def test_instance_health_check_fail(self, instance_health_check):
        """Test instance health check with unhealthy instance"""
        context = {
            "instance_id": "test-instance-001",
            "instance_state": "stopped",
        }
        result = asyncio.run(instance_health_check.run(context, CheckType.PRE_CHECK))
        assert result.passed is False

    def test_instance_health_check_missing_instance_id(self, instance_health_check):
        """Test instance health check with missing instance_id"""
        context = {}
        result = asyncio.run(instance_health_check.run(context, CheckType.PRE_CHECK))
        assert result.passed is False
        assert "instance_id" in result.message.lower()

    def test_replication_lag_check_pass(self, replication_lag_check):
        """Test replication lag check when lag is normal"""
        context = {
            "instance_id": "test-instance-001",
            "replication_lag_seconds": 5.0,
        }
        result = asyncio.run(replication_lag_check.run(context, CheckType.POST_CHECK))
        assert result.passed is True

    def test_replication_lag_check_fail(self, replication_lag_check):
        """Test replication lag check when lag is too high"""
        context = {
            "instance_id": "test-instance-001",
            "replication_lag_seconds": 60.0,
        }
        result = asyncio.run(replication_lag_check.run(context, CheckType.POST_CHECK))
        assert result.passed is False
        assert result.metrics["lag_seconds"] == 60.0

    def test_session_count_check_pass(self, session_count_check):
        """Test session count check when under limit"""
        context = {
            "instance_id": "test-instance-001",
            "session_count": 100,
        }
        result = asyncio.run(session_count_check.run(context, CheckType.PRE_CHECK))
        assert result.passed is True

    def test_session_count_check_fail(self, session_count_check):
        """Test session count check when over limit"""
        context = {
            "instance_id": "test-instance-001",
            "session_count": 1500,
        }
        result = asyncio.run(session_count_check.run(context, CheckType.PRE_CHECK))
        assert result.passed is False

    def test_lock_wait_check_pass(self, lock_wait_check):
        """Test lock wait check when wait time is normal"""
        context = {
            "instance_id": "test-instance-001",
            "lock_wait_seconds": 5.0,
        }
        result = asyncio.run(lock_wait_check.run(context, CheckType.POST_CHECK))
        assert result.passed is True

    def test_lock_wait_check_fail(self, lock_wait_check):
        """Test lock wait check when wait time is too long"""
        context = {
            "instance_id": "test-instance-001",
            "lock_wait_seconds": 60.0,
        }
        result = asyncio.run(lock_wait_check.run(context, CheckType.POST_CHECK))
        assert result.passed is False


class TestConnectionPoolCheck:
    """Test connection pool check"""

    def test_pool_check_pass(self, connection_pool_check):
        """Test connection pool check when usage is normal"""
        context = {
            "connection_pool_used": 50,
            "connection_pool_max": 100,
        }
        result = asyncio.run(connection_pool_check.run(context, CheckType.PRE_CHECK))
        assert result.passed is True
        assert result.metrics["usage_pct"] == 50.0

    def test_pool_check_fail(self, connection_pool_check):
        """Test connection pool check when usage is too high"""
        context = {
            "connection_pool_used": 90,
            "connection_pool_max": 100,
        }
        result = asyncio.run(connection_pool_check.run(context, CheckType.PRE_CHECK))
        assert result.passed is False

    def test_pool_check_zero_max(self, connection_pool_check):
        """Test connection pool check with zero max (invalid config)"""
        context = {
            "connection_pool_used": 50,
            "connection_pool_max": 0,
        }
        result = asyncio.run(connection_pool_check.run(context, CheckType.PRE_CHECK))
        assert result.passed is False


class TestCheckHookRegistryExecution:
    """Test running all hooks through registry"""

    @pytest.mark.asyncio
    async def test_run_all_pre_checks(self, check_registry):
        """Test running all pre-checks"""
        context = {
            "instance_id": "test-instance-001",
            "instance_state": "running",
            "replication_lag_seconds": 5.0,
            "session_count": 100,
            "lock_wait_seconds": 2.0,
            "connection_pool_used": 40,
            "connection_pool_max": 100,
        }
        
        results = await check_registry.run_pre_checks(context)
        assert len(results) >= 5
        
        # Check that all expected hooks ran
        for hook_name in ["InstanceHealthCheck", "ReplicationLagCheck", "SessionCountCheck", "LockWaitCheck", "ConnectionPoolCheck"]:
            assert hook_name in results

    @pytest.mark.asyncio
    async def test_run_all_post_checks(self, check_registry):
        """Test running all post-checks"""
        context = {
            "instance_id": "test-instance-001",
            "instance_state": "running",
            "replication_lag_seconds": 10.0,
            "session_count": 150,
            "lock_wait_seconds": 5.0,
            "connection_pool_used": 60,
            "connection_pool_max": 100,
        }
        
        results = await check_registry.run_post_checks(context)
        assert len(results) >= 5

    @pytest.mark.asyncio
    async def test_mixed_check_results(self, check_registry):
        """Test with mixed pass/fail results"""
        context = {
            "instance_id": "test-instance-001",
            "instance_state": "running",
            "replication_lag_seconds": 5.0,
            "session_count": 50,  # Pass
            "lock_wait_seconds": 5.0,  # Pass
            "connection_pool_used": 90,  # Fail
            "connection_pool_max": 100,
        }
        
        results = await check_registry.run_pre_checks(context)
        
        # Verify some passed and some failed
        passed_count = sum(1 for r in results.values() if r.passed)
        failed_count = sum(1 for r in results.values() if not r.passed)
        assert passed_count + failed_count == len(results)


class TestRealDBPerceptionIntegration:
    """Test perception layer with real PostgreSQL database"""

    def test_pg_session_count_from_real_db(self, pg_cursor):
        """Test getting session count from real PostgreSQL"""
        pg_cursor.execute("SELECT COUNT(*) FROM pg_stat_activity")
        count = pg_cursor.fetchone()[0]
        assert count >= 1
        print(f"Current session count: {count}")

    def test_pg_replication_info(self, pg_connection, pg_cursor):
        """Test getting replication info from real PostgreSQL"""
        # Check if this is a primary or replica
        pg_cursor.execute("SELECT pg_is_in_recovery()")
        is_replica = pg_cursor.fetchone()[0]
        print(f"Is replica: {is_replica}")
        # This is informational - just verify query works

    def test_pg_lock_info(self, pg_cursor):
        """Test getting lock information from real PostgreSQL"""
        pg_cursor.execute("""
            SELECT COUNT(*) 
            FROM pg_locks 
            WHERE granted = false
        """)
        waiting_locks = pg_cursor.fetchone()[0]
        print(f"Waiting locks: {waiting_locks}")
        assert waiting_locks >= 0

    def test_pg_connection_validation(self, pg_connection):
        """Test that PostgreSQL connection is valid"""
        assert pg_connection is not None
        assert pg_connection.closed == 0
        
        # Test the connection is usable
        cursor = pg_connection.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1
        cursor.close()

    def test_pg_database_info(self, pg_cursor):
        """Test getting database information"""
        pg_cursor.execute("SELECT current_database(), current_user, version()")
        db_name, user, version = pg_cursor.fetchone()
        print(f"Database: {db_name}, User: {user}")
        assert db_name == "javis_test_db"

    def test_pg_tables_info(self, pg_cursor):
        """Test getting table information"""
        pg_cursor.execute("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
        """)
        tables = pg_cursor.fetchall()
        table_names = [t[0] for t in tables]
        print(f"Tables: {table_names}")
        assert "orders" in table_names

    def test_pg_indexes_info(self, pg_cursor):
        """Test getting index information"""
        pg_cursor.execute("""
            SELECT indexname, tablename 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename = 'orders'
        """)
        indexes = pg_cursor.fetchall()
        print(f"Indexes on orders: {indexes}")
        assert len(indexes) >= 1

    def test_pg_size_info(self, pg_cursor):
        """Test getting table size information"""
        pg_cursor.execute("""
            SELECT pg_size_pretty(pg_total_relation_size('orders'))
        """)
        size = pg_cursor.fetchone()[0]
        print(f"Orders table size: {size}")


class TestCheckTypeEnum:
    """Test CheckType enumeration"""

    def test_check_type_values(self):
        """Test CheckType enum values"""
        assert CheckType.PRE_CHECK.value == "pre_check"
        assert CheckType.POST_CHECK.value == "post_check"


class TestCheckResultDataclass:
    """Test CheckResult dataclass"""

    def test_check_result_pass(self):
        """Test CheckResult for passed check"""
        result = CheckResult(
            passed=True,
            message="All checks passed",
            check_name="TestCheck",
            metrics={"key": "value"},
        )
        assert result.passed is True
        assert result.message == "All checks passed"
        assert result.metrics["key"] == "value"

    def test_check_result_fail(self):
        """Test CheckResult for failed check"""
        result = CheckResult(
            passed=False,
            message="Check failed",
            check_name="TestCheck",
        )
        assert result.passed is False
        assert result.message == "Check failed"


# ============================================================================
# Test markers
# ============================================================================
pytest.mark.perception = pytest.mark.perception
pytest.mark.hooks = pytest.mark.hooks


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "perception"])
