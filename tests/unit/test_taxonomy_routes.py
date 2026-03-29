"""Tests for taxonomy API routes"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI


class TestTaxonomyRoutes:
    """Test taxonomy API endpoints"""

    @pytest.fixture
    def mock_service(self):
        """Create mock taxonomy service"""
        service = MagicMock()
        return service

    @pytest.fixture
    def client(self, mock_service):
        """Create test client with mocked taxonomy service"""
        import sys
        import os
        import importlib.util

        # Load the taxonomy_routes module directly from file
        routes_dir = os.path.join(os.path.dirname(__file__), '../..', 'src', 'api', 'knowledge_routes')
        spec = importlib.util.spec_from_file_location(
            "taxonomy_routes_test",
            os.path.join(routes_dir, "taxonomy_routes.py")
        )
        taxonomy_routes = importlib.util.module_from_spec(spec)
        sys.modules['taxonomy_routes_test'] = taxonomy_routes
        spec.loader.exec_module(taxonomy_routes)

        # Set the global service to our mock
        taxonomy_routes._taxonomy_service = mock_service

        app = FastAPI()
        app.include_router(taxonomy_routes.router)
        return TestClient(app)

    # ===== GET /api/v1/taxonomy/entities =====

    def test_list_entities(self, client, mock_service):
        """Test listing all entities"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType

        mock_service.list_entities = AsyncMock(return_value=[
            EntityType(id="os.linux", name="Linux", category="os", description="Linux OS"),
            EntityType(id="db.postgresql", name="PostgreSQL", category="database", description="PostgreSQL DB"),
        ])

        response = client.get("/api/v1/taxonomy/entities")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 2
        assert data["items"][0]["id"] == "os.linux"
        assert data["total"] == 2

    def test_list_entities_empty(self, client, mock_service):
        """Test listing entities when none exist"""
        mock_service.list_entities = AsyncMock(return_value=[])

        response = client.get("/api/v1/taxonomy/entities")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_entities_with_filter(self, client, mock_service):
        """Test listing entities with category filter"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType

        mock_service.list_entities = AsyncMock(return_value=[
            EntityType(id="os.linux", name="Linux", category="os", description="Linux OS"),
        ])

        response = client.get("/api/v1/taxonomy/entities?category=os")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["category"] == "os"

    # ===== GET /api/v1/taxonomy/resources/{entity_id} =====

    def test_list_resources_by_entity(self, client, mock_service):
        """Test listing resources for an entity"""
        from src.knowledge.db.repositories.taxonomy_repo import ResourceType, EntityType

        mock_service.get_entity_with_resources = AsyncMock(return_value={
            "entity": EntityType(id="os.linux", name="Linux", category="os"),
            "resources": [
                {"resource": ResourceType(id="os.linux.cpu", name="CPU", entity_type_id="os.linux", category="hardware"), "observation_points": []},
                {"resource": ResourceType(id="os.linux.memory", name="Memory", entity_type_id="os.linux", category="hardware"), "observation_points": []},
            ],
        })

        response = client.get("/api/v1/taxonomy/resources/os.linux")

        assert response.status_code == 200
        data = response.json()
        assert data["entity"]["id"] == "os.linux"
        assert len(data["resources"]) == 2

    def test_list_resources_entity_not_found(self, client, mock_service):
        """Test listing resources for non-existent entity"""
        mock_service.get_entity_with_resources = AsyncMock(return_value=None)

        response = client.get("/api/v1/taxonomy/resources/nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    # ===== GET /api/v1/taxonomy/observation-points/{resource_id} =====

    def test_list_observation_points_by_resource(self, client, mock_service):
        """Test listing observation points for a resource"""
        from src.knowledge.db.repositories.taxonomy_repo import ResourceType, ObservationPointType

        mock_service.get_resource_with_observation_points = AsyncMock(return_value={
            "resource": ResourceType(id="os.linux.cpu", name="CPU", entity_type_id="os.linux", category="hardware"),
            "observation_points": [
                ObservationPointType(id="os.linux.cpu.load", name="Load", resource_type_id="os.linux.cpu", category="load", unit="percent"),
                ObservationPointType(id="os.linux.cpu.temp", name="Temp", resource_type_id="os.linux.cpu", category="performance", unit="celsius"),
            ],
        })

        response = client.get("/api/v1/taxonomy/observation-points/os.linux.cpu")

        assert response.status_code == 200
        data = response.json()
        assert data["resource"]["id"] == "os.linux.cpu"
        assert len(data["observation_points"]) == 2

    def test_list_observation_points_resource_not_found(self, client, mock_service):
        """Test listing observation points for non-existent resource"""
        mock_service.get_resource_with_observation_points = AsyncMock(return_value=None)

        response = client.get("/api/v1/taxonomy/observation-points/nonexistent")

        assert response.status_code == 404

    # ===== GET /api/v1/taxonomy/tree =====

    def test_get_entity_tree(self, client, mock_service):
        """Test getting full entity tree"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType
        from src.knowledge.services.taxonomy_service import EntityTreeNode

        tree_node = EntityTreeNode(
            entity=EntityType(id="os", name="OS", category="os"),
            resources=[],
            children=[
                EntityTreeNode(
                    entity=EntityType(id="os.linux", name="Linux", category="os", parent_id="os"),
                    resources=[],
                ),
            ],
        )
        mock_service.build_entity_tree = AsyncMock(return_value=[tree_node])
        mock_service.tree_to_dict = MagicMock(return_value=[{
            "entity": {"id": "os", "name": "OS", "category": "os"},
            "resources": [],
            "children": [{
                "entity": {"id": "os.linux", "name": "Linux", "category": "os"},
                "resources": [],
                "children": [],
            }],
        }])

        response = client.get("/api/v1/taxonomy/tree")

        assert response.status_code == 200
        data = response.json()
        assert "tree" in data
        assert len(data["tree"]) == 1
        assert data["tree"][0]["entity"]["id"] == "os"

    def test_get_entity_tree_empty(self, client, mock_service):
        """Test getting empty entity tree"""
        mock_service.build_entity_tree = AsyncMock(return_value=[])
        mock_service.tree_to_dict = MagicMock(return_value=[])

        response = client.get("/api/v1/taxonomy/tree")

        assert response.status_code == 200
        data = response.json()
        assert data["tree"] == []

    # ===== POST /api/v1/taxonomy/entities =====

    def test_create_entity(self, client, mock_service):
        """Test creating an entity"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType

        mock_service.create_entity = AsyncMock(return_value=EntityType(
            id="os.windows",
            name="Windows",
            category="os",
            description="Windows OS",
        ))

        response = client.post(
            "/api/v1/taxonomy/entities",
            json={
                "id": "os.windows",
                "name": "Windows",
                "category": "os",
                "description": "Windows OS",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "os.windows"
        assert data["name"] == "Windows"

    def test_create_entity_duplicate(self, client, mock_service):
        """Test creating duplicate entity returns 409"""
        mock_service.create_entity = AsyncMock(side_effect=ValueError("Entity already exists"))

        response = client.post(
            "/api/v1/taxonomy/entities",
            json={
                "id": "os.linux",
                "name": "Linux",
                "category": "os",
            },
        )

        assert response.status_code == 409

    # ===== POST /api/v1/taxonomy/resources =====

    def test_create_resource(self, client, mock_service):
        """Test creating a resource type"""
        from src.knowledge.db.repositories.taxonomy_repo import ResourceType

        mock_service.create_resource = AsyncMock(return_value=ResourceType(
            id="os.linux.disk",
            name="Disk",
            entity_type_id="os.linux",
            category="hardware",
        ))

        response = client.post(
            "/api/v1/taxonomy/resources",
            json={
                "id": "os.linux.disk",
                "name": "Disk",
                "entity_type_id": "os.linux",
                "category": "hardware",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "os.linux.disk"

    # ===== POST /api/v1/taxonomy/observation-points =====

    def test_create_observation_point(self, client, mock_service):
        """Test creating an observation point"""
        from src.knowledge.db.repositories.taxonomy_repo import ObservationPointType

        mock_service.create_observation_point = AsyncMock(return_value=ObservationPointType(
            id="os.linux.cpu.load",
            name="CPU Load",
            resource_type_id="os.linux.cpu",
            category="load",
            unit="percent",
        ))

        response = client.post(
            "/api/v1/taxonomy/observation-points",
            json={
                "id": "os.linux.cpu.load",
                "name": "CPU Load",
                "resource_type_id": "os.linux.cpu",
                "category": "load",
                "unit": "percent",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "os.linux.cpu.load"
        assert data["unit"] == "percent"

    # ===== DELETE endpoints =====

    def test_delete_entity(self, client, mock_service):
        """Test deleting an entity"""
        mock_service.delete_entity = AsyncMock(return_value=True)

        response = client.delete("/api/v1/taxonomy/entities/os.linux")

        assert response.status_code == 204

    def test_delete_resource(self, client, mock_service):
        """Test deleting a resource type"""
        mock_service.delete_resource = AsyncMock(return_value=True)

        response = client.delete("/api/v1/taxonomy/resources/os.linux.cpu")

        assert response.status_code == 204

    def test_delete_observation_point(self, client, mock_service):
        """Test deleting an observation point"""
        mock_service.delete_observation_point = AsyncMock(return_value=True)

        response = client.delete("/api/v1/taxonomy/observation-points/os.linux.cpu.load")

        assert response.status_code == 204

    # ===== Error Handling =====

    def test_internal_server_error(self, client, mock_service):
        """Test handling internal server errors"""
        mock_service.list_entities = AsyncMock(side_effect=Exception("Database error"))

        response = client.get("/api/v1/taxonomy/entities")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
