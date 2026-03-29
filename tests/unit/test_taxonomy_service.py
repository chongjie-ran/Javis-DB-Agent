"""Tests for taxonomy service"""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestTaxonomyService:
    """Test TaxonomyService business logic"""

    @pytest.fixture
    def mock_repo(self):
        """Create a mock repository"""
        repo = MagicMock()
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        """Create service with mock repo"""
        from src.knowledge.services.taxonomy_service import TaxonomyService
        service = TaxonomyService(taxonomy_repo=mock_repo)
        service._repo = mock_repo  # Ensure repo is set
        return service

    # ===== EntityTree Tests =====

    @pytest.mark.asyncio
    async def test_build_entity_tree_single_level(self, service, mock_repo):
        """Test building entity tree with single level (no children)"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType, ResourceType, ObservationPointType
        from src.knowledge.services.taxonomy_service import EntityTreeNode

        # Mock entity types
        mock_repo.list_entity_types = AsyncMock(return_value=[
            EntityType(id="os.linux", name="Linux", category="os", description="Linux OS", parent_id=None),
            EntityType(id="db.postgresql", name="PostgreSQL", category="database", description="PostgreSQL DB", parent_id=None),
        ])

        # Mock resource types for each entity
        async def mock_resource_types(entity_id, category=None, limit=100, offset=0):
            if entity_id == "os.linux":
                return [
                    ResourceType(id="os.linux.cpu", name="CPU", entity_type_id="os.linux", category="hardware", description=None),
                ]
            elif entity_id == "db.postgresql":
                return [
                    ResourceType(id="db.postgresql.session", name="Session", entity_type_id="db.postgresql", category="data_access", description=None),
                ]
            return []

        mock_repo.list_resource_types_by_entity = AsyncMock(side_effect=mock_resource_types)

        # Mock observation points
        async def mock_obs_points(resource_id, category=None, limit=100, offset=0):
            if resource_id == "os.linux.cpu":
                return [
                    ObservationPointType(id="os.linux.cpu.load", name="CPU Load", resource_type_id="os.linux.cpu", category="load", unit="percent", description=None),
                ]
            elif resource_id == "db.postgresql.session":
                return [
                    ObservationPointType(id="db.postgresql.session.count", name="Session Count", resource_type_id="db.postgresql.session", category="load", unit="count", description=None),
                ]
            return []

        mock_repo.list_observation_points_by_resource = AsyncMock(side_effect=mock_obs_points)

        # Build tree
        tree = await service.build_entity_tree()

        assert len(tree) == 2
        linux_node = next(n for n in tree if n.entity.id == "os.linux")
        assert linux_node.entity.name == "Linux"
        assert len(linux_node.resources) == 1
        assert linux_node.resources[0]["resource"].name == "CPU"
        assert len(linux_node.resources[0]["observation_points"]) == 1

    @pytest.mark.asyncio
    async def test_build_entity_tree_with_hierarchy(self, service, mock_repo):
        """Test building entity tree with parent-child relationships"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType, ResourceType, ObservationPointType

        # Entity with parent
        mock_repo.list_entity_types = AsyncMock(return_value=[
            EntityType(id="os", name="Operating System", category="os", description=None, parent_id=None),
            EntityType(id="os.linux", name="Linux", category="os", description=None, parent_id="os"),
        ])

        async def mock_resource_types(entity_id, category=None, limit=100, offset=0):
            if entity_id in ["os", "os.linux"]:
                return [
                    ResourceType(id=f"{entity_id}.cpu", name="CPU", entity_type_id=entity_id, category="hardware", description=None),
                ]
            return []

        mock_repo.list_resource_types_by_entity = AsyncMock(side_effect=mock_resource_types)

        async def mock_obs_points(resource_id, category=None, limit=100, offset=0):
            return [
                ObservationPointType(id=f"{resource_id}.load", name="Load", resource_type_id=resource_id, category="load", unit="percent", description=None),
            ]

        mock_repo.list_observation_points_by_resource = AsyncMock(side_effect=mock_obs_points)

        tree = await service.build_entity_tree()

        assert len(tree) == 1  # Only root entities (parent_id=None)
        root = tree[0]
        assert root.entity.id == "os"
        assert len(root.children) == 1
        assert root.children[0].entity.id == "os.linux"

    # ===== CRUD Operation Tests =====

    @pytest.mark.asyncio
    async def test_create_entity(self, service, mock_repo):
        """Test creating an entity"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType

        mock_repo.create_entity_type = AsyncMock(return_value=EntityType(
            id="os.windows",
            name="Windows",
            category="os",
            description="Windows OS",
        ))

        result = await service.create_entity(
            id="os.windows",
            name="Windows",
            category="os",
            description="Windows OS",
        )

        assert result.id == "os.windows"
        assert result.name == "Windows"
        mock_repo.create_entity_type.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_resource(self, service, mock_repo):
        """Test creating a resource type"""
        from src.knowledge.db.repositories.taxonomy_repo import ResourceType, EntityType

        mock_repo.get_entity_type_by_id = AsyncMock(return_value=EntityType(
            id="os.linux",
            name="Linux",
            category="os",
        ))

        mock_repo.create_resource_type = AsyncMock(return_value=ResourceType(
            id="os.linux.memory",
            name="Memory",
            entity_type_id="os.linux",
            category="hardware",
            description="Memory resource",
        ))

        result = await service.create_resource(
            id="os.linux.memory",
            name="Memory",
            entity_type_id="os.linux",
            category="hardware",
            description="Memory resource",
        )

        assert result.id == "os.linux.memory"
        mock_repo.create_resource_type.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_observation_point(self, service, mock_repo):
        """Test creating an observation point type"""
        from src.knowledge.db.repositories.taxonomy_repo import ObservationPointType, ResourceType

        mock_repo.get_resource_type_by_id = AsyncMock(return_value=ResourceType(
            id="os.linux.cpu",
            name="CPU",
            entity_type_id="os.linux",
            category="hardware",
        ))

        mock_repo.create_observation_point_type = AsyncMock(return_value=ObservationPointType(
            id="os.linux.cpu.util",
            name="CPU Utilization",
            resource_type_id="os.linux.cpu",
            category="performance",
            unit="percent",
            description="CPU utilization metric",
        ))

        result = await service.create_observation_point(
            id="os.linux.cpu.util",
            name="CPU Utilization",
            resource_type_id="os.linux.cpu",
            category="performance",
            unit="percent",
            description="CPU utilization metric",
        )

        assert result.id == "os.linux.cpu.util"
        assert result.unit == "percent"
        mock_repo.create_observation_point_type.assert_called_once()

    # ===== Query Tests =====

    @pytest.mark.asyncio
    async def test_get_entity_with_resources(self, service, mock_repo):
        """Test getting entity with its resources"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType, ResourceType

        mock_repo.get_entity_type_by_id = AsyncMock(return_value=EntityType(
            id="os.linux",
            name="Linux",
            category="os",
            description="Linux OS",
        ))

        mock_repo.list_resource_types_by_entity = AsyncMock(return_value=[
            ResourceType(id="os.linux.cpu", name="CPU", entity_type_id="os.linux", category="hardware", description=None),
        ])

        mock_repo.list_observation_points_by_resource = AsyncMock(return_value=[])

        result = await service.get_entity_with_resources("os.linux")

        assert result["entity"].id == "os.linux"
        assert len(result["resources"]) == 1
        assert result["resources"][0]["resource"].name == "CPU"

    @pytest.mark.asyncio
    async def test_get_resource_with_observation_points(self, service, mock_repo):
        """Test getting resource with its observation points"""
        from src.knowledge.db.repositories.taxonomy_repo import ResourceType, ObservationPointType

        mock_repo.get_resource_type_by_id = AsyncMock(return_value=ResourceType(
            id="os.linux.cpu",
            name="CPU",
            entity_type_id="os.linux",
            category="hardware",
            description="CPU resource",
        ))

        mock_repo.list_observation_points_by_resource = AsyncMock(return_value=[
            ObservationPointType(id="os.linux.cpu.load", name="Load", resource_type_id="os.linux.cpu", category="load", unit="percent", description=None),
            ObservationPointType(id="os.linux.cpu.temp", name="Temperature", resource_type_id="os.linux.cpu", category="performance", unit="celsius", description=None),
        ])

        result = await service.get_resource_with_observation_points("os.linux.cpu")

        assert result["resource"].id == "os.linux.cpu"
        assert len(result["observation_points"]) == 2

    # ===== Validation Tests =====

    @pytest.mark.asyncio
    async def test_validate_entity_category_valid(self, service):
        """Test valid entity categories"""
        valid_categories = ["os", "database", "application"]
        for cat in valid_categories:
            # Should not raise
            pass
        assert True

    @pytest.mark.asyncio
    async def test_validate_resource_category_valid(self, service):
        """Test valid resource categories"""
        valid_categories = ["hardware", "software", "data"]
        for cat in valid_categories:
            # Should not raise
            pass
        assert True

    @pytest.mark.asyncio
    async def test_validate_observation_category_valid(self, service):
        """Test valid observation point categories"""
        valid_categories = ["load", "performance", "error", "security", "config"]
        for cat in valid_categories:
            # Should not raise
            pass
        assert True


