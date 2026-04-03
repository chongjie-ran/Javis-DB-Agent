"""
DFX Test Suite - Shared Fixtures
V2.6.1+V2.7 全面测试配置
"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

# ---------------------------------------------------------------------------
# Database fixtures (real PostgreSQL)
# ---------------------------------------------------------------------------

TEST_DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "zcloud_agent_test",
    "user": "zcloud_test",
    "password": "zcloud_test_pass"
}


@pytest.fixture
def temp_db_path():
    """临时 SQLite 数据库路径"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def real_pg_conn():
    """真实 PostgreSQL 连接（测试完成后自动关闭）"""
    try:
        import psycopg2
        conn = psycopg2.connect(**TEST_DB_CONFIG)
        yield conn
        conn.close()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")


# ---------------------------------------------------------------------------
# Session Manager fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session_manager_short_ttl(temp_db_path):
    """短TTL会话管理器（用于TTL过期测试）"""
    from src.gateway.persistent_session import PersistentSessionManager
    mgr = PersistentSessionManager(
        db_path=temp_db_path,
        ttl_seconds=2,  # 2秒TTL，用于快速测试
        max_sessions=50,
    )
    yield mgr
    mgr.cleanup_all()


@pytest.fixture
def session_manager_normal(temp_db_path):
    """正常TTL会话管理器"""
    from src.gateway.persistent_session import PersistentSessionManager
    mgr = PersistentSessionManager(
        db_path=temp_db_path,
        ttl_seconds=300,  # 5分钟
        max_sessions=100,
    )
    yield mgr
    mgr.cleanup_all()


# ---------------------------------------------------------------------------
# Approval Gate fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def approval_gate_short():
    """短超时审批门（用于超时测试）"""
    from src.gateway.approval import ApprovalGate
    gate = ApprovalGate(timeout_seconds=3)
    yield gate
    # cleanup
    for req in gate.list_pending():
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                gate.approve(req.request_id, "cleanup", "cleanup")
            )
        except:
            pass


@pytest.fixture
def approval_gate_normal():
    """正常超时审批门"""
    from src.gateway.approval import ApprovalGate
    gate = ApprovalGate(timeout_seconds=300)
    yield gate
    for req in gate.list_pending():
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                gate.approve(req.request_id, "cleanup", "cleanup")
            )
        except:
            pass


# ---------------------------------------------------------------------------
# Hook fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hook_registry():
    """干净的 Hook Registry"""
    import src.gateway.hooks.hook_registry as hr_module
    from src.gateway.hooks import HookRegistry, get_hook_registry
    hr_module._registry = None
    return get_hook_registry()


# ---------------------------------------------------------------------------
# Helper imports (must be after path setup)
# ---------------------------------------------------------------------------

def get_hook_registry():
    from src.gateway.hooks.hook_registry import get_hook_registry
    return get_hook_registry()
