"""
Unit tests for LocalRegistry
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timezone

from src.discovery.registry import LocalRegistry, ManagedInstance
from src.discovery.scanner import DBType
from src.discovery.identifier import IdentifiedInstance, DiscoveredInstance


class TestLocalRegistry:
    """Test cases for LocalRegistry"""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database file"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def registry(self, temp_db):
        """Create a registry with temporary database"""
        return LocalRegistry(db_path=temp_db)

    def test_init_creates_directory(self, temp_db):
        """Test that initialization creates parent directory"""
        temp_path = Path(temp_db)
        # Use a fresh directory for this specific test
        new_db_dir = temp_path.parent / "test_registry_init_subdir"
        new_db_path = new_db_dir / "test.db"

        registry = LocalRegistry(db_path=str(new_db_path))
        assert new_db_dir.exists()

    def test_register_new_instance(self, registry):
        """Test registering a new instance"""
        instance = ManagedInstance(
            id="test-id-1",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="discovered",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )

        instance_id = registry.register(instance)
        assert instance_id is not None

    def test_register_upsert_existing(self, registry):
        """Test that registering existing instance updates it"""
        instance1 = ManagedInstance(
            id="test-id-1",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.2",
            version_major=16,
            version_minor=2,
            edition="",
            status="discovered",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.register(instance1)

        instance2 = ManagedInstance(
            id="test-id-2",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="onboarded",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        instance_id = registry.register(instance2)

        # Should return same instance (upsert by db_type+host+port)
        retrieved = registry.get_by_id(instance_id)
        assert retrieved is not None
        assert retrieved.version == "16.3"

    def test_get_all(self, registry):
        """Test getting all instances"""
        for i in range(3):
            instance = ManagedInstance(
                id=f"test-id-{i}",
                db_type="postgresql",
                host="localhost",
                port=5432 + i,
                version="16.3",
                version_major=16,
                version_minor=3,
                edition="",
                status="discovered",
                discovered_at=datetime.now(timezone.utc).isoformat(),
            )
            registry.register(instance)

        all_instances = registry.get_all()
        assert len(all_instances) == 3

    def test_get_all_with_status_filter(self, registry):
        """Test getting instances with status filter"""
        instance1 = ManagedInstance(
            id="test-id-1",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="discovered",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.register(instance1)

        instance2 = ManagedInstance(
            id="test-id-2",
            db_type="postgresql",
            host="localhost",
            port=5433,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="onboarded",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.register(instance2)

        discovered = registry.get_all(status_filter="discovered")
        assert len(discovered) == 1
        assert discovered[0].status == "discovered"

    def test_get_by_id(self, registry):
        """Test getting instance by ID"""
        instance = ManagedInstance(
            id="test-id-specific",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="discovered",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.register(instance)

        retrieved = registry.get_by_id("test-id-specific")
        assert retrieved is not None
        assert retrieved.id == "test-id-specific"

    def test_get_by_id_not_found(self, registry):
        """Test getting non-existent instance by ID"""
        retrieved = registry.get_by_id("non-existent-id")
        assert retrieved is None

    def test_get_by_key(self, registry):
        """Test getting instance by unique key"""
        instance = ManagedInstance(
            id="test-id-key",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="discovered",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.register(instance)

        retrieved = registry.get_by_key("postgresql", "localhost", 5432)
        assert retrieved is not None
        assert retrieved.db_type == "postgresql"

    def test_update_status(self, registry):
        """Test updating instance status"""
        instance = ManagedInstance(
            id="test-id-status",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="discovered",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.register(instance)

        success = registry.update_status("test-id-status", "onboarded", "manual_onboard")
        assert success is True

        retrieved = registry.get_by_id("test-id-status")
        assert retrieved.status == "onboarded"

    def test_update_status_not_found(self, registry):
        """Test updating non-existent instance status"""
        success = registry.update_status("non-existent", "onboarded")
        assert success is False

    def test_update_connections(self, registry):
        """Test updating connection count"""
        instance = ManagedInstance(
            id="test-id-conn",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="onboarded",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.register(instance)

        success = registry.update_connections("test-id-conn", 42)
        assert success is True

        retrieved = registry.get_by_id("test-id-conn")
        assert retrieved.current_connections == 42

    def test_remove_soft_delete(self, registry):
        """Test that remove performs soft delete"""
        instance = ManagedInstance(
            id="test-id-remove",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="onboarded",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.register(instance)

        success = registry.remove("test-id-remove")
        assert success is True

        retrieved = registry.get_by_id("test-id-remove")
        assert retrieved.status == "removed"

    def test_get_stats(self, registry):
        """Test getting registry statistics"""
        for i in range(3):
            instance = ManagedInstance(
                id=f"test-id-stats-{i}",
                db_type="postgresql",
                host="localhost",
                port=5432 + i,
                version="16.3",
                version_major=16,
                version_minor=3,
                edition="",
                status="onboarded" if i < 2 else "discovered",
                discovered_at=datetime.now(timezone.utc).isoformat(),
            )
            registry.register(instance)

        stats = registry.get_stats()
        assert stats["total_instances"] == 3
        assert "by_status" in stats
        assert "by_type" in stats

    def test_create_and_finish_scan_session(self, registry):
        """Test scan session lifecycle"""
        session_id = "test-session-123"
        registry.create_scan_session(session_id)

        # Session is created, finish it
        registry.finish_scan_session(
            session_id,
            instances_found=5,
            instances_new=2,
            instances_changed=1,
        )

    def test_get_status_history(self, registry):
        """Test getting status history"""
        instance = ManagedInstance(
            id="test-id-history",
            db_type="postgresql",
            host="localhost",
            port=5432,
            version="16.3",
            version_major=16,
            version_minor=3,
            edition="",
            status="discovered",
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        registry.register(instance)

        # Update status multiple times
        registry.update_status("test-id-history", "onboarded", "first_update")
        registry.update_status("test-id-history", "monitoring", "second_update")

        history = registry.get_status_history("test-id-history")
        assert len(history) >= 2


class TestManagedInstance:
    """Test cases for ManagedInstance dataclass"""

    def test_from_identified(self):
        """Test creating ManagedInstance from IdentifiedInstance"""
        discovered = DiscoveredInstance(
            db_type=DBType.POSTGRESQL,
            host="localhost",
            port=5432,
            version="",
            process_path="/usr/lib/postgresql/16/bin/postgres",
            pid=1234,
        )

        identified = IdentifiedInstance(
            instance=discovered,
            version="16.3",
            version_major=16,
            version_minor=3,
            max_connections=100,
            current_connections=10,
        )

        managed = ManagedInstance.from_identified(identified, status="onboarded")

        assert managed.db_type == "postgresql"
        assert managed.host == "localhost"
        assert managed.port == 5432
        assert managed.version == "16.3"
        assert managed.version_major == 16
        assert managed.version_minor == 3
        assert managed.status == "onboarded"
        assert managed.pid == 1234
        assert managed.onboarded_at is not None

    def test_from_identified_with_discovered_status(self):
        """Test creating ManagedInstance with discovered status"""
        discovered = DiscoveredInstance(
            db_type=DBType.MYSQL,
            host="localhost",
            port=3306,
        )

        identified = IdentifiedInstance(
            instance=discovered,
            version="8.0.35",
            version_major=8,
            version_minor=0,
            edition="MySQL Community",
        )

        managed = ManagedInstance.from_identified(identified, status="discovered")

        assert managed.status == "discovered"
        assert managed.onboarded_at is None
        assert managed.edition == "MySQL Community"
