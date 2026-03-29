"""Tests for taxonomy repository"""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestTaxonomyRepository:
    """Test TaxonomyRepository CRUD operations"""

    @pytest.fixture
    def mock_db_pool(self):
        """Create a mock database pool"""
        pool = MagicMock()
        return pool

    @pytest.fixture
    def repo(self, mock_db_pool):
        """Create repository with mock pool"""
        from src.knowledge.db.repositories.taxonomy_repo import TaxonomyRepository
        return TaxonomyRepository(db_pool=mock_db_pool)

    def _make_ctx(self, mock_conn):
        """Create async context manager"""
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

    # ===== Entity Type Tests =====

    @pytest.mark.asyncio
    async def test_create_entity_type(self, repo, mock_db_pool):
        """Test creating an entity type"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.commit = AsyncMock()
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        # Mock the SELECT after INSERT
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "os.linux",
            "name": "Linux",
            "category": "os",
            "description": "Linux操作系统",
            "parent_id": None,
            "metadata": {"version": "6.x"},
            "created_at": None,
            "updated_at": None,
        })

        entity = EntityType(
            id="os.linux",
            name="Linux",
            category="os",
            description="Linux操作系统",
            parent_id=None,
            metadata={"version": "6.x"},
        )

        result = await repo.create_entity_type(entity)
        assert result.id == "os.linux"
        assert result.name == "Linux"
        assert mock_conn.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_get_entity_type_by_id(self, repo, mock_db_pool):
        """Test getting entity type by ID"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "os.linux",
            "name": "Linux",
            "category": "os",
            "description": "Linux操作系统",
            "parent_id": None,
            "metadata": '{"version": "6.x"}',
            "created_at": None,
            "updated_at": None,
        })
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        result = await repo.get_entity_type_by_id("os.linux")
        assert result.id == "os.linux"
        assert result.name == "Linux"
        assert result.category == "os"

    @pytest.mark.asyncio
    async def test_list_entity_types(self, repo, mock_db_pool):
        """Test listing all entity types"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                "id": "os.linux",
                "name": "Linux",
                "category": "os",
                "description": "Linux操作系统",
                "parent_id": None,
                "metadata": None,
                "created_at": None,
                "updated_at": None,
            },
            {
                "id": "db.postgresql",
                "name": "PostgreSQL",
                "category": "database",
                "description": "PostgreSQL数据库",
                "parent_id": None,
                "metadata": None,
                "created_at": None,
                "updated_at": None,
            },
        ])
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        results = await repo.list_entity_types()
        assert len(results) == 2
        assert results[0].id == "os.linux"
        assert results[1].id == "db.postgresql"

    @pytest.mark.asyncio
    async def test_update_entity_type(self, repo, mock_db_pool):
        """Test updating an entity type"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.commit = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "os.linux",
            "name": "Linux Updated",
            "category": "os",
            "description": "Updated description",
            "parent_id": None,
            "metadata": None,
            "created_at": None,
            "updated_at": None,
        })
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        entity = EntityType(
            id="os.linux",
            name="Linux Updated",
            category="os",
            description="Updated description",
            parent_id=None,
            metadata=None,
        )

        result = await repo.update_entity_type(entity)
        assert result.name == "Linux Updated"
        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_entity_type(self, repo, mock_db_pool):
        """Test deleting an entity type"""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")
        mock_conn.commit = AsyncMock()
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        result = await repo.delete_entity_type("os.linux")
        assert result is True
        mock_conn.execute.assert_called_once()

    # ===== Resource Type Tests =====

    @pytest.mark.asyncio
    async def test_create_resource_type(self, repo, mock_db_pool):
        """Test creating a resource type"""
        from src.knowledge.db.repositories.taxonomy_repo import ResourceType

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.commit = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "os.linux.cpu",
            "name": "CPU",
            "entity_type_id": "os.linux",
            "category": "hardware",
            "description": "CPU计算资源",
            "metadata": None,
            "created_at": None,
            "updated_at": None,
        })
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        resource = ResourceType(
            id="os.linux.cpu",
            name="CPU",
            entity_type_id="os.linux",
            category="hardware",
            description="CPU计算资源",
            metadata=None,
        )

        result = await repo.create_resource_type(resource)
        assert result.id == "os.linux.cpu"
        assert result.name == "CPU"

    @pytest.mark.asyncio
    async def test_list_resource_types_by_entity(self, repo, mock_db_pool):
        """Test listing resource types by entity ID"""
        from src.knowledge.db.repositories.taxonomy_repo import ResourceType

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                "id": "os.linux.cpu",
                "name": "CPU",
                "entity_type_id": "os.linux",
                "category": "hardware",
                "description": "CPU计算资源",
                "metadata": None,
                "created_at": None,
                "updated_at": None,
            },
            {
                "id": "os.linux.memory",
                "name": "Memory",
                "entity_type_id": "os.linux",
                "category": "hardware",
                "description": "内存资源",
                "metadata": None,
                "created_at": None,
                "updated_at": None,
            },
        ])
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        results = await repo.list_resource_types_by_entity("os.linux")
        assert len(results) == 2
        assert results[0].id == "os.linux.cpu"

    @pytest.mark.asyncio
    async def test_delete_resource_type(self, repo, mock_db_pool):
        """Test deleting a resource type"""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")
        mock_conn.commit = AsyncMock()
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        result = await repo.delete_resource_type("os.linux.cpu")
        assert result is True
        mock_conn.execute.assert_called_once()

    # ===== Observation Point Type Tests =====

    @pytest.mark.asyncio
    async def test_create_observation_point_type(self, repo, mock_db_pool):
        """Test creating an observation point type"""
        from src.knowledge.db.repositories.taxonomy_repo import ObservationPointType

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.commit = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": "os.linux.cpu.load",
            "name": "CPU负载",
            "resource_type_id": "os.linux.cpu",
            "category": "load",
            "unit": "percent",
            "description": "CPU负载观察点",
            "metadata": None,
            "created_at": None,
            "updated_at": None,
        })
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        obs_point = ObservationPointType(
            id="os.linux.cpu.load",
            name="CPU负载",
            resource_type_id="os.linux.cpu",
            category="load",
            unit="percent",
            description="CPU负载观察点",
            metadata=None,
        )

        result = await repo.create_observation_point_type(obs_point)
        assert result.id == "os.linux.cpu.load"
        assert result.unit == "percent"

    @pytest.mark.asyncio
    async def test_list_observation_points_by_resource(self, repo, mock_db_pool):
        """Test listing observation points by resource ID"""
        from src.knowledge.db.repositories.taxonomy_repo import ObservationPointType

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                "id": "os.linux.cpu.load",
                "name": "CPU负载",
                "resource_type_id": "os.linux.cpu",
                "category": "load",
                "unit": "percent",
                "description": "CPU负载观察点",
                "metadata": None,
                "created_at": None,
                "updated_at": None,
            },
            {
                "id": "os.linux.cpu.perf",
                "name": "CPU性能",
                "resource_type_id": "os.linux.cpu",
                "category": "performance",
                "unit": "score",
                "description": "CPU性能指标",
                "metadata": None,
                "created_at": None,
                "updated_at": None,
            },
        ])
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        results = await repo.list_observation_points_by_resource("os.linux.cpu")
        assert len(results) == 2
        assert results[0].category == "load"

    @pytest.mark.asyncio
    async def test_delete_observation_point_type(self, repo, mock_db_pool):
        """Test deleting an observation point type"""
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")
        mock_conn.commit = AsyncMock()
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        result = await repo.delete_observation_point_type("os.linux.cpu.load")
        assert result is True
        mock_conn.execute.assert_called_once()

    # ===== Bulk Operations =====

    @pytest.mark.asyncio
    async def test_bulk_create_entity_types(self, repo, mock_db_pool):
        """Test bulk creating entity types"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.commit = AsyncMock()
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        entities = [
            EntityType(id="os.linux", name="Linux", category="os", description=None),
            EntityType(id="os.windows", name="Windows", category="os", description=None),
        ]

        await repo.bulk_create_entity_types(entities)
        assert mock_conn.execute.call_count == 2
        assert mock_conn.commit.call_count == 1

    # ===== Error Cases =====

    @pytest.mark.asyncio
    async def test_get_entity_type_not_found(self, repo, mock_db_pool):
        """Test getting non-existent entity type returns None"""
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_db_pool.acquire.return_value = self._make_ctx(mock_conn)

        result = await repo.get_entity_type_by_id("nonexistent")
        assert result is None
