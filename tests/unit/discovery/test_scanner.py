"""
Unit tests for DatabaseScanner
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.discovery.scanner import DatabaseScanner, DiscoveredInstance, DBType

# Check if psutil is available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class TestDatabaseScanner:
    """Test cases for DatabaseScanner"""

    def test_init_default(self):
        """Test initialization with defaults"""
        scanner = DatabaseScanner()
        assert scanner.scan_timeout == 2.0
        assert scanner.max_concurrent == 50
        assert 5432 in scanner.ports
        assert 3306 in scanner.ports

    def test_init_custom(self):
        """Test initialization with custom parameters"""
        scanner = DatabaseScanner(
            ports=[5432, 3306],
            scan_timeout=5.0,
            max_concurrent=100,
        )
        assert scanner.ports == [5432, 3306]
        assert scanner.scan_timeout == 5.0
        assert scanner.max_concurrent == 100

    def test_discovered_instance_id(self):
        """Test DiscoveredInstance instance_id property"""
        instance = DiscoveredInstance(
            db_type=DBType.POSTGRESQL,
            host="localhost",
            port=5432,
        )
        assert instance.instance_id == "postgresql:localhost:5432"

    def test_discovered_instance_id_ipv6(self):
        """Test DiscoveredInstance with IPv6 host"""
        instance = DiscoveredInstance(
            db_type=DBType.MYSQL,
            host="::1",
            port=3306,
        )
        assert instance.instance_id == "mysql:::1:3306"

    def test_default_db_ports(self):
        """Test default DB ports mapping"""
        assert DatabaseScanner.DEFAULT_DB_PORTS[5432] == DBType.POSTGRESQL
        assert DatabaseScanner.DEFAULT_DB_PORTS[3306] == DBType.MYSQL
        assert DatabaseScanner.DEFAULT_DB_PORTS[1521] == DBType.ORACLE

    def test_process_patterns(self):
        """Test process name patterns"""
        assert DBType.POSTGRESQL in DatabaseScanner.PROCESS_PATTERNS
        assert DBType.MYSQL in DatabaseScanner.PROCESS_PATTERNS
        assert DBType.ORACLE in DatabaseScanner.PROCESS_PATTERNS
        assert "postgres" in DatabaseScanner.PROCESS_PATTERNS[DBType.POSTGRESQL]
        assert "mysqld" in DatabaseScanner.PROCESS_PATTERNS[DBType.MYSQL]

    @pytest.mark.asyncio
    async def test_is_port_open_success(self):
        """Test port open detection when port is open"""
        scanner = DatabaseScanner()

        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0

        mock_socket_class = MagicMock(return_value=mock_sock_instance)

        with patch('src.discovery.scanner.socket.socket', mock_socket_class):
            result = await scanner._is_port_open("localhost", 5432)
            assert result is True
            mock_sock_instance.settimeout.assert_called_once_with(scanner.scan_timeout)
            mock_sock_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_port_open_failure(self):
        """Test port open detection when port is closed"""
        scanner = DatabaseScanner()

        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 1

        mock_socket_class = MagicMock(return_value=mock_sock_instance)

        with patch('src.discovery.scanner.socket.socket', mock_socket_class):
            result = await scanner._is_port_open("localhost", 5432)
            assert result is False

    @pytest.mark.asyncio
    async def test_is_port_open_timeout(self):
        """Test port open detection with timeout"""
        scanner = DatabaseScanner()

        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.side_effect = TimeoutError()

        mock_socket_class = MagicMock(return_value=mock_sock_instance)

        with patch('src.discovery.scanner.socket.socket', mock_socket_class):
            result = await scanner._is_port_open("localhost", 5432)
            assert result is False

    @pytest.mark.asyncio
    async def test_scan_ports_returns_discovered(self):
        """Test scan_ports returns list of DiscoveredInstance"""
        scanner = DatabaseScanner(ports=[5432])

        with patch.object(scanner, '_is_port_open', return_value=True):
            results = await scanner.scan_ports("localhost")
            assert len(results) == 1
            assert results[0].port == 5432
            assert results[0].db_type == DBType.POSTGRESQL

    @pytest.mark.asyncio
    async def test_scan_ports_empty_when_no_open_ports(self):
        """Test scan_ports returns empty when no ports open"""
        scanner = DatabaseScanner(ports=[5432, 3306])

        with patch.object(scanner, '_is_port_open', return_value=False):
            results = await scanner.scan_ports("localhost")
            assert len(results) == 0

    @pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil not installed")
    def test_scan_processes_empty_when_no_db_processes(self):
        """Test scan_processes returns empty when no DB processes"""
        scanner = DatabaseScanner()

        with patch('src.discovery.scanner.psutil.process_iter') as mock_iter:
            mock_iter.return_value = []
            results = scanner.scan_processes()
            assert len(results) == 0

    @pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil not installed")
    def test_scan_processes_finds_postgres(self):
        """Test scan_processes finds PostgreSQL process"""
        scanner = DatabaseScanner()

        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_proc.name.return_value = "postgres"
        mock_proc.exe.return_value = "/usr/lib/postgresql/16/bin/postgres"
        mock_proc.info = {"name": "postgres", "pid": 1234, "exe": "/usr/lib/postgresql/16/bin/postgres", "cmdline": []}

        mock_conn = MagicMock()
        mock_conn.status = "LISTEN"
        mock_conn.laddr.port = 5432
        mock_proc.net_connections.return_value = [mock_conn]

        with patch('src.discovery.scanner.psutil.process_iter', return_value=[mock_proc]):
            results = scanner.scan_processes()
            assert len(results) == 1
            assert results[0].db_type == DBType.POSTGRESQL
            assert results[0].pid == 1234

    @pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil not installed")
    def test_scan_processes_finds_mysql(self):
        """Test scan_processes finds MySQL process"""
        scanner = DatabaseScanner()

        mock_proc = MagicMock()
        mock_proc.pid = 5678
        mock_proc.name.return_value = "mysqld"
        mock_proc.exe.return_value = "/usr/sbin/mysqld"
        mock_proc.info = {"name": "mysqld", "pid": 5678, "exe": "/usr/sbin/mysqld", "cmdline": []}

        mock_conn = MagicMock()
        mock_conn.status = "LISTEN"
        mock_conn.laddr.port = 3306
        mock_proc.net_connections.return_value = [mock_conn]

        with patch('src.discovery.scanner.psutil.process_iter', return_value=[mock_proc]):
            results = scanner.scan_processes()
            assert len(results) == 1
            assert results[0].db_type == DBType.MYSQL
            assert results[0].pid == 5678

    @pytest.mark.asyncio
    async def test_scan_local_combines_results(self):
        """Test scan_local combines port and process scan results"""
        scanner = DatabaseScanner(ports=[5432])

        port_instance = DiscoveredInstance(
            db_type=DBType.POSTGRESQL,
            host="localhost",
            port=5432,
            status="reachable",
        )

        proc_instance = DiscoveredInstance(
            db_type=DBType.POSTGRESQL,
            host="localhost",
            port=5432,
            status="process_found",
            pid=1234,
        )

        with patch.object(scanner, 'scan_ports', return_value=[port_instance]):
            with patch.object(scanner, 'scan_processes', return_value=[proc_instance]):
                results = await scanner.scan_local()
                assert len(results) == 1
                # Should prefer the one with PID
                assert results[0].pid == 1234

    @pytest.mark.asyncio
    async def test_scan_local_deduplicates(self):
        """Test scan_local deduplicates results"""
        scanner = DatabaseScanner(ports=[5432, 3306])

        instances = [
            DiscoveredInstance(db_type=DBType.POSTGRESQL, host="localhost", port=5432, status="reachable"),
            DiscoveredInstance(db_type=DBType.POSTGRESQL, host="localhost", port=5432, status="process_found", pid=1234),
            DiscoveredInstance(db_type=DBType.MYSQL, host="localhost", port=3306, status="reachable"),
        ]

        with patch.object(scanner, 'scan_ports', return_value=instances[:2]):
            with patch.object(scanner, 'scan_processes', return_value=instances):
                results = await scanner.scan_local()
                # Should have 2 unique instances (PG and MySQL)
                assert len(results) == 2

    @pytest.mark.asyncio
    async def test_scan_host_custom_ports(self):
        """Test scanning a host with custom ports"""
        scanner = DatabaseScanner(ports=[5432, 3306, 27017])

        with patch.object(scanner, '_is_port_open', return_value=True):
            results = await scanner.scan_host("192.168.1.100", ports=[5432])
            assert len(results) == 1
            assert results[0].host == "192.168.1.100"
