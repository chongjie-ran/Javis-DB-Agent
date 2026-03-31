"""
本地数据库扫描器
支持端口扫描 + 进程扫描 双通道发现
"""

import socket
import asyncio
import re
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

try:
    import psutil
except ImportError:
    psutil = None


class DBType(Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    ORACLE = "oracle"
    MARIADB = "mariadb"
    UNKNOWN = "unknown"


@dataclass
class DiscoveredInstance:
    """发现的数据库实例"""
    db_type: DBType
    host: str = "localhost"
    port: int = 0
    version: str = ""
    process_name: str = ""
    pid: Optional[int] = None
    status: str = "unknown"  # unknown / reachable / identified / process_found
    process_path: str = ""
    socket_family: str = "ipv4"  # ipv4 / ipv6

    @property
    def instance_id(self) -> str:
        return f"{self.db_type.value}:{self.host}:{self.port}"


class DatabaseScanner:
    """
    数据库扫描器

    发现策略：
    1. 端口扫描：检测常见数据库端口（5432, 3306, 1521等）
    2. 进程扫描：通过psutil扫描运行中的数据库进程
    3. 连接测试：验证可连接性（无需认证的info查询）
    """

    # 常见数据库端口
    DEFAULT_DB_PORTS = {
        5432: DBType.POSTGRESQL,
        3306: DBType.MYSQL,
        1521: DBType.ORACLE,
        27017: DBType.UNKNOWN,  # MongoDB (预留)
    }

    # 进程名匹配模式
    PROCESS_PATTERNS = {
        DBType.POSTGRESQL: ["postgres", "postmaster", "pg"],
        DBType.MYSQL: ["mysqld", "mariadb"],
        DBType.ORACLE: ["oracle", "tnslsnr"],
    }

    # 扫描超时(秒)
    SCAN_TIMEOUT = 2.0

    def __init__(
        self,
        ports: Optional[List[int]] = None,
        scan_timeout: float = SCAN_TIMEOUT,
        max_concurrent: int = 50,
    ):
        self.ports = ports or list(self.DEFAULT_DB_PORTS.keys())
        self.scan_timeout = scan_timeout
        self.max_concurrent = max_concurrent

    async def scan_ports(self, host: str = "localhost") -> List[DiscoveredInstance]:
        """异步端口扫描，检测常见数据库端口是否开放"""
        results: List[DiscoveredInstance] = []
        sem = asyncio.Semaphore(self.max_concurrent)

        async def check_port(port: int) -> Optional[DiscoveredInstance]:
            async with sem:
                db_type = self.DEFAULT_DB_PORTS.get(port, DBType.UNKNOWN)
                if await self._is_port_open(host, port):
                    return DiscoveredInstance(
                        db_type=db_type,
                        host=host,
                        port=port,
                        status="reachable" if db_type != DBType.UNKNOWN else "unknown",
                    )
                return None

        tasks = [check_port(p) for p in self.ports]
        discovered = await asyncio.gather(*tasks)
        results = [d for d in discovered if d is not None]
        return results

    async def _is_port_open(self, host: str, port: int) -> bool:
        """检测端口是否开放"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.scan_timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except (socket.error, OSError):
            return False

    def scan_processes(self) -> List[DiscoveredInstance]:
        """进程扫描，通过psutil查找运行中的数据库进程"""
        if psutil is None:
            return []
        results: List[DiscoveredInstance] = []
        seen: set = set()

        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
            try:
                name = proc.info["name"] or ""

                for db_type, patterns in self.PROCESS_PATTERNS.items():
                    if any(p.lower() in name.lower() for p in patterns):
                        key = (db_type, name.lower())
                        if key not in seen:
                            seen.add(key)
                            instance = self._proc_to_instance(proc, db_type)
                            if instance:
                                results.append(instance)
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return results

    def _proc_to_instance(
        self, proc: 'psutil.Process', db_type: DBType
    ) -> Optional[DiscoveredInstance]:
        """从进程信息构造DiscoveredInstance"""
        try:
            connections = proc.connections(kind="inet")
            ports = set()
            for conn in connections:
                if conn.status == "LISTEN":
                    ports.add(conn.laddr.port)

            # 优先使用标准端口
            default_port = next(
                (p for p, t in self.DEFAULT_DB_PORTS.items() if t == db_type),
                0
            )
            port = next((p for p in ports if p == default_port), next(iter(ports), 0))

            if not port:
                return None

            return DiscoveredInstance(
                db_type=db_type,
                host="localhost",
                port=port,
                pid=proc.pid,
                process_name=proc.name(),
                process_path=proc.exe() or "",
                status="process_found",
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return None

    async def scan_local(self) -> List[DiscoveredInstance]:
        """
        综合扫描：端口扫描 + 进程扫描
        合并结果，按(db_type, port)去重
        """
        port_results, proc_results = await asyncio.gather(
            self.scan_ports("localhost"),
            asyncio.to_thread(self.scan_processes),
        )

        seen: dict = {}
        all_instances = list(port_results) + list(proc_results)
        for instance in all_instances:
            key = (instance.db_type, instance.port)
            if key not in seen:
                seen[key] = instance
            else:
                # 优先保留有更多信息的实例
                existing = seen[key]
                if instance.pid and not existing.pid:
                    seen[key] = instance
                elif instance.process_path and not existing.process_path:
                    seen[key] = instance

        return list(seen.values())

    async def scan_host(self, host: str, ports: Optional[List[int]] = None) -> List[DiscoveredInstance]:
        """
        扫描指定主机的数据库端口

        Args:
            host: 目标主机
            ports: 要扫描的端口列表，默认为当前实例的ports

        Returns:
            List[DiscoveredInstance]: 发现的实例列表
        """
        ports_to_scan = ports or self.ports
        results: List[DiscoveredInstance] = []
        sem = asyncio.Semaphore(self.max_concurrent)

        async def check_port(port: int) -> Optional[DiscoveredInstance]:
            async with sem:
                db_type = self.DEFAULT_DB_PORTS.get(port, DBType.UNKNOWN)
                if await self._is_port_open(host, port):
                    return DiscoveredInstance(
                        db_type=db_type,
                        host=host,
                        port=port,
                        status="reachable" if db_type != DBType.UNKNOWN else "unknown",
                    )
                return None

        tasks = [check_port(p) for p in ports_to_scan]
        discovered = await asyncio.gather(*tasks, return_exceptions=True)
        results = [d for d in discovered if d is not None and not isinstance(d, Exception)]
        return results
