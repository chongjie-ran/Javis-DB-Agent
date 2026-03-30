"""
V1.5 真实环境自动化测试框架
支持 MySQL 和 PostgreSQL 真实环境测试
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest
import asyncio
from typing import Optional

# Import db adapters if they exist
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


class TestConfig:
    """测试配置"""

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

    @classmethod
    def is_mysql_available(cls) -> bool:
        """检查MySQL是否可用"""
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
        """检查PostgreSQL是否可用"""
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
    def get_mysql_conn(cls):
        """获取MySQL连接（ caller负责关闭）"""
        if not cls.is_mysql_available():
            raise RuntimeError("MySQL不可用")
        return pymysql.connect(
            host=cls.MYSQL_HOST,
            port=cls.MYSQL_PORT,
            user=cls.MYSQL_USER,
            password=cls.MYSQL_PASSWORD,
            database=cls.MYSQL_DATABASE,
            connect_timeout=10,
        )

    @classmethod
    def get_pg_conn(cls):
        """获取PostgreSQL连接（ caller负责关闭）"""
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mysql_available():
    """Session级别：MySQL是否可用"""
    return TestConfig.is_mysql_available()


@pytest.fixture(scope="session")
def pg_available():
    """Session级别：PostgreSQL是否可用"""
    return TestConfig.is_pg_available()


@pytest.fixture
def mysql_conn(mysql_available):
    """MySQL连接 fixture（每个测试自动关闭）"""
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
    """PostgreSQL连接 fixture（每个测试自动关闭）"""
    if not pg_available:
        pytest.skip("PostgreSQL不可用")
    conn = TestConfig.get_pg_conn()
    yield conn
    try:
        conn.close()
    except Exception:
        pass


@pytest.fixture
def backup_agent():
    """BackupAgent实例"""
    from src.agents.backup_agent import BackupAgent
    return BackupAgent()


@pytest.fixture
def perf_agent():
    """PerformanceAgent实例"""
    from src.agents.performance_agent import PerformanceAgent
    return PerformanceAgent()


@pytest.fixture
def orchestrator():
    """OrchestratorAgent实例"""
    from src.agents.orchestrator import OrchestratorAgent
    return OrchestratorAgent()


# ---------------------------------------------------------------------------
# Pytest runner configuration
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line("markers", "mysql: MySQL环境测试")
    config.addinivalue_line("markers", "pg: PostgreSQL环境测试")
    config.addinivalue_line("markers", "integration: 集成测试")
    config.addinivalue_line("markers", "slow: 耗时较长的测试")
    config.addinivalue_line("markers", "real_db: 真实数据库测试")


if __name__ == "__main__":
    # 支持直接运行：python test_runner.py
    # 先打印环境状态
    from check_env import main as check_main
    check_main()
    print("\n运行测试:")
    pytest.main([__file__, "-v", "--tb=short"])
