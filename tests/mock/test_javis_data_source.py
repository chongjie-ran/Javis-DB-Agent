"""
Javis数据源Mock数据 - 第二轮测试
提供更全面的测试数据
"""
import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, List


class ZCloudMockDataGenerator:
    """Javis-DB-Agent Mock数据生成器"""
    
    @staticmethod
    def generate_instance_status(instance_id: str = "INS-TEST-001", **overrides) -> Dict[str, Any]:
        """生成实例状态数据"""
        data = {
            "instance_id": instance_id,
            "instance_name": f"db_{instance_id.lower()}",
            "host": "192.168.1.100",
            "port": 5432,
            "version": "PostgreSQL 16.3",
            "uptime_seconds": 864000,
            "state": "running",
            "region": "ap-shanghai",
            "engine": "postgresql",
            "metrics": {
                "cpu_usage_percent": 45.5,
                "memory_usage_percent": 62.3,
                "disk_usage_percent": 78.1,
                "connections": 85,
                "max_connections": 200,
                "transactions_per_second": 1250,
                "queries_per_second": 5000,
                "cache_hit_ratio": 0.95,
                "active_transactions": 12,
                "blocked_transactions": 2,
                "wal_files": 15
            },
            "replication": {
                "role": "primary",
                "replication_slots": 2,
                "lag_bytes": 1024
            }
        }
        data.update(overrides)
        return data
    
    @staticmethod
    def generate_sessions(count: int = 5) -> Dict[str, Any]:
        """生成会话数据"""
        states = ["active", "idle", "idle in transaction", "fastpath function call", "disabled"]
        wait_events = [None, "Lock", "Extend EOF", "LWLockNamed", "IO/Local/IOComplete"]
        
        sessions = []
        for i in range(count):
            pid = 1000 + i * 100
            state = states[i % len(states)]
            duration = i * 60
            
            sessions.append({
                "pid": pid,
                "state": state,
                "duration_seconds": duration,
                "query": f"SELECT * FROM table_{i} WHERE id = {i}" if state == "active" else "<command string>",
                "query_start": (datetime.now() - timedelta(seconds=duration)).isoformat(),
                "wait_event_type": wait_events[i % len(wait_events)],
                "wait_event": f"lock:{i}" if wait_events[i % len(wait_events)] == "Lock" else None,
                "backend_type": "client backend",
                "application_name": f"app_server_{i % 3 + 1}",
                "user": "db_user",
                "database": "zcloud_db",
                "client_addr": f"192.168.1.{100 + i}"
            })
        
        return {
            "instance_id": "INS-TEST-001",
            "sessions": sessions,
            "total_count": count,
            "active_count": sum(1 for s in sessions if s["state"] == "active"),
            "idle_count": sum(1 for s in sessions if "idle" in s["state"]),
            "blocked_count": sum(1 for s in sessions if s["wait_event_type"] == "Lock")
        }
    
    @staticmethod
    def generate_locks(lock_count: int = 3) -> Dict[str, Any]:
        """生成锁数据"""
        lock_types = ["relation", "tuple", "transactionid", "virtualxid"]
        modes = ["AccessShareLock", "RowShareLock", "RowExclusiveLock", "ShareUpdateExclusiveLock", 
                 "ShareRowExclusiveLock", "ExclusiveLock", "AccessExclusiveLock"]
        
        locks = []
        for i in range(lock_count):
            granted = i < lock_count - 1  # 最后一个等待
            locks.append({
                "lock_type": lock_types[i % len(lock_types)],
                "mode": modes[i % len(modes)],
                "granted": granted,
                "pid": 1000 + i * 100,
                "transactionid": f"{(datetime.now() - timedelta(hours=i)).timestamp():.0f}",
                "query": f"UPDATE table_{i} SET col = {i}" if i % 2 == 0 else "SELECT * FROM table",
                "relation": f"table_{i}" if i % 2 == 0 else None,
                "page": i * 10 if i % 2 == 0 else None,
                "tuple": i if i % 3 == 0 else None
            })
        
        return {
            "instance_id": "INS-TEST-001",
            "locks": locks,
            "lock_wait_chain": ZCloudMockDataGenerator._build_lock_chain(locks),
            "total_lock_count": len(locks),
            "waiting_lock_count": sum(1 for l in locks if not l["granted"]),
            "granted_lock_count": sum(1 for l in locks if l["granted"])
        }
    
    @staticmethod
    def _build_lock_chain(locks: List[Dict]) -> List[Dict]:
        """构建锁等待链"""
        chain = []
        waiting = [l for l in locks if not l["granted"]]
        granted = [l for l in locks if l["granted"]]
        
        for w in waiting:
            blockers = [g for g in granted if g["pid"] != w["pid"]]
            if blockers:
                chain.append({
                    "blocked_pid": w["pid"],
                    "blocked_query": w.get("query", ""),
                    "blocking_pid": blockers[0]["pid"],
                    "blocking_query": blockers[0].get("query", "")
                })
        return chain
    
    @staticmethod
    def generate_slow_sqls(count: int = 5) -> Dict[str, Any]:
        """生成慢SQL数据"""
        slow_sqls = []
        for i in range(count):
            avg_time = 30 + i * 10
            slow_sqls.append({
                "fingerprint": f"fp-{i:06d}",
                "query": f"SELECT o.*, c.* FROM orders o JOIN customers c ON o.c_id = c.id WHERE c.region = 'APAC' AND o.status = '{['pending', 'processing', 'shipped'][i % 3]}'",
                "calls": 1000 + i * 100,
                "total_time_ms": avg_time * (1000 + i * 100),
                "avg_time_ms": avg_time,
                "min_time_ms": avg_time - 5,
                "max_time_ms": avg_time + 50,
                "rows": 10000 * (i + 1),
                "database": "zcloud_db",
                "user": "db_user",
                "execution_plan": {
                    "operation": "Nested Loop" if i % 2 == 0 else "Hash Join",
                    "cost": 1000 * (i + 1),
                    "actual_rows": 10000 * (i + 1),
                    "warnings": ["Seq Scan on orders"] if i % 2 == 0 else [],
                    "plans": [
                        {
                            "node": "Seq Scan on orders",
                            "cost": 500,
                            "rows": 10000
                        },
                        {
                            "node": "Index Scan on customers",
                            "cost": 50,
                            "rows": 1000
                        }
                    ]
                }
            })
        
        return {
            "instance_id": "INS-TEST-001",
            "slow_sqls": slow_sqls,
            "total_count": len(slow_sqls),
            "summary": {
                "total_queries": sum(s["calls"] for s in slow_sqls),
                "avg_time_ms": sum(s["avg_time_ms"] for s in slow_sqls) / len(slow_sqls)
            }
        }
    
    @staticmethod
    def generate_replication_status() -> Dict[str, Any]:
        """生成复制状态数据"""
        return {
            "instance_id": "INS-TEST-001",
            "role": "primary",
            "is_primary": True,
            "replication_slots": [
                {
                    "slot_name": f"replica_slot_{i}",
                    "active": True,
                    "restart_lsn": f"0/{5000000 + i * 100000}",
                    "confirmed_flush_lsn": f"0/{5000000 + i * 100000}",
                    "lag_bytes": 1024 * (i + 1)
                }
                for i in range(2)
            ],
            "replicas": [
                {
                    "application_name": f"replica_{i}",
                    "host": f"192.168.1.{200 + i}",
                    "port": 5432,
                    "state": "streaming",
                    "lag_bytes": 1024 * (i + 1),
                    "sent_lsn": f"0/{6000000 + i * 100000}",
                    "write_lsn": f"0/{5900000 + i * 100000}",
                    "flush_lsn": f"0/{5800000 + i * 100000}",
                    "replay_lsn": f"0/{5700000 + i * 100000}"
                }
                for i in range(2)
            ],
            "replication_lag_bytes": 2048,
            "replication_lag_seconds": 2
        }
    
    @staticmethod
    def generate_alert_events(count: int = 5) -> List[Dict[str, Any]]:
        """生成告警事件列表"""
        alert_types = [
            ("ALT_LOCK_WAIT", "锁等待超时", "warning"),
            ("ALT_SLOW_QUERY", "慢SQL告警", "info"),
            ("ALT_REPLICATION_LAG", "主从延迟告警", "warning"),
            ("ALT_CONNECTION_HIGH", "连接数过高", "warning"),
            ("ALT_DISK_HIGH", "磁盘使用率过高", "info")
        ]
        
        alerts = []
        for i in range(count):
            alert_code, name, severity = alert_types[i % len(alert_types)]
            alerts.append({
                "alert_id": f"ALT-20260328-{i:03d}",
                "alert_code": alert_code,
                "name": name,
                "severity": severity,
                "instance_id": "INS-TEST-001",
                "triggered_at": (datetime.now() - timedelta(hours=i)).isoformat() + "Z",
                "status": "firing" if i < 2 else "resolved",
                "labels": {
                    "severity": severity,
                    "category": alert_code.split("_")[1].lower()
                },
                "annotations": {
                    "summary": f"实例 INS-TEST-001 发生{name}",
                    "description": f"告警详情描述 {i}"
                },
                "metrics": {
                    "wait_time_ms": 35000 + i * 1000,
                    "blocked_sessions": 2 + i,
                    "lock_count": 3 + i
                }
            })
        
        return alerts
    
    @staticmethod
    def generate_inspection_result(health_score: int = 78) -> Dict[str, Any]:
        """生成巡检结果"""
        return {
            "inspection_id": "INS-20260328-001",
            "instance_id": "INS-TEST-001",
            "started_at": (datetime.now() - timedelta(minutes=30)).isoformat() + "Z",
            "completed_at": datetime.now().isoformat() + "Z",
            "duration_seconds": 300,
            "health_score": health_score,
            "categories": {
                "availability": {
                    "score": 95,
                    "issues": [],
                    "checks": ["实例运行状态", "连接可用性", "复制状态"]
                },
                "performance": {
                    "score": 65,
                    "issues": ["慢SQL数量过多", "连接数接近上限", "缓存命中率下降"],
                    "checks": ["CPU使用率", "内存使用率", "慢SQL统计", "连接数"]
                },
                "security": {
                    "score": 90,
                    "issues": [],
                    "checks": ["密码策略", "权限配置", "审计日志"]
                },
                "capacity": {
                    "score": 72,
                    "issues": ["磁盘使用率偏高", "表空间增长过快"],
                    "checks": ["磁盘空间", "表空间使用率", "数据增长趋势"]
                }
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
    
    @staticmethod
    def generate_rca_report() -> Dict[str, Any]:
        """生成RCA报告"""
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
                "revenue_impact": "约5000元",
                "services_affected": ["订单服务", "支付服务"]
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
                {"action": "添加事务超时参数", "config": "statement_timeout=300000"},
                {"action": "在批处理作业中增加定期COMMIT", "frequency": "每1000条"},
                {"action": "添加锁等待时间监控", "threshold": "30秒"}
            ],
            "attachments": ["lock_chain.png", "session_list.csv", "db_logs.zip"]
        }


