"""
Mock data fixtures for testing
"""
import json
from datetime import datetime


def get_mock_instance_status():
    """Mock instance status data"""
    return {
        "instance_id": "INS-TEST-001",
        "instance_name": "test_db_primary",
        "host": "192.168.1.100",
        "port": 5432,
        "version": "PostgreSQL 16.3",
        "uptime_seconds": 864000,
        "state": "running",
        "metrics": {
            "cpu_usage_percent": 45.5,
            "memory_usage_percent": 62.3,
            "disk_usage_percent": 78.1,
            "connections": 85,
            "max_connections": 200,
            "transactions_per_second": 1250,
            "queries_per_second": 5000
        }
    }


def get_mock_sessions():
    """Mock session data"""
    return {
        "instance_id": "INS-TEST-001",
        "sessions": [
            {
                "pid": 1234,
                "state": "active",
                "duration_seconds": 300,
                "query": "SELECT o_id, name FROM orders WHERE status = 'pending'",
                "wait_event_type": "Lock",
                "wait_event": "lock_tuple",
                "backend_type": "client backend",
                "application_name": "app_server_1"
            },
            {
                "pid": 5678,
                "state": "idle in transaction",
                "duration_seconds": 600,
                "query": "BEGIN; UPDATE accounts SET balance = balance - 100;",
                "wait_event_type": None,
                "backend_type": "client backend",
                "application_name": "batch_job"
            },
            {
                "pid": 9012,
                "state": "active",
                "duration_seconds": 5,
                "query": "SELECT count(*) FROM large_table",
                "wait_event_type": None,
                "backend_type": "client backend",
                "application_name": "analytics"
            }
        ],
        "total_count": 3
    }


def get_mock_locks():
    """Mock lock data"""
    return {
        "instance_id": "INS-TEST-001",
        "locks": [
            {
                "lock_type": "relation",
                "mode": "ShareRowExclusiveLock",
                "granted": True,
                "pid": 5678,
                "query": "UPDATE accounts SET balance = balance - 100",
                "relation": "accounts"
            },
            {
                "lock_type": "tuple",
                "mode": "ForUpdate",
                "granted": False,
                "pid": 1234,
                "query": "SELECT o_id, name FROM orders WHERE status = 'pending'",
                "relation": "orders"
            }
        ],
        "lock_wait_chain": [
            {
                "blocked_pid": 1234,
                "blocked_query": "SELECT o_id FROM orders",
                "blocking_pid": 5678,
                "blocking_query": "UPDATE accounts"
            }
        ]
    }


def get_mock_slow_sqls():
    """Mock slow SQL data"""
    return {
        "instance_id": "INS-TEST-001",
        "slow_sqls": [
            {
                "fingerprint": "abc123def456",
                "query": "SELECT * FROM orders o JOIN customers c ON o.c_id = c.id WHERE c.region = 'APAC'",
                "calls": 1500,
                "total_time_ms": 45000,
                "avg_time_ms": 30,
                "min_time_ms": 25,
                "max_time_ms": 150,
                "rows": 50000,
                "execution_plan": {
                    "operation": "Nested Loop",
                    "cost": 10000,
                    "actual_rows": 50000,
                    "warnings": ["Seq Scan on orders"]
                }
            },
            {
                "fingerprint": "xyz789ghi012",
                "query": "SELECT count(*) FROM large_table WHERE created_at > '2026-01-01'",
                "calls": 200,
                "total_time_ms": 8000,
                "avg_time_ms": 40,
                "min_time_ms": 35,
                "max_time_ms": 200,
                "rows": 1000000,
                "execution_plan": {
                    "operation": "Seq Scan",
                    "cost": 5000,
                    "actual_rows": 1000000,
                    "warnings": ["全表扫描"]
                }
            }
        ]
    }


def get_mock_replication_status():
    """Mock replication status"""
    return {
        "instance_id": "INS-TEST-001",
        "role": "primary",
        "replication_slots": [
            {
                "slot_name": "replica_slot_1",
                "active": True,
                "restart_lsn": "0/5000000",
                "confirmed_flush_lsn": "0/5000000"
            }
        ],
        "replication_lag_bytes": 1024000,
        "replication_lag_seconds": 5
    }


