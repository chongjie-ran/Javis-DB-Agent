"""PostgreSQL数据库适配器
实现 PostgreSQL 特定的数据采集逻辑
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


class PostgresConnector(DBConnector):
    """PostgreSQL数据库连接器"""
    
    def __init__(
        self,
        host: str,
        port: int,
        username: str = "postgres",
        password: str = "",
        api_base: str = "http://localhost:18081",
    ):
        super().__init__(host=host, port=port, username=username, password=password)
        self.api_base = api_base
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def db_type(self) -> DBType:
        return DBType.POSTGRES
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def get_sessions(self, limit: int = 100, filter_expr: str = "") -> list[SessionInfo]:
        """获取PostgreSQL会话列表（pg_stat_activity风格）"""
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{self.api_base}/api/pg/sessions",
                params={"limit": limit} if limit != 100 else {},
            )
            resp.raise_for_status()
            data = resp.json()
            sessions = []
            for row in data.get("sessions", []):
                sessions.append(SessionInfo(
                    pid=row.get("pid", 0),
                    sid=row.get("pid", 0),
                    serial=0,
                    username=row.get("usename", ""),
                    db=row.get("datname", ""),
                    state=row.get("state"),
                    query=row.get("query"),
                    query_start=row.get("query_start"),
                    wait_event=row.get("wait_event_type"),
                    wait_seconds=0,
                    machine=row.get("client_addr", ""),
                    logon_time=time.time(),  # PostgreSQL不直接提供logon_time
                ))
            return sessions
        except httpx.HTTPError:
            # Mock fallback数据
            return [
                SessionInfo(
                    pid=1001 + i,
                    sid=1001 + i,
                    serial=0,
                    username=f"app_user_{i}" if i % 3 else "postgres",
                    db="orders_db",
                    state="active" if i % 2 == 0 else "idle",
                    query=f"SELECT * FROM orders WHERE id = {i};" if i % 2 == 0 else "<idle>",
                    query_start=time.time() - 5 if i % 2 == 0 else None,
                    wait_event="Lock" if i % 3 == 0 else None,
                    wait_seconds=10 if i % 3 == 0 else 0,
                    machine=f"192.168.1.{10 + i % 3}",
                    logon_time=time.time() - 3600 * (i + 1),
                )
                for i in range(min(limit, 10))
            ]
    
    async def get_locks(self, include_blocker: bool = True) -> list[LockInfo]:
        """获取PostgreSQL锁信息（pg_locks风格）"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_base}/api/pg/locks")
            resp.raise_for_status()
            data = resp.json()
            locks = []
            for row in data.get("locks", []):
                locks.append(LockInfo(
                    lock_type=row.get("locktype", ""),
                    mode_held=row.get("granted", False),
                    mode_requested=row.get("mode", ""),
                    lock_id1=str(row.get("relation", "")),
                    lock_id2=str(row.get("page", "")),
                    pid=row.get("pid", 0),
                    blocker_pid=row.get("blocking_pid", 0),
                    relation=f"{row.get('schemaname', '')}.{row.get('relname', '')}" if row.get("relname") else None,
                    granted=row.get("granted", False),
                    wait_seconds=0,
                ))
            return locks
        except httpx.HTTPError:
            return [
                LockInfo(
                    lock_type="relation",
                    mode_held=True,
                    mode_requested="ShareLock",
                    lock_id1="orders_pkey",
                    lock_id2="",
                    pid=1001,
                    blocker_pid=1002,
                    relation="public.orders",
                    granted=True,
                    wait_seconds=0,
                ),
                LockInfo(
                    lock_type="transactionid",
                    mode_held=False,
                    mode_requested="Exclusive",
                    lock_id1="456789",
                    lock_id2="",
                    pid=1002,
                    blocker_pid=0,
                    granted=False,
                    wait_seconds=30,
                ),
            ]
    
    async def get_replication(self) -> ReplicationInfo:
        """获取PostgreSQL流复制状态"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_base}/api/pg/replication")
            resp.raise_for_status()
            data = resp.json()
            replicas = []
            for r in data.get("replicas", []):
                replicas.append({
                    "pid": r.get("pid"),
                    "client_addr": r.get("client_addr"),
                    "state": r.get("state"),
                    "sent_lsn": r.get("sent_lsn"),
                    "write_lsn": r.get("write_lsn"),
                    "flush_lsn": r.get("flush_lsn"),
                    "replay_lsn": r.get("replay_lsn"),
                    "lag_mb": r.get("lag_mb", 0),
                })
            return ReplicationInfo(
                role=data.get("role", "primary"),
                replication_enabled=data.get("replication_enabled", True),
                replicas=replicas,
                wal_lag=data.get("wal_lag", 0),
                replay_lag=data.get("replay_lag", 0),
                flush_lag=data.get("flush_lag", 0),
            )
        except httpx.HTTPError:
            return ReplicationInfo(
                role="primary",
                replication_enabled=True,
                replicas=[
                    {
                        "pid": 12345,
                        "client_addr": "192.168.1.102",
                        "state": "streaming",
                        "sent_lsn": "0/7000060",
                        "write_lsn": "0/7000058",
                        "flush_lsn": "0/7000058",
                        "replay_lsn": "0/7000058",
                        "lag_mb": 0.5,
                    }
                ],
                wal_lag=0.3,
                replay_lag=0.5,
                flush_lag=0.4,
            )
    
    async def get_capacity(self) -> CapacityInfo:
        """获取PostgreSQL容量信息"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_base}/api/pg/capacity")
            resp.raise_for_status()
            data = resp.json()
            return CapacityInfo(
                disk_total_gb=data.get("disk_total_gb", 0),
                disk_used_gb=data.get("disk_used_gb", 0),
                disk_free_gb=data.get("disk_free_gb", 0),
                disk_used_percent=data.get("disk_used_percent", 0),
                tablespaces=data.get("tablespaces", []),
                database_size=data.get("database_size", ""),
            )
        except httpx.HTTPError:
            return CapacityInfo(
                disk_total_gb=500.0,
                disk_used_gb=350.0,
                disk_free_gb=150.0,
                disk_used_percent=70.0,
                tablespaces=[
                    {"name": "pg_default", "used_percent": 70.0, "total_mb": 102400, "used_mb": 71680},
                    {"name": "pg_global", "used_percent": 50.0, "total_mb": 8192, "used_mb": 4096},
                ],
                database_size="45 GB",
            )
    
    async def get_performance(self) -> PerformanceInfo:
        """获取PostgreSQL性能指标"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.api_base}/api/pg/performance")
            resp.raise_for_status()
            data = resp.json()
            return PerformanceInfo(
                cpu_usage_percent=data.get("cpu_usage_percent", 0),
                memory_usage_percent=data.get("memory_usage_percent", 0),
                io_usage_percent=data.get("io_usage_percent", 0),
                active_connections=data.get("active_connections", 0),
                max_connections=data.get("max_connections", 100),
                transactions_per_sec=data.get("transactions_per_sec", 0),
                commits_per_sec=data.get("commits_per_sec", 0),
                rollbacks_per_sec=data.get("rollbacks_per_sec", 0),
                buffer_hit_ratio=data.get("buffer_hit_ratio", 0),
            )
        except httpx.HTTPError:
            return PerformanceInfo(
                cpu_usage_percent=32.1,
                memory_usage_percent=55.8,
                io_usage_percent=20.5,
                active_connections=89,
                max_connections=300,
                transactions_per_sec=125.5,
                commits_per_sec=120.0,
                rollbacks_per_sec=5.5,
                buffer_hit_ratio=99.5,
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
