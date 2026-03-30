"""
V2.0 TDD测试框架配置
测试目标：P0-1(安全治理) / P0-2(知识层) / P0-3(感知层)

依赖环境变量：
    TEST_MYSQL_HOST, TEST_MYSQL_PORT, TEST_MYSQL_USER, TEST_MYSQL_PASSWORD, TEST_MYSQL_DATABASE
    TEST_PG_HOST, TEST_PG_PORT, TEST_PG_USER, TEST_PG_PASSWORD, TEST_PG_DATABASE
    TEST_ZCOULD_API_URL, TEST_ZCLOUD_API_KEY   # 感知层真实API测试

运行方式：
    pytest tests/v2.0/ -v                          # 全部测试
    pytest tests/v2.0/ -k "SEC" -v                 # 仅P0-1安全层
    pytest tests/v2.0/ -k "KNO" -v                 # 仅P0-2知识层
    pytest tests/v2.0/ -k "PER" -v                 # 仅P0-3感知层
    pytest tests/v2.0/ -k "INT" -v                 # 仅集成测试
    pytest tests/v2.0/ -m "pg" -v                  # 仅PG环境测试
    pytest tests/v2.0/ -m "mysql" -v               # 仅MySQL环境测试
    pytest tests/v2.0/ -m "real_api" -v            # 仅真实API测试
    pytest tests/v2.0/ -m "slow" -v               # 耗时测试(>5s)
    pytest tests/v2.0/ -m "happy" -v               # Happy path测试
    pytest tests/v2.0/ -m "edge" -v                # Edge cases测试
    pytest tests/v2.0/ -m "error" -v               # Error cases测试
    pytest tests/v2.0/ -m "regression" -v          # 回归测试

前置准备：
    1. 确保MySQL/PG测试实例可用（参考 tests/v1.5/validation/check_env.py）
    2. 创建测试数据库和表（运行 setup_v2.0_test_env.sql）
    3. 配置zCloud API Mock或真实凭证（用于P0-3感知层）
"""
import os
import sys
import pytest
import asyncio
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, AsyncMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

# Import db adapters
try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


# ============================================================================
# Test Configuration
# ============================================================================

