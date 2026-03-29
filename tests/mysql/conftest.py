"""
MySQL 兼容性测试 - conftest.py

提供 MySQL 测试所需的 fixtures
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock
from typing import Optional, Dict, Any

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


class MockMySQLConnection:
    """模拟 MySQL 连接用于测试"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._connected = True
        self._cursor = MagicMock()
    
    def cursor(self):
        return self._cursor
    
    def commit(self):
        pass
    
    def close(self):
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected


@pytest.fixture
def mysql_config():
    """MySQL 测试配置"""
    return {
        "host": "127.0.0.1",
        "port": 3307,
        "user": "root",
        "password": "test123",
        "database": "zcloud_test_mysql",
    }


@pytest.fixture
def mock_mysql_connection(mysql_config):
    """模拟 MySQL 连接"""
    return MockMySQLConnection(mysql_config)


@pytest.fixture
def mysql_instance_data():
    """MySQL 实例测试数据"""
    return {
        "instance_id": "INS-MYSQL-001",
        "instance_name": "PROD-MYSQL-DB",
        "db_type": "mysql",
        "version": "8.0.32",
        "status": "running",
        "host": "192.168.1.100",
        "port": 3306,
        "cpu_percent": 45.5,
        "memory_percent": 68.3,
        "disk_percent": 55.0,
        "connections": 156,
        "max_connections": 500,
    }


@pytest.fixture
def mysql_session_data():
    """MySQL 会话测试数据"""
    return {
        "sessions": [
            {
                "thread_id": 1,
                "user": "app_user",
                "host": "192.168.1.50",
                "db": "orders",
                "command": "Query",
                "time": 5,
                "state": "executing",
                "current_sql": "SELECT * FROM orders WHERE status = 'pending'",
            },
            {
                "thread_id": 2,
                "user": "app_user",
                "host": "192.168.1.51",
                "db": "orders",
                "command": "Query",
                "time": 120,
                "state": "Waiting for table metadata lock",
                "current_sql": "ALTER TABLE orders ADD COLUMN new_col VARCHAR(50)",
            },
            {
                "thread_id": 3,
                "user": "app_user",
                "host": "192.168.1.52",
                "db": None,
                "command": "Sleep",
                "time": 300,
                "state": None,
                "current_sql": None,
            },
        ],
        "total": 3,
        "active_count": 2,
    }


@pytest.fixture
def mysql_lock_data():
    """MySQL 锁等待测试数据"""
    return {
        "locks": [
            {
                "waiting_trx_id": "12345",
                "waiting_thread": 2,
                "waiting_query": "INSERT INTO orders VALUES (1, 'pending')",
                "blocking_trx_id": "12344",
                "blocking_thread": 1,
                "blocking_query": "ALTER TABLE orders ADD COLUMN new_col VARCHAR(50)",
                "blocking_started": "2026-03-28 10:00:00",
                "blocking_rows_locked": 0,
                "blocking_state": "RUNNING",
            }
        ],
        "total_blocked": 1,
        "deadlock_count": 0,
    }


@pytest.fixture
def mysql_slow_sql_data():
    """MySQL 慢SQL测试数据"""
    return {
        "slow_sqls": [
            {
                "sql_id": "sql_001",
                "sql_text": "SELECT o.*, u.* FROM orders o JOIN users u ON o.user_id = u.id WHERE o.created_at > '2026-01-01'",
                "executions": 150,
                "total_time_sec": 45.6,
                "avg_time_ms": 304.0,
                "rows_examined": 150000,
                "rows_sent": 15000,
            },
            {
                "sql_id": "sql_002",
                "sql_text": "SELECT COUNT(*) FROM orders WHERE status = 'completed' GROUP BY user_id",
                "executions": 500,
                "total_time_sec": 30.2,
                "avg_time_ms": 60.4,
                "rows_examined": 50000,
                "rows_sent": 500,
            },
        ],
        "total": 2,
    }


@pytest.fixture
def mysql_alert_data():
    """MySQL 告警测试数据"""
    return {
        "alerts": [
            {
                "alert_id": "ALT-MYSQL-001",
                "alert_name": "连接数告警",
                "alert_type": "CONNECTIONS_HIGH",
                "severity": "warning",
                "instance_id": "INS-MYSQL-001",
                "metric_value": 450,
                "threshold": 400,
                "message": "MySQL 连接数达到 450，超过阈值 400",
                "status": "active",
            },
            {
                "alert_id": "ALT-MYSQL-002",
                "alert_name": "锁等待超时",
                "alert_type": "LOCK_WAIT_TIMEOUT",
                "severity": "warning",
                "instance_id": "INS-MYSQL-001",
                "metric_value": 120.5,
                "threshold": 60.0,
                "message": "InnoDB 锁等待时间达到 120.5 秒",
                "status": "active",
            },
            {
                "alert_id": "ALT-MYSQL-003",
                "alert_name": "缓冲池命中率低",
                "alert_type": "BUFFER_HIT_RATIO_LOW",
                "severity": "info",
                "instance_id": "INS-MYSQL-001",
                "metric_value": 85.0,
                "threshold": 90.0,
                "message": "InnoDB 缓冲池命中率为 85%，低于 90%",
                "status": "active",
            },
        ]
    }


@pytest.fixture
def mysql_mock_client():
    """MySQL Mock 客户端"""
    client = MagicMock()
    
    # 实例状态
    client.get_instance = AsyncMock(return_value={
        "instance_id": "INS-MYSQL-001",
        "instance_name": "PROD-MYSQL-DB",
        "db_type": "mysql",
        "status": "running",
    })
    
    # 会话列表
    client.get_sessions = AsyncMock(return_value={
        "sessions": [
            {"thread_id": 1, "user": "app_user", "command": "Query", "time": 5},
            {"thread_id": 2, "user": "app_user", "command": "Query", "time": 120},
        ],
        "total": 2,
    })
    
    # 锁等待
    client.get_locks = AsyncMock(return_value={
        "locks": [
            {
                "waiting_trx_id": "12345",
                "blocking_trx_id": "12344",
                "wait_seconds": 120,
            }
        ],
        "total_blocked": 1,
    })
    
    # 慢SQL
    client.get_slow_sql = AsyncMock(return_value={
        "slow_sqls": [
            {
                "sql_id": "sql_001",
                "sql_text": "SELECT * FROM orders",
                "avg_time_ms": 304.0,
            }
        ],
        "total": 1,
    })
    
    return client