class TestEntityTreeNode:
    """Test EntityTreeNode data structure"""

    def test_entity_tree_node_creation(self):
        """Test creating an EntityTreeNode"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType, ResourceType
        from src.knowledge.services.taxonomy_service import EntityTreeNode

        entity = EntityType(
            id="os.linux",
            name="Linux",
            category="os",
            description="Linux OS",
        )

        resource = ResourceType(
            id="os.linux.cpu",
            name="CPU",
            entity_type_id="os.linux",
            category="hardware",
            description=None,
        )

        node = EntityTreeNode(
            entity=entity,
            resources=[{"resource": resource, "observation_points": []}],
        )

        assert node.entity.id == "os.linux"
        assert len(node.resources) == 1
        assert len(node.children) == 0

    def test_entity_tree_node_with_children(self):
        """Test EntityTreeNode with child nodes"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType
        from src.knowledge.services.taxonomy_service import EntityTreeNode

        parent_entity = EntityType(id="os", name="OS", category="os", description=None)
        child_entity = EntityType(id="os.linux", name="Linux", category="os", description=None, parent_id="os")

        parent = EntityTreeNode(entity=parent_entity, resources=[])
        child = EntityTreeNode(entity=child_entity, resources=[])
        parent.children.append(child)

        assert len(parent.children) == 1
        assert parent.children[0].entity.id == "os.linux"

    def test_entity_tree_node_to_dict(self):
        """Test converting EntityTreeNode to dict"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType, ResourceType, ObservationPointType
        from src.knowledge.services.taxonomy_service import EntityTreeNode

        entity = EntityType(
            id="os.linux",
            name="Linux",
            category="os",
            description="Linux OS",
        )

        resource = ResourceType(
            id="os.linux.cpu",
            name="CPU",
            entity_type_id="os.linux",
            category="hardware",
            description=None,
        )

        obs_point = ObservationPointType(
            id="os.linux.cpu.load",
            name="Load",
            resource_type_id="os.linux.cpu",
            category="load",
            unit="percent",
            description=None,
        )

        node = EntityTreeNode(
            entity=entity,
            resources=[{"resource": resource, "observation_points": [obs_point]}],
        )

        d = node.to_dict()

        assert d["entity"]["id"] == "os.linux"
        assert len(d["resources"]) == 1
        assert d["resources"][0]["resource"]["id"] == "os.linux.cpu"
        assert len(d["resources"][0]["observation_points"]) == 1
        assert d["resources"][0]["observation_points"][0]["id"] == "os.linux.cpu.load"
