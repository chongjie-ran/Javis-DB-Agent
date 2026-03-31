"""
Unit tests for DatabaseIdentifier
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.discovery.scanner import DatabaseScanner, DiscoveredInstance, DBType
from src.discovery.identifier import DatabaseIdentifier, IdentifiedInstance


class TestDatabaseIdentifier:
    """Test cases for DatabaseIdentifier"""

    def test_init_default(self):
        """Test initialization with defaults"""
        identifier = DatabaseIdentifier()
        assert identifier.scan_timeout == 3.0

    def test_init_custom(self):
        """Test initialization with custom timeout"""
        identifier = DatabaseIdentifier(scan_timeout=5.0)
        assert identifier.scan_timeout == 5.0

    def test_mariadb_indicators(self):
        """Test MariaDB detection indicators"""
        assert "MariaDB" in DatabaseIdentifier.MARIADB_INDICATORS
        assert "maria" in DatabaseIdentifier.MARIADB_INDICATORS
        assert "mariadb" in DatabaseIdentifier.MARIADB_INDICATORS

    def test_identified_instance_creation(self):
        """Test IdentifiedInstance creation"""
        instance = DiscoveredInstance(
            db_type=DBType.POSTGRESQL,
            host="localhost",
            port=5432,
        )
        identified = IdentifiedInstance(
            instance=instance,
            version="16.3",
            version_major=16,
            version_minor=3,
        )
        assert identified.version == "16.3"
        assert identified.version_major == 16
        assert identified.version_minor == 3

    def test_identified_instance_defaults(self):
        """Test IdentifiedInstance default values"""
        instance = DiscoveredInstance(
            db_type=DBType.MYSQL,
            host="localhost",
            port=3306,
        )
        identified = IdentifiedInstance(
            instance=instance,
            version="8.0.35",
            version_major=8,
            version_minor=0,
        )
        assert identified.edition == ""
        assert identified.max_connections == 100
        assert identified.current_connections == 0

    @pytest.mark.asyncio
    async def test_identify_unknown_type(self):
        """Test identify with unknown db_type"""
        identifier = DatabaseIdentifier()
        instance = DiscoveredInstance(
            db_type=DBType.UNKNOWN,
            host="localhost",
            port=9999,
        )
        result = await identifier.identify(instance)
        assert result is None

    @pytest.mark.asyncio
    async def test_identify_oracle_returns_unverified(self):
        """Test identify Oracle returns unverified result"""
        identifier = DatabaseIdentifier()
        instance = DiscoveredInstance(
            db_type=DBType.ORACLE,
            host="localhost",
            port=1521,
        )
        result = await identifier.identify(instance)
        assert result is not None
        assert result.version == "unknown"
        assert instance.status == "unverified_requires_oracle_client"

    @pytest.mark.asyncio
    async def test_identify_all_filters_failures(self):
        """Test identify_all filters out failed identifications"""
        identifier = DatabaseIdentifier()

        pg_instance = DiscoveredInstance(db_type=DBType.POSTGRESQL, host="localhost", port=5432)
        oracle_instance = DiscoveredInstance(db_type=DBType.ORACLE, host="localhost", port=1521)

        with patch.object(identifier, '_identify_postgres', return_value=None):
            with patch.object(identifier, '_identify_oracle', return_value=AsyncMock()()):
                # Mock _identify_oracle to return a proper result
                async def mock_oracle(inst):
                    return IdentifiedInstance(
                        instance=inst,
                        version="unknown",
                        version_major=0,
                        version_minor=0,
                    )
                identifier._identify_oracle = mock_oracle

                results = await identifier.identify_all([pg_instance, oracle_instance])
                # Only oracle should succeed since _identify_postgres returns None
                assert len(results) == 1
