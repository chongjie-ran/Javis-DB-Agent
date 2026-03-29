"""DBConnector 抽象基类
定义统一数据库操作接口，支持 MySQL/PostgreSQL 双引擎
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DBType(Enum):
    """支持的数据库类型"""
    MYSQL = "mysql"
    POSTGRES = "postgresql"


@dataclass
class SessionInfo:
    """会话信息"""
    sid: int = 0
    serial: int = 0
    username: str = ""
    status: str = ""
    program: str = ""
    db: str = ""
    command: str = ""
    sql_id: Optional[str] = None
    wait_event: Optional[str] = None
    wait_seconds: int = 0
    machine: str = ""
    logon_time: float = 0.0
    # PG特有
    pid: int = 0
    query_start: Optional[float] = None
    state: Optional[str] = None
    query: Optional[str] = None


@dataclass
class LockInfo:
    """锁信息"""
    lock_type: str = ""
    mode_held: str = ""
    mode_requested: str = ""
    lock_id1: str = ""
    lock_id2: str = ""
    blocked_sid: int = 0
    blocked_serial: int = 0
    blocker_sid: int = 0
    blocker_serial: int = 0
    wait_seconds: int = 0
    # PG特有
    pid: int = 0
    blocker_pid: int = 0
    relation: Optional[str] = None
    granted: bool = False


@dataclass
class ReplicationInfo:
    """复制状态信息"""
    role: str = ""
    replication_enabled: bool = False
    replicas: list = field(default_factory=list)
    lag_seconds: float = 0.0
    lag_bytes: int = 0
    # PG特有
    wal_lag: float = 0.0
    replay_lag: float = 0.0
    flush_lag: float = 0.0


@dataclass
class CapacityInfo:
    """容量信息"""
    disk_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_free_gb: float = 0.0
    disk_used_percent: float = 0.0
    tablespaces: list = field(default_factory=list)
    # PG特有
    database_size: str = ""


@dataclass
class PerformanceInfo:
    """性能指标"""
    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    io_usage_percent: float = 0.0
    active_connections: int = 0
    max_connections: int = 0
    qps: float = 0.0
    tps: float = 0.0
    buffer_hit_ratio: float = 0.0
    # PG特有
    transactions_per_sec: float = 0.0
    commits_per_sec: float = 0.0
    rollbacks_per_sec: float = 0.0


class DBConnector(ABC):
    """数据库连接器抽象基类
    
    提供统一的数据库操作接口：
    - get_sessions()      - 会话列表
    - get_locks()         - 锁信息
    - get_replication()   - 复制状态
    - get_capacity()      - 容量信息
    - get_performance()   - 性能指标
    """
    
    def __init__(self, host: str, port: int, username: str = "", password: str = ""):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
    
    @property
    @abstractmethod
    def db_type(self) -> DBType:
        """返回数据库类型"""
        pass
    
    @abstractmethod
    async def get_sessions(self, limit: int = 100, filter_expr: str = "") -> list[SessionInfo]:
        """获取会话列表"""
        pass
    
    @abstractmethod
    async def get_locks(self, include_blocker: bool = True) -> list[LockInfo]:
        """获取锁信息"""
        pass
    
    @abstractmethod
    async def get_replication(self) -> ReplicationInfo:
        """获取复制状态"""
        pass
    
    @abstractmethod
    async def get_capacity(self) -> CapacityInfo:
        """获取容量信息"""
        pass
    
    @abstractmethod
    async def get_performance(self) -> PerformanceInfo:
        """获取性能指标"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        pass


def get_db_connector(
    db_type: str,
    host: str,
    port: int,
    username: str = "",
    password: str = "",
) -> DBConnector:
    """工厂函数：根据db_type返回对应的连接器
    
    Args:
        db_type: mysql 或 postgresql
        host: 数据库主机
        port: 端口
        username: 用户名
        password: 密码
    
    Returns:
        DBConnector实例
    
    Raises:
        ValueError: 不支持的数据库类型
    """
    if db_type == "mysql":
        from src.db.mysql_adapter import MySQLConnector
        return MySQLConnector(host=host, port=port, username=username, password=password)
    elif db_type == "postgresql":
        from src.db.postgres_adapter import PostgresConnector
        return PostgresConnector(host=host, port=port, username=username, password=password)
    else:
        raise ValueError(f"Unsupported db_type: {db_type}. Supported: mysql, postgresql")
