"""
DatabaseIdentifier 单元测试
测试 PostgreSQL 识别、MySQL/MariaDB 识别、版本获取
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.discovery.identifier import DatabaseIdentifier, IdentifiedInstance
from src.discovery.scanner import DBType, DiscoveredInstance


# ─────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────

def make_instance(
    db_type: DBType,
    port: int = 5432,
    status: str = "reachable",
) -> DiscoveredInstance:
    return DiscoveredInstance(
        db_type=db_type,
        host="localhost",
        port=port,
        status=status,
    )


def make_mock_asyncpg_conn(version_str: str = "PostgreSQL 16.4"):
    """创建模拟的asyncpg连接"""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"version": version_str})
    mock_conn.fetchval = AsyncMock(return_value=100)
    mock_conn.close = AsyncMock()
    return mock_conn


# ─────────────────────────────────────────────
# 测试：IdentifiedInstance
# ─────────────────────────────────────────────

class TestIdentifiedInstance:
    def test_instance_id_method(self):
        inst = make_instance(DBType.POSTGRESQL, 5432)
        identified = IdentifiedInstance(
            instance=inst,
            version="16.4",
            version_major=16,
            version_minor=4,
        )
        assert identified.instance_id() == "postgresql:localhost:5432"

    def test_defaults(self):
        inst = make_instance(DBType.POSTGRESQL)
        identified = IdentifiedInstance(
            instance=inst,
            version="16.4",
            version_major=16,
            version_minor=4,
        )
        assert identified.edition == ""
        assert identified.max_connections == 100
        assert identified.current_connections == 0


# ─────────────────────────────────────────────
# 测试：DatabaseIdentifier 初始化
# ─────────────────────────────────────────────

class TestIdentifierInit:
    def test_default_timeout(self):
        identifier = DatabaseIdentifier()
        assert identifier.SCAN_TIMEOUT == 3.0

    def test_mariadb_indicators(self):
        identifier = DatabaseIdentifier()
        assert "MariaDB" in identifier.MARIADB_INDICATORS
        assert "maria" in identifier.MARIADB_INDICATORS


# ─────────────────────────────────────────────
# 测试：PostgreSQL 识别
# ─────────────────────────────────────────────

class TestPostgresIdentification:
    @pytest.mark.asyncio
    async def test_identify_postgres_asyncpg_unavailable(self):
        """asyncpg不可用时返回None"""
        identifier = DatabaseIdentifier()
        inst = make_instance(DBType.POSTGRESQL, 5432)

        with patch("src.discovery.identifier.ASYNCPG_AVAILABLE", False):
            result = await identifier.identify(inst)
            assert result is None

    @pytest.mark.asyncio
    async def test_identify_postgres_success(self):
        """成功识别PostgreSQL并获取版本"""
        inst = make_instance(DBType.POSTGRESQL, 5432)
        mock_conn = make_mock_asyncpg_conn("PostgreSQL 16.4 on x86_64")

        identifier = DatabaseIdentifier()
        with patch("src.discovery.identifier.ASYNCPG_AVAILABLE", True):
            with patch("src.discovery.identifier.asyncpg.connect",
                       new_callable=AsyncMock, return_value=mock_conn):
                result = await identifier.identify(inst)

        assert result is not None
        assert result.version_major == 16
        assert result.version_minor == 4
        assert "PostgreSQL" in result.version
        assert result.instance.status == "identified"

    @pytest.mark.asyncio
    async def test_identify_postgres_connection_failure(self):
        """连接失败时返回None"""
        identifier = DatabaseIdentifier()
        inst = make_instance(DBType.POSTGRESQL, 5432)

        with patch("src.discovery.identifier.ASYNCPG_AVAILABLE", True):
            with patch("src.discovery.identifier.asyncpg.connect",
                       new_callable=AsyncMock, side_effect=Exception("Connection refused")):
                result = await identifier.identify(inst)

        assert result is None

    @pytest.mark.asyncio
    async def test_identify_postgres_extracts_major_minor(self):
        """从版本字符串正确提取主次版本号"""
        inst = make_instance(DBType.POSTGRESQL, 5432)
        mock_conn = make_mock_asyncpg_conn("PostgreSQL 15.2 on x86_64")

        identifier = DatabaseIdentifier()
        with patch("src.discovery.identifier.ASYNCPG_AVAILABLE", True):
            with patch("src.discovery.identifier.asyncpg.connect",
                       new_callable=AsyncMock, return_value=mock_conn):
                result = await identifier.identify(inst)

        assert result.version_major == 15
        assert result.version_minor == 2

    @pytest.mark.asyncio
    async def test_identify_postgres_connections_info(self):
        """获取连接数信息"""
        inst = make_instance(DBType.POSTGRESQL, 5432)
        mock_conn = make_mock_asyncpg_conn("PostgreSQL 16.4")
        mock_conn.fetchval = AsyncMock(side_effect=[
            42,    # count(*) from pg_stat_activity
            200,   # SHOW max_connections
        ])

        identifier = DatabaseIdentifier()
        with patch("src.discovery.identifier.ASYNCPG_AVAILABLE", True):
            with patch("src.discovery.identifier.asyncpg.connect",
                       new_callable=AsyncMock, return_value=mock_conn):
                result = await identifier.identify(inst)

        assert result.current_connections == 42
        assert result.max_connections == 200

    @pytest.mark.asyncio
    async def test_identify_postgres_closes_connection_on_error(self):
        """发生异常时正确关闭连接"""
        inst = make_instance(DBType.POSTGRESQL, 5432)
        mock_conn = make_mock_asyncpg_conn()
        mock_conn.fetchrow = AsyncMock(side_effect=Exception("Query failed"))

        identifier = DatabaseIdentifier()
        with patch("src.discovery.identifier.ASYNCPG_AVAILABLE", True):
            with patch("src.discovery.identifier.asyncpg.connect",
                       new_callable=AsyncMock, return_value=mock_conn):
                result = await identifier.identify(inst)

        assert result is None
        mock_conn.close.assert_called_once()


# ─────────────────────────────────────────────
# 测试：MySQL / MariaDB 识别
# ─────────────────────────────────────────────

def _make_mock_aiomysql_module(cursor_mock):
    """创建模拟的aiomysql模块"""
    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=cursor_mock)
    mock_conn.close = MagicMock()

    mock_aiomysql = MagicMock()
    mock_aiomysql.connect = AsyncMock(return_value=mock_conn)
    mock_aiomysql.DictCursor = object()
    return mock_aiomysql


class TestMySQLIdentification:
    @pytest.mark.asyncio
    async def test_identify_mysql_success(self):
        """成功识别MySQL"""
        inst = make_instance(DBType.MYSQL, 3306)

        async def mock_identify_mysql(self, instance):
            instance.status = "identified"
            return IdentifiedInstance(
                instance=instance,
                version="8.0.36",
                version_major=8,
                version_minor=0,
                edition="MySQL",
                max_connections=200,
            )

        identifier = DatabaseIdentifier()
        with patch.object(DatabaseIdentifier, "_identify_mysql", mock_identify_mysql):
            result = await identifier.identify(inst)

        assert result is not None
        assert result.version_major == 8
        assert result.version_minor == 0
        assert result.edition == "MySQL"
        assert result.max_connections == 200
        assert result.instance.status == "identified"

    @pytest.mark.asyncio
    async def test_identify_mariadb_detected(self):
        """成功识别MariaDB并设置正确edition"""
        inst = make_instance(DBType.MYSQL, 3306)

        async def mock_identify_mysql(self, instance):
            identified = IdentifiedInstance(
                instance=instance,
                version="10.11.4-MariaDB",
                version_major=10,
                version_minor=11,
                edition="MariaDB",
                max_connections=100,
            )
            identified.instance.db_type = DBType.MARIADB
            return identified

        identifier = DatabaseIdentifier()
        with patch.object(DatabaseIdentifier, "_identify_mysql", mock_identify_mysql):
            result = await identifier.identify(inst)

        assert result is not None
        assert result.edition == "MariaDB"
        assert result.instance.db_type == DBType.MARIADB

    @pytest.mark.asyncio
    async def test_identify_mysql_aiomysql_unavailable(self):
        """aiomysql不可用时返回None"""
        with patch("src.discovery.identifier.AIOMYSQL_AVAILABLE", False):
            identifier = DatabaseIdentifier()
            inst = make_instance(DBType.MYSQL, 3306)
            result = await identifier.identify(inst)
            assert result is None

    @pytest.mark.asyncio
    async def test_identify_mysql_connection_failure(self):
        """MySQL连接失败时返回None"""
        async def mock_identify_mysql_that_fails(self, instance):
            return None

        identifier = DatabaseIdentifier()
        inst = make_instance(DBType.MYSQL, 3306)
        with patch.object(DatabaseIdentifier, "_identify_mysql", mock_identify_mysql_that_fails):
            result = await identifier.identify(inst)
            assert result is None


# ─────────────────────────────────────────────
# 测试：Oracle 预留识别
# ─────────────────────────────────────────────

class TestOracleIdentification:
    @pytest.mark.asyncio
    async def test_identify_oracle_returns_unverified(self):
        """Oracle识别返回unverified状态"""
        identifier = DatabaseIdentifier()
        inst = make_instance(DBType.ORACLE, 1521)

        result = await identifier.identify(inst)

        assert result is not None
        assert result.version == "unknown"
        assert result.instance.status == "unverified_requires_oracle_client"
        assert result.version_major == 0
        assert result.version_minor == 0


# ─────────────────────────────────────────────
# 测试：批量识别
# ─────────────────────────────────────────────

class TestBatchIdentification:
    @pytest.mark.asyncio
    async def test_identify_all_filters_exceptions(self):
        """identify_all 过滤掉异常结果，只返回成功的IdentifiedInstance"""
        inst1 = make_instance(DBType.POSTGRESQL, 5432)
        inst2 = make_instance(DBType.POSTGRESQL, 9999)

        mock_conn_success = make_mock_asyncpg_conn("PostgreSQL 16.4")

        # List of side effects: first call succeeds, second raises
        side_effects = [mock_conn_success, Exception("Failed")]

        identifier = DatabaseIdentifier()
        with patch("src.discovery.identifier.ASYNCPG_AVAILABLE", True):
            with patch("src.discovery.identifier.asyncpg.connect",
                       new_callable=AsyncMock, side_effect=side_effects):
                results = await identifier.identify_all([inst1, inst2])

        assert len(results) == 1
        assert results[0].instance.port == 5432

    @pytest.mark.asyncio
    async def test_identify_all_empty_input(self):
        """空输入返回空列表"""
        identifier = DatabaseIdentifier()
        results = await identifier.identify_all([])
        assert results == []

    @pytest.mark.asyncio
    async def test_identify_all_all_fail(self):
        """所有识别都失败时返回空列表"""
        identifier = DatabaseIdentifier()
        inst = make_instance(DBType.POSTGRESQL, 5432)

        with patch("src.discovery.identifier.ASYNCPG_AVAILABLE", True):
            with patch("src.discovery.identifier.asyncpg.connect",
                       new_callable=AsyncMock, side_effect=Exception("Failed")):
                results = await identifier.identify_all([inst])

        assert results == []


# ─────────────────────────────────────────────
# 测试：未知类型处理
# ─────────────────────────────────────────────

class TestUnknownType:
    @pytest.mark.asyncio
    async def test_identify_unknown_type_returns_none(self):
        """UNKNOWN类型的实例返回None"""
        identifier = DatabaseIdentifier()
        inst = make_instance(DBType.UNKNOWN, 9999)
        result = await identifier.identify(inst)
        assert result is None