def get_mock_alert_event():
    """Mock alert event"""
    return {
        "alert_id": "ALT-20260328-001",
        "alert_code": "ALT_LOCK_WAIT",
        "name": "锁等待超时",
        "severity": "warning",
        "instance_id": "INS-TEST-001",
        "triggered_at": "2026-03-28T10:00:00Z",
        "status": "firing",
        "labels": {
            "severity": "warning",
            "category": "lock"
        },
        "annotations": {
            "summary": "实例 INS-TEST-001 发生锁等待超时",
            "description": "等待时间超过30秒，涉及2个会话"
        },
        "metrics": {
            "wait_time_ms": 35000,
            "blocked_sessions": 2,
            "lock_count": 3
        }
    }


def get_mock_inspection_result():
    """Mock inspection result"""
    return {
        "inspection_id": "INS-20260328-001",
        "instance_id": "INS-TEST-001",
        "started_at": "2026-03-28T09:00:00Z",
        "completed_at": "2026-03-28T09:05:00Z",
        "health_score": 78,
        "categories": {
            "availability": {"score": 95, "issues": []},
            "performance": {"score": 65, "issues": ["慢SQL数量过多", "连接数接近上限"]},
            "security": {"score": 90, "issues": []},
            "capacity": {"score": 72, "issues": ["磁盘使用率偏高"]}
        },
        "risk_items": [
            {
                "severity": "warning",
                "category": "performance",
                "item": "慢SQL数量过多",
                "detail": "过去1小时发现50+慢SQL",
                "recommendation": "优化Top SQL，增加索引"
            },
            {
                "severity": "warning",
                "category": "performance",
                "item": "连接数接近上限",
                "detail": "当前连接数185/200",
                "recommendation": "考虑扩大max_connections或优化连接池"
            },
            {
                "severity": "info",
                "category": "capacity",
                "item": "磁盘使用率偏高",
                "detail": "磁盘使用率78%",
                "recommendation": "准备扩容或清理历史数据"
            }
        ],
        "summary": "整体健康状态良好，但性能和容量需要关注"
    }


def get_mock_rca_report():
    """Mock RCA report"""
    return {
        "report_id": "RCA-20260328-001",
        "title": "锁等待超时故障分析报告",
        "incident_time": "2026-03-28T10:00:00Z",
        "resolved_time": "2026-03-28T10:30:00Z",
        "duration_minutes": 30,
        "summary": "销售系统在高峰期出现订单处理延迟，经排查为锁等待超时导致",
        "timeline": [
            {"time": "10:00:00", "event": "告警触发：锁等待超时"},
            {"time": "10:05:00", "event": "运维人员接收告警"},
            {"time": "10:10:00", "event": "定位到长事务持有锁"},
            {"time": "10:15:00", "event": "评估后可安全终止会话"},
            {"time": "10:20:00", "event": "执行会话终止"},
            {"time": "10:25:00", "event": "业务恢复"},
            {"time": "10:30:00", "event": "验证完成，故障关闭"}
        ],
        "root_cause": "批处理作业开启事务后长时间未提交，导致持有ShareRowExclusiveLock，阻塞了多个业务会话",
        "impact": {
            "affected_users": 150,
            "failed_transactions": 230,
            "revenue_impact": "约5000元"
        },
        "resolution": [
            "终止持有锁的会话(PID 5678)",
            "联系应用团队优化批处理作业，增加定期提交",
            "添加事务超时配置"
        ],
        "lessons": [
            "批处理作业必须设置合理的事务超时",
            "高并发业务应避免长事务",
            "需要建立锁等待的监控告警"
        ],
        "preventive_measures": [
            "添加事务超时参数 (statement_timeout)",
            "在批处理作业中增加定期COMMIT",
            "添加锁等待时间监控"
        ]
    }


def get_mock_user_permissions():
    """Mock user permissions"""
    return {
        "user_id": "user-001",
        "username": "dba_admin",
        "role": "dba",
        "permission_level": "L3",
        "allowed_tools": [
            "query_instance_status",
            "query_session",
            "query_lock",
            "query_replication",
            "query_slow_sql",
            "diagnose_alert",
            "assess_risk",
            "execute_inspection"
        ],
        "forbidden_tools": [
            "kill_session",
            "drop_table",
            "execute_sql"
        ]
    }


class MockOllamaResponse:
    """Mock Ollama API response"""
    
    @staticmethod
    def chat_response(content):
        return {
            "model": "glm4:latest",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "total_duration": 1000000000
        }
    
    @staticmethod
    def generate_response(response_text):
        return {
            "model": "glm4:latest",
            "response": response_text,
            "done": True,
            "total_duration": 1000000000
        }