class TestMockDataGenerator:
    """Mock数据生成器测试"""
    
    def test_generate_instance_status(self):
        """测试生成实例状态"""
        data = ZCloudMockDataGenerator.generate_instance_status()
        
        assert data["instance_id"] == "INS-TEST-001"
        assert data["state"] == "running"
        assert "metrics" in data
        assert "cpu_usage_percent" in data["metrics"]
    
    def test_generate_sessions(self):
        """测试生成会话数据"""
        data = ZCloudMockDataGenerator.generate_sessions(count=5)
        
        assert len(data["sessions"]) == 5
        assert data["total_count"] == 5
        assert "active_count" in data
    
    def test_generate_locks(self):
        """测试生成锁数据"""
        data = ZCloudMockDataGenerator.generate_locks(lock_count=3)
        
        assert len(data["locks"]) == 3
        assert "lock_wait_chain" in data
    
    def test_generate_slow_sqls(self):
        """测试生成慢SQL数据"""
        data = ZCloudMockDataGenerator.generate_slow_sqls(count=5)
        
        assert len(data["slow_sqls"]) == 5
        assert "summary" in data
    
    def test_generate_replication_status(self):
        """测试生成复制状态"""
        data = ZCloudMockDataGenerator.generate_replication_status()
        
        assert data["role"] == "primary"
        assert len(data["replicas"]) == 2
    
    def test_generate_alert_events(self):
        """测试生成告警事件"""
        alerts = ZCloudMockDataGenerator.generate_alert_events(count=5)
        
        assert len(alerts) == 5
        assert alerts[0]["alert_code"] == "ALT_LOCK_WAIT"
    
    def test_generate_inspection_result(self):
        """测试生成巡检结果"""
        data = ZCloudMockDataGenerator.generate_inspection_result(health_score=78)
        
        assert data["health_score"] == 78
        assert "categories" in data
        assert "risk_items" in data
    
    def test_generate_rca_report(self):
        """测试生成RCA报告"""
        data = ZCloudMockDataGenerator.generate_rca_report()
        
        assert data["report_id"] == "RCA-20260328-001"
        assert "timeline" in data
        assert "root_cause" in data
    
    def test_override_fields(self):
        """测试覆盖字段"""
        data = ZCloudMockDataGenerator.generate_instance_status(
            instance_id="INS-CUSTOM",
            state="stopped",
            host="192.168.2.100"
        )
        
        assert data["instance_id"] == "INS-CUSTOM"
        assert data["state"] == "stopped"
        assert data["host"] == "192.168.2.100"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
