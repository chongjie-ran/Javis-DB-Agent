"""
Test configuration and fixtures for Javis-DB-Agent
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(autouse=True)
def register_all_tools():
    """Register all tools before each test"""
    from src.gateway.tool_registry import get_tool_registry
    from src.tools.query_tools import register_query_tools
    from src.tools.analysis_tools import register_analysis_tools
    from src.tools.action_tools import register_action_tools
    from src.tools.backup_tools import register_backup_tools
    from src.tools.performance_tools import register_performance_tools
    
    registry = get_tool_registry()
    register_query_tools(registry)
    register_analysis_tools(registry)
    register_action_tools(registry)
    register_backup_tools(registry)
    register_performance_tools(registry)
    yield


@pytest.fixture(autouse=True)
def mock_policy_always_allow():
    """Mock policy engine to always allow in tests"""
    from src.gateway.policy_engine import PolicyResult, RiskLevel
    from src.agents.base import get_policy_engine
    mock_policy = MagicMock()
    mock_policy.check.return_value = PolicyResult(
        allowed=True,
        approval_required=False,
        approvers=[]
    )
    with patch("src.agents.base.get_policy_engine", return_value=mock_policy):
        yield

# Test database connection
TEST_DB_CONFIG = {
    "host": "/tmp",
    "port": 5432,
    "database": "zcloud_agent_test",
    "user": "zcloud_test",
    "password": "zcloud_test_pass"
}


@pytest.fixture
def mock_ollama_client():
    """Mock Ollama client for testing without LLM"""
    client = MagicMock()
    client.generate = AsyncMock(return_value={
        "response": "mocked_llm_response",
        "done": True
    })
    client.chat = AsyncMock(return_value={
        "message": {"content": "mocked_chat_response"},
        "done": True
    })
    return client


@pytest.fixture
def mock_javis_context():
    """Mock Javis-DB-Agent platform context"""
    return {
        "instance_id": "INS-TEST-001",
        "alert_id": "ALT-TEST-001",
        "user": "test_user",
        "session_id": "session-test-001",
        "permissions": ["read", "analyze"]
    }


@pytest.fixture
def mock_query_result():
    """Mock database query result"""
    return {
        "rows": [
            {"pid": 1234, "state": "active", "query": "SELECT * FROM test", "wait_event_type": "Lock"},
            {"pid": 5678, "state": "idle", "query": "INSERT INTO test VALUES (1)", "wait_event_type": None}
        ],
        "count": 2,
        "duration_ms": 15
    }


@pytest.fixture
def mock_alert_data():
    """Mock alert data"""
    return {
        "alert_id": "ALT-TEST-001",
        "alert_name": "锁等待超时",
        "severity": "warning",
        "instance_id": "INS-TEST-001",
        "triggered_at": "2026-03-28T10:00:00Z",
        "metrics": {
            "wait_time_ms": 5000,
            "blocked_sessions": 2
        }
    }


@pytest.fixture
def mock_diagnosis_result():
    """Mock diagnosis result"""
    return {
        "alert_type": "锁等待超时",
        "root_cause": "SQL-2026-001 长时间持有锁",
        "confidence": 0.85,
        "next_steps": [
            "查看会话详情",
            "分析阻塞链",
            "评估kill session风险"
        ]
    }


@pytest.fixture
def mock_risk_assessment():
    """Mock risk assessment"""
    return {
        "level": "L3",
        "can_auto_handle": False,
        "approval_required": True,
        "risk_items": [
            {"type": "data_consistency", "score": 0.8, "description": "中断事务可能导致数据不一致"}
        ]
    }


@pytest.fixture
def test_db_connection():
    """Create a test database connection"""
    import psycopg2
    conn = psycopg2.connect(**TEST_DB_CONFIG)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def reset_test_environment():
    """Reset environment before each test"""
    # Reset any global state
    os.environ["ZLOUD_ENV"] = "test"
    yield
    # Cleanup after test
    pass