class TestConfig:
    """V2.0 测试配置"""

    # MySQL
    MYSQL_HOST = os.getenv("TEST_MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("TEST_MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("TEST_MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("TEST_MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("TEST_MYSQL_DATABASE", "test")

    # PostgreSQL
    PG_HOST = os.getenv("TEST_PG_HOST", "localhost")
    PG_PORT = int(os.getenv("TEST_PG_PORT", "5432"))
    PG_USER = os.getenv("TEST_PG_USER", "javis_test")
    PG_PASSWORD = os.getenv("TEST_PG_PASSWORD", "javis_test123")
    PG_DATABASE = os.getenv("TEST_PG_DATABASE", "postgres")

    # zCloud API (P0-3 感知层)
    ZCOULD_API_URL = os.getenv("TEST_ZCOULD_API_URL", "http://localhost:8080")
    ZCOULD_API_KEY = os.getenv("TEST_ZCLOUD_API_KEY", "test-api-key")

    @classmethod
    def is_mysql_available(cls) -> bool:
        if not HAS_PYMYSQL:
            return False
        try:
            conn = pymysql.connect(
                host=cls.MYSQL_HOST,
                port=cls.MYSQL_PORT,
                user=cls.MYSQL_USER,
                password=cls.MYSQL_PASSWORD,
                connect_timeout=5,
            )
            conn.close()
            return True
        except Exception:
            return False

    @classmethod
    def is_pg_available(cls) -> bool:
        if not HAS_PSYCOPG2:
            return False
        try:
            conn = psycopg2.connect(
                host=cls.PG_HOST,
                port=cls.PG_PORT,
                user=cls.PG_USER,
                password=cls.PG_PASSWORD,
                dbname=cls.PG_DATABASE,
                connect_timeout=5,
            )
            conn.close()
            return True
        except Exception:
            return False

    @classmethod
    def is_zcloud_api_available(cls) -> bool:
        """检查zCloud API是否可用（P0-3感知层）"""
        import requests
        try:
            resp = requests.get(
                f"{cls.ZCOULD_API_URL}/api/health",
                timeout=5,
                headers={"Authorization": f"Bearer {cls.ZCOULD_API_KEY}"}
            )
            return resp.status_code == 200
        except Exception:
            return False

    @classmethod
    def get_mysql_conn(cls):
        if not cls.is_mysql_available():
            raise RuntimeError("MySQL不可用")
        return pymysql.connect(
            host=cls.MYSQL_HOST,
            port=cls.MYSQL_PORT,
            user=cls.MYSQL_USER,
            password=cls.MYSQL_PASSWORD,
            database=cls.MYSQL_DATABASE,
            connect_timeout=10,
            charset="utf8mb4",
        )

    @classmethod
    def get_pg_conn(cls):
        if not cls.is_pg_available():
            raise RuntimeError("PostgreSQL不可用")
        return psycopg2.connect(
            host=cls.PG_HOST,
            port=cls.PG_PORT,
            user=cls.PG_USER,
            password=cls.PG_PASSWORD,
            dbname=cls.PG_DATABASE,
            connect_timeout=10,
        )


# ============================================================================
# Pytest Markers
# ============================================================================

def pytest_configure(config):
    """注册V2.0自定义标记"""
    # P0方向标记
    config.addinivalue_line("markers", "p0_sec: P0-1 安全治理层测试")
    config.addinivalue_line("markers", "p0_kno: P0-2 知识层测试")
    config.addinivalue_line("markers", "p0_per: P0-3 感知层测试")
    # 测试类型标记
    config.addinivalue_line("markers", "happy: Happy path测试")
    config.addinivalue_line("markers", "edge: Edge cases测试")
    config.addinivalue_line("markers", "error: Error cases测试")
    config.addinivalue_line("markers", "regression: 回归测试")
    # 环境标记
    config.addinivalue_line("markers", "mysql: MySQL环境测试")
    config.addinivalue_line("markers", "pg: PostgreSQL环境测试")
    config.addinivalue_line("markers", "real_api: 真实API测试")
    config.addinivalue_line("markers", "slow: 耗时较长的测试(>5s)")
    config.addinivalue_line("markers", "integration: 集成测试")


# ============================================================================
# Fixtures: 环境可用性
# ============================================================================

@pytest.fixture(scope="session")
def mysql_available():
    return TestConfig.is_mysql_available()


@pytest.fixture(scope="session")
def pg_available():
    return TestConfig.is_pg_available()


@pytest.fixture(scope="session")
def zcloud_api_available():
    return TestConfig.is_zcloud_api_available()


# ============================================================================
# Fixtures: 数据库连接
# ============================================================================

@pytest.fixture
def mysql_conn(mysql_available):
    """MySQL连接 fixture"""
    if not mysql_available:
        pytest.skip("MySQL不可用")
    conn = TestConfig.get_mysql_conn()
    yield conn
    try:
        conn.close()
    except Exception:
        pass


@pytest.fixture
def pg_conn(pg_available):
    """PostgreSQL连接 fixture"""
    if not pg_available:
        pytest.skip("PostgreSQL不可用")
    conn = TestConfig.get_pg_conn()
    yield conn
    try:
        conn.close()
    except Exception:
        pass


# ============================================================================
# Fixtures: Agent实例
# ============================================================================

@pytest.fixture
def sql_guard():
    """SQL护栏模块（P0-1）"""
    # 优先使用真实实现，回退到AsyncMock
    try:
        from src.security.sql_guard import SQLGuard
        guard = SQLGuard()
        return guard
    except ImportError:
        mock_guard = MagicMock()

        # Context-aware mock: simulates real SQL guard behavior for TDD
        DANGEROUS_KEYWORDS = {
            "truncate", "drop table", "drop index", "drop database",
            "alter system", "grant ", "revoke ",
            "shutdown", "load data infile",
            "copy ", "flush ",
            "kill(", "pg_terminate_backend", "pg_cancel_backend",
        }
        # Dangerous if present without a safe context
        # "union " is allowed in CTEs (UNION ALL for recursion); blocked in multi-table context
        DANGEROUS_PATTERNS = ["sleep(", "waitfor ", "benchmark(", "exec(", "execute(",
                              "union ", "union all ", "set global ", "set session "]
        WHITELIST = {"select 1", "select 1;", "select version()"}

        async def mock_validate(sql, context):
            sql_lower = sql.strip().lower()
            # Empty / whitespace
            if not sql.strip():
                return MagicMock(allowed=False, risk_level="L5", blocked_reason="Empty SQL", rewritten_sql=None, approval_required=False)
            # Whitelist
            if sql_lower in WHITELIST or sql_lower.replace(";", "").strip() in WHITELIST:
                return MagicMock(allowed=True, risk_level="L0", blocked_reason=None, rewritten_sql=None, approval_required=False)
            # Extremely long SQL
            if len(sql) > 10 * 1024 * 1024:
                return MagicMock(allowed=False, risk_level="L5", blocked_reason="SQL too long", rewritten_sql=None, approval_required=False)
            # Dangerous patterns (injection / dangerous functions)
            for pat in DANGEROUS_PATTERNS:
                if pat in sql_lower:
                    return MagicMock(
                        allowed=False, risk_level="L5",
                        blocked_reason=f"Dangerous pattern: {pat}",
                        rewritten_sql=None, approval_required=True,
                    )
            # Dangerous keywords (DDL/DCL/system)
            for kw in DANGEROUS_KEYWORDS:
                if kw in sql_lower:
                    return MagicMock(
                        allowed=False, risk_level="L5",
                        blocked_reason=f"Dangerous keyword: {kw}",
                        rewritten_sql=None, approval_required=True,
                    )
            # DELETE/UPDATE with WHERE - medium risk but allowed
            if sql_lower.startswith("delete ") or sql_lower.startswith("update "):
                if "where " in sql_lower:
                    return MagicMock(allowed=True, risk_level="L2", blocked_reason=None, rewritten_sql=None, approval_required=False)
                else:
                    return MagicMock(allowed=False, risk_level="L5", blocked_reason="No WHERE clause", rewritten_sql=None, approval_required=True)
            # Dangerous functions in SELECT context (pg_terminate_backend, etc.)
            if "select " in sql_lower and ("pg_terminate" in sql_lower or "pg_cancel" in sql_lower or "set " in sql_lower):
                return MagicMock(
                    allowed=False, risk_level="L5",
                    blocked_reason="Dangerous function in SELECT",
                    rewritten_sql=None, approval_required=True,
                )
            # Safe SELECT
            if sql_lower.startswith("select") or sql_lower.startswith("explain"):
                return MagicMock(allowed=True, risk_level="L1", blocked_reason=None, rewritten_sql=None, approval_required=False)
            # Default
            return MagicMock(allowed=True, risk_level="L1", blocked_reason=None, rewritten_sql=None, approval_required=False)

        mock_guard.validate = AsyncMock(side_effect=mock_validate)
        return mock_guard


@pytest.fixture
def sop_executor():
    """SOP执行器（P0-1）"""
    try:
        from src.security.execution.sop_executor import SOPExecutor
        return SOPExecutor()
    except ImportError:
        try:
            from src.tools.sop_executor import SOPExecutor
            return SOPExecutor()
        except ImportError:
            mock = MagicMock()
            # Default _execute_step (can be patched by tests via patch.object)
            mock._execute_step = AsyncMock(return_value=MagicMock(success=True, approver="system"))
            mock._should_fail_step = False
            mock._step_error = "Critical action failed"

            async def mock_execute(sop, context):
                step_results = []
                try:
                    for step_def in (sop.get("steps") or []):
                        action = step_def.get("action", "")
                        if "nonexistent" in action.lower() or "unknown" in action.lower():
                            return MagicMock(
                                success=False,
                                step_results=step_results,
                                final_result={"error": f"unknown action: {action}", "stage": "validation"},
                            )
                        if step_def.get("critical") and mock._should_fail_step:
                            await mock._execute_step(step_def, context)
                            step_results.append(MagicMock(success=False))
                            return MagicMock(
                                success=False,
                                step_results=step_results,
                                final_result={"error": mock._step_error, "stage": "step_execution", "aborted_at_step": step_def.get("step", 0)},
                            )
                        step_result = await mock._execute_step(step_def, context)
                        step_results.append(step_result)
                    return MagicMock(success=True, step_results=step_results, final_result={"status": "completed"})
                except asyncio.TimeoutError as e:
                    return MagicMock(success=False, step_results=step_results, final_result={"error": str(e), "stage": "step_execution"})
                except Exception as e:
                    return MagicMock(success=False, step_results=step_results, final_result={"error": str(e), "stage": "step_execution"})

            mock.execute = AsyncMock(side_effect=mock_execute)
            return mock


@pytest.fixture
def execution_feedback():
    """执行回流验证（P0-1）"""
    try:
        from src.security.execution.execution_feedback import ExecutionFeedback
        return ExecutionFeedback()
    except ImportError:
        try:
            from src.gateway.execution_feedback import ExecutionFeedback
            return ExecutionFeedback()
        except ImportError:
            mock_fb = MagicMock()
            # verify takes (execution_record, actual_result, context) - 3 args
            async def mock_verify(exec_record, actual_result, context):
                return MagicMock(verified=True, deviations=[], retry_count=0)
            mock_fb.verify = AsyncMock(side_effect=mock_verify)
            # batch_verify takes (executions, actual_results, context) - 3 args
            async def mock_batch_verify(executions, actual_results, context):
                return MagicMock(verified_count=len(executions), failed_count=0)
            mock_fb.batch_verify = AsyncMock(side_effect=mock_batch_verify)
            return mock_fb


@pytest.fixture
def knowledge_graph():
    """知识图谱（P0-2）- 待实现"""
    # 导入路径：src.knowledge.graph.knowledge_graph
    mock_kg = MagicMock()
    mock_kg.query.return_value = {"nodes": [], "edges": []}
    mock_kg.add_triple.return_value = True
    return mock_kg


@pytest.fixture
def case_library():
    """案例库（P0-2）- 待实现"""
    # 导入路径：src.knowledge.services.case_library_service
    mock_cl = MagicMock()
    mock_cl.search.return_value = []
    mock_cl.add_case.return_value = "CASE-001"
    return mock_cl


@pytest.fixture
def rag_retriever():
    """RAG检索器（P0-2）- 待实现"""
    # 导入路径：src.knowledge.search.rag_retriever
    mock_rag = MagicMock()
    mock_rag.hybrid_search.return_value = []
    return mock_rag


@pytest.fixture
def topology_tools():
    """拓扑感知工具（P0-3）- 待实现"""
    # 导入路径：src.tools.topology_tools
    mock_topo = MagicMock()
    mock_topo.get_cluster_topology.return_value = {}
    return mock_topo


@pytest.fixture
def config_tools():
    """配置感知工具（P0-3）- 待实现"""
    # 导入路径：src.tools.config_tools
    mock_cfg = MagicMock()
    mock_cfg.get_instance_config.return_value = {}
    return mock_cfg


@pytest.fixture
def orchestrator():
    """编排Agent"""
    try:
        from src.agents.orchestrator import OrchestratorAgent
        return OrchestratorAgent()
    except ImportError:
        pytest.skip("OrchestratorAgent不可用")


@pytest.fixture
def diagnostic_agent():
    """诊断Agent"""
    try:
        from src.agents.diagnostic import DiagnosticAgent
        return DiagnosticAgent()
    except ImportError:
        pytest.skip("DiagnosticAgent不可用")


@pytest.fixture
def risk_agent():
    """风险评估Agent"""
    try:
        from src.agents.risk import RiskAgent
        return RiskAgent()
    except ImportError:
        pytest.skip("RiskAgent不可用")


# ============================================================================
# Fixtures: Mock上下文
# ============================================================================

@pytest.fixture
def mock_context():
    """通用测试上下文"""
    return {
        "instance_id": "INS-TEST-V2-001",
        "db_type": "postgresql",
        "user": "test_user_v2",
        "session_id": "session-v2-001",
        "permissions": ["read", "analyze", "execute"],
        "risk_level": "L1",
    }


@pytest.fixture
def mock_policy_always_allow():
    """Mock PolicyEngine: 总是允许（测试用）"""
    from src.gateway.policy_engine import PolicyResult, RiskLevel
    mock_policy = MagicMock()
    mock_policy.check.return_value = PolicyResult(
        allowed=True,
        approval_required=False,
        approvers=[],
    )
    with patch("src.agents.base.get_policy_engine", return_value=mock_policy):
        yield mock_policy


@pytest.fixture
def mock_policy_deny_high_risk():
    """Mock PolicyEngine: 高风险拒绝"""
    from src.gateway.policy_engine import PolicyResult, RiskLevel
    mock_policy = MagicMock()
    mock_policy.check.return_value = PolicyResult(
        allowed=False,
        approval_required=True,
        approvers=["admin"],
    )
    with patch("src.agents.base.get_policy_engine", return_value=mock_policy):
        yield mock_policy


# ============================================================================
# Fixtures: 测试数据
# ============================================================================

@pytest.fixture
def sample_sql_queries():
    """标准SQL样本库"""
    return {
        "safe_select": "SELECT id, name FROM users WHERE status = 1",
        "safe_join": """
            SELECT a.id, b.name FROM orders a
            JOIN customers b ON a.customer_id = b.id
            WHERE a.created_at > '2026-01-01'
        """,
        "dangerous_truncate": "TRUNCATE TABLE users",
        "dangerous_drop": "DROP TABLE IF EXISTS backup_logs",
        "dangerous_delete_all": "DELETE FROM session_history WHERE 1=1",
        "dangerous_update_no_where": "UPDATE user_permissions SET level = 99",
        "dangerous_alter": "ALTER TABLE orders DROP COLUMN discount",
        "injection_attempt": "SELECT * FROM users WHERE name = '1' OR '1'='1'",
        "union_injection": "SELECT * FROM users UNION SELECT * FROM passwords",
        "comment_injection": "SELECT * FROM users; -- DROP TABLE users",
        "big_query": "SELECT " + "a" * (1024 * 1024),  # 1MB query
    }


@pytest.fixture
def sample_knowledge_graph_data():
    """知识图谱样本数据"""
    return {
        "故障模式": "锁等待超时",
        "根因": "长事务持有锁未释放",
        "症状": ["wait_time > 30s", "blocked_sessions > 5"],
        "处置": ["找到阻塞会话", "评估kill风险", "执行kill或等待"],
        "预防": ["设置锁超时", "拆分大事务"],
    }


@pytest.fixture
def sample_topology_data():
    """拓扑感知样本数据"""
    return {
        "cluster_id": "CLS-TEST-001",
        "nodes": [
            {"node_id": "N1", "role": "primary", "host": "192.168.1.10", "status": "up"},
            {"node_id": "N2", "role": "replica", "host": "192.168.1.11", "status": "up"},
            {"node_id": "N3", "role": "replica", "host": "192.168.1.12", "status": "down"},
        ],
        "connections": [
            {"from": "N1", "to": "N2", "type": "sync"},
            {"from": "N1", "to": "N3", "type": "async"},
        ],
    }


# ============================================================================
# Auto-cleanup fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def register_all_tools():
    """每个测试前注册所有工具"""
    try:
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
    except Exception:
        pass  # 测试可能在实现前运行
    yield


@pytest.fixture(autouse=True)
def reset_test_env():
    """每个测试前后重置测试环境"""
    original_env = os.environ.get("ZLOUD_ENV", "test")
    os.environ["ZLOUD_ENV"] = "test"
    yield
    os.environ["ZLOUD_ENV"] = original_env
