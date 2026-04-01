"""Mock Javis-DB-Agent API Client
模拟Javis平台的API接口结构，用于开发和测试
"""
import time
import random
import threading
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class MockInstance:
    """模拟数据库实例"""
    instance_id: str
    instance_name: str
    db_type: str  # mysql/postgresql/oracle
    version: str
    status: str  # running/stopped/error
    host: str
    port: int
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    connections: int = 0
    max_connections: int = 500
    uptime_seconds: int = 0
    created_at: float = field(default_factory=time.time)
    

@dataclass
class MockAlert:
    """模拟告警"""
    alert_id: str
    alert_name: str
    alert_type: str
    severity: str  # critical/warning/info
    instance_id: str
    instance_name: str
    occurred_at: float
    metric_value: float
    threshold: float
    message: str
    status: str  # active/acknowledged/resolved


class MockJavisClient:
    """Mock Javis-DB-Agent API客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8080/api/v1"):
        self.base_url = base_url
        self._instances = self._init_mock_instances()
        self._alerts = self._init_mock_alerts()
    
    def _init_mock_instances(self) -> dict[str, MockInstance]:
        """初始化模拟实例数据"""
        return {
            "INS-001": MockInstance(
                instance_id="INS-001",
                instance_name="PROD-ORDER-DB",
                db_type="mysql",
                version="8.0.32",
                status="running",
                host="192.168.1.10",
                port=3306,
                cpu_usage=45.5,
                memory_usage=68.3,
                disk_usage=55.0,
                connections=156,
                max_connections=500,
                uptime_seconds=864000,
            ),
            "INS-002": MockInstance(
                instance_id="INS-002",
                instance_name="PROD-USER-DB",
                db_type="postgresql",
                version="14.7",
                status="running",
                host="192.168.1.11",
                port=5432,
                cpu_usage=32.1,
                memory_usage=55.8,
                disk_usage=42.3,
                connections=89,
                max_connections=300,
                uptime_seconds=1728000,
            ),
            "INS-003": MockInstance(
                instance_id="INS-003",
                instance_name="PROD-ANALYTICS-DB",
                db_type="mysql",
                version="8.0.32",
                status="running",
                host="192.168.1.12",
                port=3307,
                cpu_usage=78.9,
                memory_usage=85.2,
                disk_usage=72.6,
                connections=245,
                max_connections=800,
                uptime_seconds=432000,
            ),
        }
    
    def _init_mock_alerts(self) -> dict[str, MockAlert]:
        """初始化模拟告警数据"""
        now = time.time()
        return {
            "ALT-001": MockAlert(
                alert_id="ALT-001",
                alert_name="CPU使用率过高",
                alert_type="CPU_HIGH",
                severity="warning",
                instance_id="INS-003",
                instance_name="PROD-ANALYTICS-DB",
                occurred_at=now - 300,
                metric_value=78.9,
                threshold=75.0,
                message="CPU使用率达到78.9%，超过阈值75%",
                status="active",
            ),
            "ALT-002": MockAlert(
                alert_id="ALT-002",
                alert_name="锁等待超时",
                alert_type="LOCK_WAIT_TIMEOUT",
                severity="warning",
                instance_id="INS-001",
                instance_name="PROD-ORDER-DB",
                occurred_at=now - 600,
                metric_value=120.5,
                threshold=60.0,
                message="实例发生锁等待超时，当前等待时间120秒",
                status="active",
            ),
        }
    
    # ==================== 实例管理 API ====================
    
    async def get_instance(self, instance_id: str) -> Optional[dict]:
        """获取实例详情"""
        instance = self._instances.get(instance_id)
        if not instance:
            return None
        
        # 模拟实时数据波动
        instance.cpu_usage = min(100, max(0, instance.cpu_usage + random.uniform(-5, 5)))
        instance.memory_usage = min(100, max(0, instance.memory_usage + random.uniform(-2, 2)))
        instance.connections = max(0, instance.connections + random.randint(-10, 10))
        
        return {
            "instance_id": instance.instance_id,
            "instance_name": instance.instance_name,
            "db_type": instance.db_type,
            "version": instance.version,
            "status": instance.status,
            "host": instance.host,
            "port": instance.port,
            "metrics": {
                "cpu_usage_percent": round(instance.cpu_usage, 2),
                "memory_usage_percent": round(instance.memory_usage, 2),
                "disk_usage_percent": round(instance.disk_usage, 2),
                "connections": instance.connections,
                "max_connections": instance.max_connections,
            },
            "uptime_seconds": instance.uptime_seconds,
            "created_at": instance.created_at,
            "timestamp": time.time(),
        }
    
    async def list_instances(self, status: Optional[str] = None) -> list[dict]:
        """列出实例"""
        result = []
        for instance in self._instances.values():
            if status and instance.status != status:
                continue
            result.append({
                "instance_id": instance.instance_id,
                "instance_name": instance.instance_name,
                "db_type": instance.db_type,
                "status": instance.status,
                "host": instance.host,
                "port": instance.port,
            })
        return result
    
    async def get_instance_metrics(
        self,
        instance_id: str,
        metrics: Optional[list[str]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> dict:
        """获取实例指标历史"""
        instance = self._instances.get(instance_id)
        if not instance:
            return {}
        
        # 生成模拟历史数据
        now = time.time()
        if not end_time:
            end_time = now
        if not start_time:
            start_time = now - 3600  # 默认1小时
        
        # 生成60个数据点
        points = []
        step = (end_time - start_time) / 60
        for i in range(60):
            ts = start_time + step * i
            points.append({
                "timestamp": ts,
                "cpu": round(instance.cpu_usage + random.uniform(-10, 10), 2),
                "memory": round(instance.memory_usage + random.uniform(-5, 5), 2),
                "connections": max(0, instance.connections + random.randint(-20, 20)),
            })
        
        return {
            "instance_id": instance_id,
            "metrics": metrics or ["cpu", "memory", "connections"],
            "data_points": points,
            "start_time": start_time,
            "end_time": end_time,
        }
    
    # ==================== 会话管理 API ====================
    
    async def get_sessions(
        self,
        instance_id: str,
        limit: int = 20,
        filter_expr: Optional[str] = None,
    ) -> dict:
        """获取会话列表"""
        sessions = [
            {
                "sid": 1001 + i,
                "serial": 2001 + i,
                "username": f"app_user_{i%3}",
                "status": "ACTIVE" if i % 3 != 0 else "INACTIVE",
                "program": f"python-{i}.exe",
                "sql_id": f"sql_{'a'*8}_{i}" if i % 4 != 0 else None,
                "wait_event": "db file sequential read" if i % 5 == 0 else None,
                "seconds_in_wait": random.randint(0, 300) if i % 5 == 0 else 0,
                "machine": f"app-server-{i%3+1}",
                "logon_time": time.time() - random.randint(60, 86400),
                "client_ip": f"192.168.1.{100+i}",
            }
            for i in range(min(limit, 50))
        ]
        
        return {
            "instance_id": instance_id,
            "sessions": sessions,
            "total": len(sessions),
            "active_count": sum(1 for s in sessions if s["status"] == "ACTIVE"),
            "timestamp": time.time(),
        }
    
    async def get_session_detail(self, instance_id: str, sid: int, serial: int) -> dict:
        """获取会话详情"""
        return {
            "sid": sid,
            "serial": serial,
            "username": "app_user_0",
            "status": "ACTIVE",
            "program": "python-0.exe",
            "sql_id": f"sql_{'a'*8}_0",
            "sql_text": "SELECT * FROM orders WHERE status = 'pending' AND created_at > SYSDATE - 1",
            "wait_event": "db file sequential read",
            "wait_seconds": 45,
            "machine": "app-server-1",
            "logon_time": time.time() - 3600,
            "client_ip": "192.168.1.100",
            "background_process": False,
            "osuser": "appuser",
            "process": "12345",
        }
    
    # ==================== 锁管理 API ====================
    
    async def get_locks(self, instance_id: str, include_blocker: bool = True) -> dict:
        """获取锁等待信息"""
        locks = [
            {
                "wait_sid": 1001,
                "wait_serial": 2001,
                "wait_sql_id": f"sql_{'a'*8}",
                "lock_type": "TX",
                "mode_held": "Exclusive",
                "mode_requested": "Share",
                "lock_id1": "12345",
                "lock_id2": "67890",
                "blocker_sid": 1002 if include_blocker else None,
                "blocker_serial": 2002 if include_blocker else None,
                "blocker_sql_id": f"sql_{'b'*8}" if include_blocker else None,
                "wait_seconds": 120,
                "chain_length": 2,
            }
        ]
        
        return {
            "instance_id": instance_id,
            "locks": locks,
            "total_blocked": len(locks),
            "timestamp": time.time(),
        }
    
    # ==================== 告警管理 API ====================
    
    async def get_alerts(
        self,
        instance_id: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """获取告警列表"""
        result = []
        for alert in self._alerts.values():
            if instance_id and alert.instance_id != instance_id:
                continue
            if severity and alert.severity != severity:
                continue
            if status and alert.status != status:
                continue
            result.append({
                "alert_id": alert.alert_id,
                "alert_name": alert.alert_name,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "instance_id": alert.instance_id,
                "instance_name": alert.instance_name,
                "occurred_at": alert.occurred_at,
                "metric_value": alert.metric_value,
                "threshold": alert.threshold,
                "message": alert.message,
                "status": alert.status,
            })
        return result[:limit]
    
    async def get_alert_detail(self, alert_id: str) -> Optional[dict]:
        """获取告警详情"""
        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        
        return {
            "alert_id": alert.alert_id,
            "alert_name": alert.alert_name,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "instance_id": alert.instance_id,
            "instance_name": alert.instance_name,
            "occurred_at": alert.occurred_at,
            "metric_value": alert.metric_value,
            "threshold": alert.threshold,
            "message": alert.message,
            "status": alert.status,
            "附加信息": {
                "duration_seconds": int(time.time() - alert.occurred_at),
                "acknowledged": False,
                "acknowledged_by": None,
                "acknowledged_at": None,
                "resolved_at": None,
            },
        }
    
    # ==================== SQL监控 API ====================
    
    async def get_slow_sql(
        self,
        instance_id: str,
        limit: int = 10,
        order_by: str = "elapsed_time",
    ) -> dict:
        """获取慢SQL"""
        slow_sqls = [
            {
                "sql_id": f"sql_{'a'*(12-i)}",
                "sql_text": f"SELECT * FROM orders WHERE status = 'pending' AND created_at > SYSDATE - {i}...",
                "executions": 1000 - i * 100,
                "elapsed_time_sec": round(30.5 - i * 3, 2),
                "avg_elapsed_sec": round((30.5 - i * 3) / max(1000 - i * 100, 1), 3),
                "disk_reads": 50000 - i * 5000,
                "buffer_gets": 100000 - i * 10000,
                "rows_processed": 10000 - i * 1000,
                "first_load_time": time.time() - 86400 * (i + 1),
                "last_active_time": time.time() - 3600 * (i + 1),
            }
            for i in range(min(limit, 10))
        ]
        
        return {
            "instance_id": instance_id,
            "slow_sqls": slow_sqls,
            "count": len(slow_sqls),
            "order_by": order_by,
            "timestamp": time.time(),
        }
    
    async def get_sql_plan(self, sql_id: str, instance_id: Optional[str] = None) -> dict:
        """获取SQL执行计划"""
        return {
            "sql_id": sql_id,
            "instance_id": instance_id,
            "plan": [
                {
                    "id": 0,
                    "operation": "SELECT",
                    "object_name": None,
                    "optimizer": "ALL_ROWS",
                    "cost": 100,
                    "cardinality": 1000,
                    "bytes": 50000,
                },
                {
                    "id": 1,
                    "operation": "TABLE ACCESS FULL",
                    "object_name": "ORDERS",
                    "optimizer": "ALL_ROWS",
                    "cost": 100,
                    "cardinality": 1000,
                    "filter": "STATUS='pending'",
                },
            ],
            "timestamp": time.time(),
        }
    
    # ==================== 复制状态 API ====================
    
    async def get_replication_status(self, instance_id: str) -> dict:
        """获取复制状态"""
        return {
            "instance_id": instance_id,
            "role": "primary",
            "replication_enabled": True,
            "replicas": [
                {
                    "replica_id": f"REP-{i:03d}",
                    "host": f"192.168.1.{101+i}",
                    "port": 3306,
                    "role": "read_replica",
                    "status": "streaming",
                    "lag_seconds": round(random.uniform(0.1, 5.0), 2),
                    "lag_bytes": random.randint(1024, 102400),
                    "last_heartbeat": time.time() - random.uniform(0.1, 5.0),
                }
                for i in range(2)
            ],
            "ha_enabled": True,
            "ha_role": "primary",
            "timestamp": time.time(),
        }
    
    # ==================== 容量管理 API - Round 14 新增 ====================

    async def get_storage_analysis(self, instance_id: str, db_type: str = "mysql") -> dict:
        """获取存储容量分析"""
        storage_data = self._get_mock_storage(db_type)
        return {
            "instance_id": instance_id,
            "db_type": db_type,
            "storage": storage_data,
            "total_used_gb": sum(s["used_gb"] for s in storage_data),
            "total_capacity_gb": sum(s["total_gb"] for s in storage_data),
            "timestamp": time.time(),
        }

    async def get_capacity_growth(self, instance_id: str, db_type: str = "mysql", days: int = 90) -> dict:
        """获取历史增长数据"""
        history = self._generate_growth_history(db_type, days)
        return {
            "instance_id": instance_id,
            "db_type": db_type,
            "history": history,
            "prediction_days": days,
            "timestamp": time.time(),
        }

    def _get_mock_storage(self, db_type: str) -> list[dict]:
        """生成模拟存储数据"""
        import random
        if db_type == "mysql":
            return [
                {"name": "数据文件 (InnoDB)", "used_gb": 256.5, "total_gb": 500.0, "usage_percent": 51.3, "mount_point": "/data/mysql"},
                {"name": "日志文件 (Redo/Undo)", "used_gb": 80.2, "total_gb": 200.0, "usage_percent": 40.1, "mount_point": "/data/mysql_logs"},
                {"name": "系统表空间", "used_gb": 12.8, "total_gb": 20.0, "usage_percent": 64.0, "mount_point": "/data/mysql"},
                {"name": "临时表空间", "used_gb": 5.2, "total_gb": 50.0, "usage_percent": 10.4, "mount_point": "/data/mysql_temp"},
                {"name": "Binlog存储", "used_gb": 180.0, "total_gb": 200.0, "usage_percent": 90.0, "mount_point": "/data/binlog"},
            ]
        elif db_type == "postgresql":
            return [
                {"name": "数据目录 (PGDATA)", "used_gb": 320.0, "total_gb": 500.0, "usage_percent": 64.0, "mount_point": "/var/lib/postgresql/data"},
                {"name": "WAL日志", "used_gb": 45.0, "total_gb": 100.0, "usage_percent": 45.0, "mount_point": "/var/lib/postgresql/wal"},
                {"name": "表空间 main", "used_gb": 280.0, "total_gb": 400.0, "usage_percent": 70.0, "mount_point": "/var/lib/postgresql/tbs_main"},
                {"name": "临时文件存储", "used_gb": 8.5, "total_gb": 50.0, "usage_percent": 17.0, "mount_point": "/var/lib/postgresql/temp"},
            ]
        else:  # oracle
            return [
                {"name": "SYSTEM表空间", "used_gb": 15.2, "total_gb": 20.0, "usage_percent": 76.0, "mount_point": "+DATA"},
                {"name": "SYSAUX表空间", "used_gb": 22.5, "total_gb": 30.0, "usage_percent": 75.0, "mount_point": "+DATA"},
                {"name": "USERS表空间", "used_gb": 8.0, "total_gb": 10.0, "usage_percent": 80.0, "mount_point": "+DATA"},
                {"name": "UNDOTBS1", "used_gb": 35.0, "total_gb": 100.0, "usage_percent": 35.0, "mount_point": "+DATA"},
                {"name": "TEMP表空间", "used_gb": 3.2, "total_gb": 50.0, "usage_percent": 6.4, "mount_point": "+DATA"},
                {"name": "ARCHIVELOG存储", "used_gb": 95.0, "total_gb": 100.0, "usage_percent": 95.0, "mount_point": "+FRA"},
            ]

    def _generate_growth_history(self, db_type: str, days: int) -> list[dict]:
        """生成历史增长数据"""
        import random
        base_size = 200.0
        history = []
        for i in range(min(days, 30)):  # 最多30天历史
            day = i - min(days, 30) + 1
            size = base_size + (min(days, 30) - 1 - day) * 1.0 + random.uniform(-0.3, 0.5)
            history.append({"day": day, "size_gb": round(size, 2)})
        return history

    # ==================== 表空间 API ====================
    
    async def get_tablespaces(self, instance_id: str, tablespace_name: Optional[str] = None) -> dict:
        """获取表空间信息"""
        tablespaces = [
            {
                "tablespace_name": name,
                "status": "ONLINE",
                "total_size_mb": total,
                "used_size_mb": int(total * usage),
                "free_size_mb": int(total * (1 - usage)),
                "usage_percent": usage * 100,
                "auto_extensible": True,
                "max_size_mb": total * 4,
            }
            for name, total, usage in [
                ("SYSTEM", 10240, 0.80),
                ("USERS", 5120, 0.60),
                ("UNDO_TBS", 8192, 0.50),
                ("TEMP_TBS", 4096, 0.125),
            ]
            if not tablespace_name or name == tablespace_name
        ]
        
        return {
            "instance_id": instance_id,
            "tablespaces": tablespaces,
            "total_count": len(tablespaces),
            "timestamp": time.time(),
        }
    
    # ==================== 备份状态 API ====================
    
    async def get_backup_status(self, instance_id: str, backup_type: Optional[str] = None) -> dict:
        """获取备份状态"""
        backups = [
            {
                "backup_id": f"BK-{int(time.time()) - 86400}",
                "backup_type": "full",
                "status": "completed",
                "start_time": time.time() - 86400,
                "end_time": time.time() - 86400 + 3600,
                "duration_seconds": 3600,
                "size_mb": 1024 * 15,
                "backupset_location": "/backup/full_latest",
                "device_type": "disk",
            },
            {
                "backup_id": f"BK-{int(time.time()) - 172800}",
                "backup_type": "full",
                "status": "completed",
                "start_time": time.time() - 172800,
                "end_time": time.time() - 172800 + 4000,
                "duration_seconds": 4000,
                "size_mb": 1024 * 14,
                "backupset_location": "/backup/full_20260326",
                "device_type": "disk",
            },
        ]
        
        if backup_type:
            backups = [b for b in backups if b["backup_type"] == backup_type]
        
        return {
            "instance_id": instance_id,
            "backups": backups,
            "total": len(backups),
            "latest_full_backup": backups[0] if backups else None,
            "timestamp": time.time(),
        }
    
    # ==================== 审计日志 API ====================
    
    async def get_audit_logs(
        self,
        instance_id: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        operation_type: Optional[str] = None,
        limit: int = 50,
    ) -> dict:
        """获取审计日志"""
        operations = ["LOGON", "LOGOFF", "SELECT", "INSERT", "UPDATE", "DELETE", "DDL"]
        
        if not end_time:
            end_time = time.time()
        if not start_time:
            start_time = end_time - 86400
        
        logs = [
            {
                "audit_id": f"AUD-{int(start_time + (end_time - start_time) * i / limit)}",
                "timestamp": start_time + (end_time - start_time) * i / limit,
                "user": f"app_user_{i%3}",
                "user_host": f"192.168.1.{20+i%10}",
                "operation": operation_type or operations[i % len(operations)],
                "object_owner": "app_schema" if i % 3 == 0 else "public",
                "object_name": f"table_{i%10}" if i % 4 != 0 else None,
                "status": "SUCCESS" if i % 10 != 0 else "FAILED",
                "client_ip": f"10.0.0.{i%20}",
            }
            for i in range(min(limit, 50))
        ]
        
        return {
            "instance_id": instance_id,
            "logs": logs,
            "total": len(logs),
            "start_time": start_time,
            "end_time": end_time,
            "timestamp": time.time(),
        }
    
    # ==================== 健康检查 ====================
    
    async def health_check(self) -> dict:
        """健康检查"""
        return {
            "status": "ok",
            "service": "javis-db-mock-api",
            "timestamp": time.time(),
        }
    
    # ==================== 告警确认/解决 ====================
    
    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str, comment: str = "") -> dict:
        """确认告警"""
        return {
            "alert_id": alert_id,
            "acknowledged_by": acknowledged_by,
            "comment": comment,
            "acknowledged_at": time.time(),
            "status": "acknowledged",
        }
    
    async def resolve_alert(self, alert_id: str, resolved_by: str, resolution: str, resolution_type: str = "fixed") -> dict:
        """解决告警"""
        return {
            "alert_id": alert_id,
            "resolved_by": resolved_by,
            "resolution": resolution,
            "resolution_type": resolution_type,
            "resolved_at": time.time(),
            "status": "resolved",
        }
    
    # ==================== 参数管理 ====================
    
    async def get_parameters(self, instance_id: str, category: Optional[str] = None) -> dict:
        """获取参数列表"""
        params = [
            {"name": "max_connections", "value": "500", "category": "connection", "description": "最大连接数"},
            {"name": "innodb_buffer_pool_size", "value": "134217728", "category": "memory", "description": "InnoDB缓冲池大小"},
            {"name": "query_cache_size", "value": "16777216", "category": "query", "description": "查询缓存大小"},
            {"name": "log_error", "value": "/var/log/mysql/error.log", "category": "logging", "description": "错误日志路径"},
            {"name": "slow_query_log", "value": "ON", "category": "logging", "description": "慢查询日志"},
        ]
        
        if category:
            params = [p for p in params if p["category"] == category]
        
        return {
            "instance_id": instance_id,
            "parameters": params,
            "total": len(params),
            "timestamp": time.time(),
        }
    
    async def update_parameter(self, instance_id: str, param_name: str, param_value: str) -> dict:
        """更新参数"""
        return {
            "instance_id": instance_id,
            "param_name": param_name,
            "param_value": param_value,
            "status": "pending_reboot",
            "message": f"参数 {param_name} 已更新，需要重启实例生效",
            "timestamp": time.time(),
        }
    
    # ==================== 巡检管理 ====================
    
    async def get_inspection_results(self, instance_id: str) -> dict:
        """获取巡检结果"""
        return {
            "instance_id": instance_id,
            "inspection_id": f"INS-{int(time.time())}",
            "status": "completed",
            "score": 85,
            "items": [
                {"category": "性能", "item": "CPU使用率", "status": "warning", "message": "CPU使用率偏高"},
                {"category": "性能", "item": "内存使用率", "status": "normal", "message": "正常"},
                {"category": "可用性", "item": "实例状态", "status": "normal", "message": "运行中"},
                {"category": "安全", "item": "密码策略", "status": "normal", "message": "符合要求"},
            ],
            "timestamp": time.time(),
        }
    
    async def trigger_inspection(self, instance_id: str) -> dict:
        """触发巡检"""
        return {
            "instance_id": instance_id,
            "inspection_id": f"INS-{int(time.time())}",
            "status": "triggered",
            "message": "巡检任务已触发，正在执行中",
            "estimated_duration_seconds": 60,
            "timestamp": time.time(),
        }
    
    # ==================== 工单管理 ====================
    
    async def list_workorders(self, instance_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        """列出工单"""
        workorders = [
            {
                "workorder_id": "WO-001",
                "instance_id": "INS-001",
                "type": "parameter_change",
                "title": "调整最大连接数",
                "status": "pending_approval",
                "requester": "admin",
                "created_at": time.time() - 86400,
            },
            {
                "workorder_id": "WO-002",
                "instance_id": "INS-002",
                "type": "backup",
                "title": "执行全量备份",
                "status": "completed",
                "requester": "admin",
                "created_at": time.time() - 172800,
            },
        ]
        
        if instance_id:
            workorders = [w for w in workorders if w["instance_id"] == instance_id]
        if status:
            workorders = [w for w in workorders if w["status"] == status]
        
        return workorders
    
    async def get_workorder_detail(self, workorder_id: str) -> dict:
        """获取工单详情"""
        return {
            "workorder_id": workorder_id,
            "instance_id": "INS-001",
            "type": "parameter_change",
            "title": "调整最大连接数",
            "description": "将max_connections从500调整为800",
            "status": "pending_approval",
            "requester": "admin",
            "approver": None,
            "created_at": time.time() - 86400,
            "approved_at": None,
            "completed_at": None,
            "steps": [
                {"step": 1, "action": "修改参数", "status": "completed"},
                {"step": 2, "action": "审批", "status": "pending"},
                {"step": 3, "action": "重启实例", "status": "pending"},
            ],
            "timestamp": time.time(),
        }


# 单例模式（线程安全）
_mock_client: Optional[MockJavisClient] = None
_mock_client_lock = threading.Lock()


def get_mock_javis_client() -> MockJavisClient:
    """获取Mock客户端单例（线程安全）"""
    global _mock_client
    if _mock_client is None:
        with _mock_client_lock:
            if _mock_client is None:  # 二次检查
                _mock_client = MockJavisClient()
    return _mock_client
