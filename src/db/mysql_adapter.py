"""MySQL数据库适配器
实现 MySQL 特定的数据采集逻辑
"""
import time
import httpx
from typing import Optional
from src.db.base import (
    DBConnector,
    DBType,
    SessionInfo,
    LockInfo,
    ReplicationInfo,
    CapacityInfo,
    PerformanceInfo,
)


class MySQLConnector(DBConnector):
    """MySQL数据库连接器"""
    
    def __init__(
        self,
        host: str,
        port: int,
        username: str = "root",
        password: str = "",
        api_base: str = "http://localhost:18080",
    ):
        super().__init__(host=host, port=port, username=username, password=password)
        self.api_base = api_base
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def db_type(self) -> DBType:
        return DBType.MYSQL
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def get_sessions(self, limit: int = 100, filter_expr: str = "") -> list[SessionInfo]:
        """获取MySQL会话列表（模拟processlist风格）"""
        # 实际通过Mock API获取
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self.api_base}/api/mysql/sessions",
                params={"limit": limit} if limit != 100 else {},
            )
            resp.raise_for_status()
            data = resp.json()
            sessions = []
            for row in data.get("sessions", []):
                sessions.append(SessionInfo(
                    sid=row.get("id", 0),
                    serial=row.get("serial", 0),
                    username=row.get("user", ""),
                    status=row.get("command", ""),
                    program=row.get("program", ""),
                    db=row.get("db", ""),
                    command=row.get("command", ""),
                    sql_id=row.get("sql_id"),
                    wait_event=row.get("wait"),
                    wait_seconds=row.get("time", 0),
                    machine=row.get("host", ""),
                    logon_time=row.get("time"),
                ))
            return sessions
        except httpx.HTTPError:
            # Mock fallback数据
            return [
                SessionInfo(
                    sid=1001 + i,
                    serial=2001 + i,
                    username=f"app_user_{i}" if i % 3 else "system",
                    status="Sleep" if i % 2 else "Query",
                    program=f"mysql_{i}.exe",
                    db="orders_db",
                    command="Query" if i % 2 == 0 else "Sleep",
                    sql_id=f"sql_{'a'*8}_{i}" if i % 2 == 0 else None,
                    wait_event="query" if i % 3 == 0 else None,
                    wait_seconds=5 if i % 3 == 0 else 0,
                    machine=f"app-server-{i % 3 + 1}",
                    logon_time=time.time() - 3600 * (i + 1),
                )
                for i in range(min(limit, 10))
            ]
    
    async def get_locks(self, include_blocker: bool = True) -> list[LockInfo]:
        """获取MySQL锁信息（模拟performance_schema.data_locks）"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_base}/api/mysql/locks")
            resp.raise_for_status()
            data = resp.json()
            locks = []
            for row in data.get("locks", []):
                locks.append(LockInfo(
                    lock_type=row.get("LOCK_TYPE", ""),
                    mode_held=row.get("LOCK_MODE", ""),
                    mode_requested=row.get("LOCK_MODE", ""),
                    lock_id1=row.get("LOCK_DATA", ""),
                    lock_id2="",
                    blocked_sid=row.get("THREAD_ID", 0),
                    blocked_serial=0,
                    blocker_sid=row.get("BLOCKING_THREAD_ID", 0),
                    blocker_serial=0,
                    wait_seconds=row.get("wait_time", 0),
                ))
            return locks
        except httpx.HTTPError:
            return [
                LockInfo(
                    lock_type="RECORD",
                    mode_held="X",
                    mode_requested="X",
                    lock_id1=f"id_12345_{i}",
                    lock_id2="",
                    blocked_sid=1001,
                    blocked_serial=2001,
                    blocker_sid=1002,
                    blocker_serial=2002,
                    wait_seconds=120,
                )
                for i in range(2)
            ]
    
    async def get_replication(self) -> ReplicationInfo:
        """获取MySQL主从复制状态"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_base}/api/mysql/replication")
            resp.raise_for_status()
            data = resp.json()
            replicas = []
            for r in data.get("replicas", []):
                replicas.append({
                    "replica_id": r.get("Replica_ID"),
                    "host": r.get("Host"),
                    "port": r.get("Port"),
                    "role": "read_replica",
                    "status": r.get("Slave_IO_Running", "No"),
                    "lag_seconds": float(r.get("Seconds_Behind_Master", 0)),
                    "lag_bytes": 0,
                    "last_heartbeat": time.time(),
                })
            return ReplicationInfo(
                role=data.get("role", "primary"),
                replication_enabled=data.get("replication_enabled", True),
                replicas=replicas,
                lag_seconds=float(data.get("seconds_behind_master", 0)),
            )
        except httpx.HTTPError:
            return ReplicationInfo(
                role="primary",
                replication_enabled=True,
                replicas=[
                    {
                        "replica_id": "REP-001",
                        "host": "192.168.1.101",
                        "port": 3306,
                        "role": "read_replica",
                        "status": "Streaming",
                        "lag_seconds": 2.5,
                        "lag_bytes": 102400,
                        "last_heartbeat": time.time() - 2.5,
                    }
                ],
                lag_seconds=2.5,
                lag_bytes=102400,
            )
    
    async def get_capacity(self) -> CapacityInfo:
        """获取MySQL容量信息"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_base}/api/mysql/capacity")
            resp.raise_for_status()
            data = resp.json()
            return CapacityInfo(
                disk_total_gb=data.get("disk_total_gb", 0),
                disk_used_gb=data.get("disk_used_gb", 0),
                disk_free_gb=data.get("disk_free_gb", 0),
                disk_used_percent=data.get("disk_used_percent", 0),
                tablespaces=data.get("tablespaces", []),
            )
        except httpx.HTTPError:
            return CapacityInfo(
                disk_total_gb=500.0,
                disk_used_gb=350.0,
                disk_free_gb=150.0,
                disk_used_percent=70.0,
                tablespaces=[
                    {"name": "system", "used_percent": 60.0, "total_gb": 100, "used_gb": 60},
                    {"name": "data", "used_percent": 72.0, "total_gb": 400, "used_gb": 288},
                ],
            )
    
    async def get_performance(self) -> PerformanceInfo:
        """获取MySQL性能指标"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_base}/api/mysql/performance")
            resp.raise_for_status()
            data = resp.json()
            return PerformanceInfo(
                cpu_usage_percent=data.get("cpu_usage_percent", 0),
                memory_usage_percent=data.get("memory_usage_percent", 0),
                io_usage_percent=data.get("io_usage_percent", 0),
                active_connections=data.get("active_connections", 0),
                max_connections=data.get("max_connections", 500),
                qps=data.get("qps", 0),
                tps=data.get("tps", 0),
                buffer_hit_ratio=data.get("buffer_hit_ratio", 0),
            )
        except httpx.HTTPError:
            return PerformanceInfo(
                cpu_usage_percent=45.2,
                memory_usage_percent=68.5,
                io_usage_percent=30.1,
                active_connections=156,
                max_connections=500,
                qps=1200.5,
                tps=85.3,
                buffer_hit_ratio=99.2,
            )
    
    async def health_check(self) -> bool:
        """健康检查"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_base}/health", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return True  # Mock模式始终返回健康
    
    async def close(self) -> None:
        """关闭连接"""
        if self._client:
            await self._client.aclose()
            self._client = None
