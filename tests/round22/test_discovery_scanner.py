"""
DatabaseScanner 单元测试
测试端口扫描、进程扫描、去重合并
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.discovery.scanner import DatabaseScanner, DiscoveredInstance, DBType


# ─────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────

def make_instance(
    db_type: DBType,
    port: int,
    status: str = "reachable",
    pid: int | None = None,
    process_path: str = "",
) -> DiscoveredInstance:
    return DiscoveredInstance(
        db_type=db_type,
        host="localhost",
        port=port,
        status=status,
        pid=pid,
        process_path=process_path,
    )


# ─────────────────────────────────────────────
# 测试：DBType 枚举
# ─────────────────────────────────────────────

class TestDBType:
    def test_dbtype_values(self):
        assert DBType.POSTGRESQL.value == "postgresql"
        assert DBType.MYSQL.value == "mysql"
        assert DBType.ORACLE.value == "oracle"
        assert DBType.MARIADB.value == "mariadb"
        assert DBType.UNKNOWN.value == "unknown"

    def test_dbtype_is_enum(self):
        assert isinstance(DBType.POSTGRESQL, DBType)


# ─────────────────────────────────────────────
# 测试：DiscoveredInstance
# ─────────────────────────────────────────────

class TestDiscoveredInstance:
    def test_instance_id_format(self):
        inst = make_instance(DBType.POSTGRESQL, 5432)
        assert inst.instance_id == "postgresql:localhost:5432"

    def test_instance_id_mysql(self):
        inst = make_instance(DBType.MYSQL, 3306)
        assert inst.instance_id == "mysql:localhost:3306"

    def test_instance_defaults(self):
        inst = DiscoveredInstance(db_type=DBType.POSTGRESQL, port=5432)
        assert inst.host == "localhost"
        assert inst.status == "unknown"
        assert inst.pid is None
        assert inst.version == ""


# ─────────────────────────────────────────────
# 测试：DatabaseScanner 初始化
# ─────────────────────────────────────────────

class TestScannerInit:
    def test_default_ports(self):
        scanner = DatabaseScanner()
        assert 5432 in scanner.ports
        assert 3306 in scanner.ports
        assert 1521 in scanner.ports

    def test_custom_ports(self):
        scanner = DatabaseScanner(ports=[5432, 3306])
        assert scanner.ports == [5432, 3306]

    def test_custom_timeout(self):
        scanner = DatabaseScanner(scan_timeout=5.0)
        assert scanner.scan_timeout == 5.0

    def test_custom_max_concurrent(self):
        scanner = DatabaseScanner(max_concurrent=100)
        assert scanner.max_concurrent == 100


# ─────────────────────────────────────────────
# 测试：端口扫描
# ─────────────────────────────────────────────

class TestPortScanning:
    @pytest.mark.asyncio
    async def test_scan_ports_all_closed(self):
        """所有端口关闭时，返回空列表"""
        scanner = DatabaseScanner(ports=[5432, 3306], scan_timeout=0.5)

        # Mock _is_port_open 始终返回 False
        with patch.object(scanner, "_is_port_open", return_value=False):
            results = await scanner.scan_ports("localhost")
            assert results == []

    @pytest.mark.asyncio
    async def test_scan_ports_one_open(self):
        """只有5432开放时，只返回PostgreSQL实例"""
        async def mock_is_port_open(host, port):
            return port == 5432

        scanner = DatabaseScanner(ports=[5432, 3306])
        with patch.object(scanner, "_is_port_open", side_effect=mock_is_port_open):
            results = await scanner.scan_ports("localhost")
            assert len(results) == 1
            assert results[0].port == 5432
            assert results[0].db_type == DBType.POSTGRESQL
            assert results[0].status == "reachable"

    @pytest.mark.asyncio
    async def test_scan_ports_multiple_open(self):
        """多个端口开放时，返回多个实例"""
        async def mock_is_port_open(host, port):
            return port in (5432, 3306)

        scanner = DatabaseScanner(ports=[5432, 3306, 1521])
        with patch.object(scanner, "_is_port_open", side_effect=mock_is_port_open):
            results = await scanner.scan_ports("localhost")
            assert len(results) == 2
            ports = {r.port for r in results}
            assert ports == {5432, 3306}

    @pytest.mark.asyncio
    async def test_scan_ports_unknown_type(self):
        """未知端口返回UNKNOWN类型"""
        scanner = DatabaseScanner(ports=[9999])
        with patch.object(scanner, "_is_port_open", return_value=True):
            results = await scanner.scan_ports("localhost")
            assert len(results) == 1
            assert results[0].db_type == DBType.UNKNOWN
            assert results[0].status == "unknown"


# ─────────────────────────────────────────────
# 测试：进程扫描
# ─────────────────────────────────────────────

class TestProcessScanning:
    def test_scan_processes_psutil_unavailable(self):
        """psutil不可用时返回空列表"""
        scanner = DatabaseScanner()
        import src.discovery.scanner as scanner_module
        original_psutil = scanner_module.psutil
        scanner_module.psutil = None
        try:
            results = scanner.scan_processes()
            assert results == []
        finally:
            scanner_module.psutil = original_psutil

    def test_scan_processes_no_db_processes(self):
        """没有数据库进程时返回空列表"""
        import src.discovery.scanner as scanner_module

        mock_proc = MagicMock()
        mock_proc.info = {"name": "nginx", "exe": "/usr/sbin/nginx"}

        mock_psutil = MagicMock()
        mock_psutil.process_iter = MagicMock(return_value=[mock_proc])

        original_psutil = scanner_module.psutil
        scanner_module.psutil = mock_psutil
        try:
            scanner = DatabaseScanner()
            results = scanner.scan_processes()
            assert results == []
        finally:
            scanner_module.psutil = original_psutil

    def test_scan_processes_finds_postgres(self):
        """能识别postgres进程"""
        import src.discovery.scanner as scanner_module

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.name.return_value = "postgres"
        mock_proc.exe.return_value = "/usr/lib/postgresql/16/bin/postgres"
        mock_proc.info = {"name": "postgres", "exe": "/usr/lib/postgresql/16/bin/postgres"}
        mock_conn = MagicMock()
        mock_conn.status = "LISTEN"
        mock_conn.laddr.port = 5432
        mock_proc.connections.return_value = [mock_conn]

        mock_psutil = MagicMock()
        mock_psutil.process_iter = MagicMock(return_value=[mock_proc])

        original_psutil = scanner_module.psutil
        scanner_module.psutil = mock_psutil
        try:
            scanner = DatabaseScanner()
            results = scanner.scan_processes()
            assert len(results) == 1
            assert results[0].db_type == DBType.POSTGRESQL
            assert results[0].port == 5432
            assert results[0].pid == 12345
            assert results[0].status == "process_found"
        finally:
            scanner_module.psutil = original_psutil

    def test_scan_processes_finds_mysql(self):
        """能识别mysqld进程"""
        import src.discovery.scanner as scanner_module

        mock_proc = MagicMock()
        mock_proc.pid = 23456
        mock_proc.name.return_value = "mysqld"
        mock_proc.exe.return_value = "/usr/sbin/mysqld"
        mock_proc.info = {"name": "mysqld", "exe": "/usr/sbin/mysqld"}
        mock_conn = MagicMock()
        mock_conn.status = "LISTEN"
        mock_conn.laddr.port = 3306
        mock_proc.connections.return_value = [mock_conn]

        mock_psutil = MagicMock()
        mock_psutil.process_iter = MagicMock(return_value=[mock_proc])

        original_psutil = scanner_module.psutil
        scanner_module.psutil = mock_psutil
        try:
            scanner = DatabaseScanner()
            results = scanner.scan_processes()
            assert len(results) == 1
            assert results[0].db_type == DBType.MYSQL
            assert results[0].port == 3306
        finally:
            scanner_module.psutil = original_psutil

    def test_scan_processes_deduplicates_by_name(self):
        """同一进程名只出现一次（去重）"""
        import src.discovery.scanner as scanner_module

        mock_proc1 = MagicMock()
        mock_proc1.pid = 111
        mock_proc1.name.return_value = "postgres"
        mock_proc1.exe.return_value = "/usr/lib/postgresql/16/bin/postgres"
        mock_proc1.info = {"name": "postgres", "exe": "/usr/lib/postgresql/16/bin/postgres"}
        mock_conn = MagicMock()
        mock_conn.status = "LISTEN"
        mock_conn.laddr.port = 5432
        mock_proc1.connections.return_value = [mock_conn]

        mock_proc2 = MagicMock()
        mock_proc2.pid = 222
        mock_proc2.name.return_value = "postgres"
        mock_proc2.exe.return_value = "/usr/lib/postgresql/16/bin/postgres"
        mock_proc2.info = {"name": "postgres", "exe": "/usr/lib/postgresql/16/bin/postgres"}
        mock_proc2.connections.return_value = [mock_conn]

        mock_psutil = MagicMock()
        mock_psutil.process_iter = MagicMock(return_value=[mock_proc1, mock_proc2])

        original_psutil = scanner_module.psutil
        scanner_module.psutil = mock_psutil
        try:
            scanner = DatabaseScanner()
            results = scanner.scan_processes()
            assert len(results) == 1  # 去重后只有1个
        finally:
            scanner_module.psutil = original_psutil


# ─────────────────────────────────────────────
# 测试：综合扫描与去重合并
# ─────────────────────────────────────────────

class TestScanLocal:
    @pytest.mark.asyncio
    async def test_scan_local_combines_port_and_process(self):
        """端口扫描和进程扫描结果合并"""
        port_instances = [make_instance(DBType.POSTGRESQL, 5432, status="reachable")]
        proc_instances = [make_instance(
            DBType.POSTGRESQL, 5432, status="process_found",
            pid=12345, process_path="/usr/bin/postgres"
        )]

        scanner = DatabaseScanner()
        with patch.object(scanner, "scan_ports", return_value=port_instances):
            with patch.object(scanner, "scan_processes", return_value=proc_instances):
                results = await scanner.scan_local()
                assert len(results) == 1
                # 优先保留有pid的实例
                assert results[0].pid == 12345
                assert results[0].process_path == "/usr/bin/postgres"

    @pytest.mark.asyncio
    async def test_scan_local_different_ports_kept_separately(self):
        """不同端口的实例分别保留"""
        port_instances = [
            make_instance(DBType.POSTGRESQL, 5432, status="reachable"),
            make_instance(DBType.MYSQL, 3306, status="reachable"),
        ]
        scanner = DatabaseScanner()
        with patch.object(scanner, "scan_ports", return_value=port_instances):
            with patch.object(scanner, "scan_processes", return_value=[]):
                results = await scanner.scan_local()
                assert len(results) == 2
                ports = {r.port for r in results}
                assert ports == {5432, 3306}

    @pytest.mark.asyncio
    async def test_scan_local_merges_same_type_same_port(self):
        """同一类型同一端口的端口扫描和进程扫描结果合并为一个"""
        port_instances = [make_instance(DBType.POSTGRESQL, 5432, status="reachable")]
        proc_instances = [make_instance(
            DBType.POSTGRESQL, 5432, status="process_found",
            pid=12345, process_path="/usr/bin/postgres"
        )]

        scanner = DatabaseScanner()
        with patch.object(scanner, "scan_ports", return_value=port_instances):
            with patch.object(scanner, "scan_processes", return_value=proc_instances):
                results = await scanner.scan_local()
                assert len(results) == 1
                # 合并后保留进程扫描的详细信息
                assert results[0].db_type == DBType.POSTGRESQL
                assert results[0].pid == 12345

    @pytest.mark.asyncio
    async def test_scan_local_empty_when_no_results(self):
        """端口和进程都没有发现时返回空列表"""
        scanner = DatabaseScanner()
        with patch.object(scanner, "scan_ports", return_value=[]):
            with patch.object(scanner, "scan_processes", return_value=[]):
                results = await scanner.scan_local()
                assert results == []


# ─────────────────────────────────────────────
# 测试：端口映射表
# ─────────────────────────────────────────────

class TestPortMapping:
    def test_default_port_mapping(self):
        assert DatabaseScanner.DEFAULT_DB_PORTS[5432] == DBType.POSTGRESQL
        assert DatabaseScanner.DEFAULT_DB_PORTS[3306] == DBType.MYSQL
        assert DatabaseScanner.DEFAULT_DB_PORTS[1521] == DBType.ORACLE
        assert DatabaseScanner.DEFAULT_DB_PORTS[27017] == DBType.UNKNOWN

    def test_process_patterns(self):
        assert DBType.POSTGRESQL in DatabaseScanner.PROCESS_PATTERNS
        assert DBType.MYSQL in DatabaseScanner.PROCESS_PATTERNS
        assert "postgres" in DatabaseScanner.PROCESS_PATTERNS[DBType.POSTGRESQL]
        assert "mysqld" in DatabaseScanner.PROCESS_PATTERNS[DBType.MYSQL]
