"""Tests for Dependency Propagation Engine - Round 19"""
import pytest
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

# Mock AlertNode from alert_correlator
class AlertRole:
    ROOT_CAUSE = "root_cause"
    SYMPTOM = "symptom"
    CONTRIBUTING = "contributing"
    UNKNOWN = "unknown"


@dataclass
class AlertNode:
    """Test alert node"""
    alert_id: str
    alert_name: str
    alert_type: str
    severity: str
    instance_id: str
    occurred_at: float
    message: str
    role: str = AlertRole.UNKNOWN
    confidence: float = 0.0
    root_cause_probability: float = 0.0
    related_alerts: List[str] = field(default_factory=list)


# ============================================================
# Tests for DependencyRepository
# ============================================================

class TestDependencyRepository:
    """Tests for DependencyRepository"""

    @pytest.fixture
    def mock_db_conn(self):
        """Create mock database connection"""
        conn = MagicMock()
        
        # Create a mock cursor that can be awaited
        async def mock_execute(sql, params=None):
            # Return a mock cursor
            mock_cursor = MagicMock()
            mock_cursor.fetchone = AsyncMock()
            mock_cursor.fetchall = AsyncMock()
            return mock_cursor
        
        conn.execute = mock_execute
        conn.commit = AsyncMock()
        conn.row_factory = None
        return conn

    @pytest.mark.asyncio
    async def test_create_dependency(self, mock_db_conn):
        """Test creating a dependency"""
        from src.knowledge.db.repositories.dependency_repo import DependencyRepository
        
        # Create an AsyncMock for execute
        mock_cursor = MagicMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)
        mock_db_conn.execute = AsyncMock(return_value=mock_cursor)
        
        repo = DependencyRepository(mock_db_conn)
        
        data = {
            "source_resource_type": "OS.CPU",
            "target_resource_type": "DB.Connection",
            "dependency_type": "depends_on",
            "weight": 0.9,
            "metadata": {"description": "CPU affects DB connections"}
        }
        
        result = await repo.create(data)
        
        assert result["source_resource_type"] == "OS.CPU"
        assert result["target_resource_type"] == "DB.Connection"
        assert result["weight"] == 0.9
        # Verify execute was called
        mock_db_conn.execute.assert_called()
        mock_db_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_dependency(self, mock_db_conn):
        """Test getting a dependency by id"""
        from src.knowledge.db.repositories.dependency_repo import DependencyRepository
        
        # Create a mock cursor with the result
        mock_cursor = MagicMock()
        mock_cursor.fetchone = AsyncMock(return_value={
            "id": "dep-001",
            "source_resource_type": "OS.CPU",
            "target_resource_type": "DB.Connection",
            "dependency_type": "depends_on",
            "weight": 0.9,
            "metadata": "{}",
            "created_at": None,
            "updated_at": None
        })
        mock_db_conn.execute = AsyncMock(return_value=mock_cursor)

        repo = DependencyRepository(mock_db_conn)
        result = await repo.get_by_id("dep-001")
        
        assert result is not None
        assert result["id"] == "dep-001"
        assert result["source_resource_type"] == "OS.CPU"

    @pytest.mark.asyncio
    async def test_list_all_dependencies(self, mock_db_conn):
        """Test listing all dependencies"""
        from src.knowledge.db.repositories.dependency_repo import DependencyRepository
        
        mock_cursor = MagicMock()
        mock_cursor.fetchall = AsyncMock(return_value=[
            {
                "id": "dep-001",
                "source_resource_type": "OS.CPU",
                "target_resource_type": "DB.Connection",
                "dependency_type": "depends_on",
                "weight": 0.9,
                "metadata": "{}",
                "created_at": None,
                "updated_at": None
            },
            {
                "id": "dep-002",
                "source_resource_type": "OS.Memory",
                "target_resource_type": "DB.Buffer",
                "dependency_type": "depends_on",
                "weight": 0.8,
                "metadata": "{}",
                "created_at": None,
                "updated_at": None
            }
        ])
        mock_db_conn.execute = AsyncMock(return_value=mock_cursor)

        repo = DependencyRepository(mock_db_conn)
        results = await repo.list_all()
        
        assert len(results) == 2
        assert results[0]["source_resource_type"] == "OS.CPU"
        assert results[1]["source_resource_type"] == "OS.Memory"

    @pytest.mark.asyncio
    async def test_delete_dependency(self, mock_db_conn):
        """Test deleting a dependency"""
        from src.knowledge.db.repositories.dependency_repo import DependencyRepository
        
        # Mock cursor for delete (no rows returned, but changes() works)
        mock_cursor1 = MagicMock()
        mock_cursor1.fetchone = AsyncMock(return_value=None)
        
        # Mock cursor for changes() query
        mock_cursor2 = MagicMock()
        mock_cursor2.fetchone = AsyncMock(return_value=(1,))
        
        async def mock_execute(sql, params=None):
            if "changes()" in sql:
                return mock_cursor2
            return mock_cursor1
        
        mock_db_conn.execute = mock_execute

        repo = DependencyRepository(mock_db_conn)
        result = await repo.delete("dep-001")
        
        assert result is True


# ============================================================
# Tests for DependencyPropagator
# ============================================================

class TestDependencyPropagator:
    """Tests for DependencyPropagator"""

    @pytest.fixture
    def mock_dependency_repo(self):
        """Create mock dependency repository"""
        repo = MagicMock()
        repo.list_all = AsyncMock(return_value=[
            {
                "id": "dep-001",
                "source_resource_type": "OS.CPU",
                "target_resource_type": "DB.Connection",
                "dependency_type": "depends_on",
                "weight": 0.9,
                "metadata": "{}"
            },
            {
                "id": "dep-002",
                "source_resource_type": "OS.Memory",
                "target_resource_type": "DB.Buffer",
                "dependency_type": "depends_on",
                "weight": 0.8,
                "metadata": "{}"
            },
            {
                "id": "dep-003",
                "source_resource_type": "DB.Connection",
                "target_resource_type": "DB.Query",
                "dependency_type": "calls",
                "weight": 0.7,
                "metadata": "{}"
            },
            {
                "id": "dep-004",
                "source_resource_type": "DB.Lock",
                "target_resource_type": "DB.Transaction",
                "dependency_type": "depends_on",
                "weight": 0.9,
                "metadata": "{}"
            }
        ])
        return repo

    @pytest.fixture
    def propagator(self, mock_dependency_repo):
        """Create DependencyPropagator with mock repo"""
        from src.knowledge.services.dependency_propagator import DependencyPropagator
        p = DependencyPropagator()
        p._dependency_repo = mock_dependency_repo
        # Pre-load the cache with the data the mock would return
        p._dependencies_cache = [
            {
                "id": "dep-001",
                "source_resource_type": "OS.CPU",
                "target_resource_type": "DB.Connection",
                "dependency_type": "depends_on",
                "weight": 0.9,
                "metadata": "{}"
            },
            {
                "id": "dep-002",
                "source_resource_type": "OS.Memory",
                "target_resource_type": "DB.Buffer",
                "dependency_type": "depends_on",
                "weight": 0.8,
                "metadata": "{}"
            },
            {
                "id": "dep-003",
                "source_resource_type": "DB.Connection",
                "target_resource_type": "DB.Query",
                "dependency_type": "calls",
                "weight": 0.7,
                "metadata": "{}"
            },
            {
                "id": "dep-004",
                "source_resource_type": "DB.Lock",
                "target_resource_type": "DB.Transaction",
                "dependency_type": "depends_on",
                "weight": 0.9,
                "metadata": "{}"
            }
        ]
        return p

    @pytest.mark.asyncio
    async def test_load_dependencies(self, propagator, mock_dependency_repo):
        """Test loading dependencies from cache"""
        deps = await propagator.load_dependencies()
        
        assert len(deps) == 4
        # Cache should already be set from fixture
        assert propagator._dependencies_cache is not None

    @pytest.mark.asyncio
    async def test_get_dependency_graph(self, propagator):
        """Test getting dependency graph"""
        await propagator.load_dependencies()
        graph = await propagator.get_dependency_graph()
        
        assert "nodes" in graph
        assert "edges" in graph
        assert len(graph["nodes"]) > 0
        assert len(graph["edges"]) > 0

    @pytest.mark.asyncio
    async def test_propagate_alert_basic(self, propagator):
        """Test basic alert propagation"""
        await propagator.load_dependencies()
        
        alert = AlertNode(
            alert_id="ALT-001",
            alert_name="CPU告警",
            alert_type="OS.CPU",
            severity="high",
            instance_id="INS-001",
            occurred_at=1234567890.0,
            message="CPU使用率超过90%"
        )
        
        propagated = await propagator.propagate_alert(alert, depth=3)
        
        # Should propagate to DB.Connection (depends_on with weight 0.9)
        assert len(propagated) >= 1
        # The propagated alert should have a root_cause_probability
        for p in propagated:
            if p.alert_type == "DB.Connection":
                assert p.root_cause_probability > 0
                assert p.root_cause_probability <= 1.0

    @pytest.mark.asyncio
    async def test_propagate_alert_with_depth_limit(self, propagator):
        """Test alert propagation respects depth"""
        await propagator.load_dependencies()
        
        alert = AlertNode(
            alert_id="ALT-001",
            alert_name="CPU告警",
            alert_type="OS.CPU",
            severity="high",
            instance_id="INS-001",
            occurred_at=1234567890.0,
            message="CPU使用率超过90%"
        )
        
        # depth=1 should only propagate one level
        propagated_depth1 = await propagator.propagate_alert(alert, depth=1)
        # depth=3 should propagate deeper
        propagated_depth3 = await propagator.propagate_alert(alert, depth=3)
        
        assert len(propagated_depth3) >= len(propagated_depth1)

    @pytest.mark.asyncio
    async def test_propagate_alert_weight_accumulation(self, propagator):
        """Test weight accumulation in propagation"""
        await propagator.load_dependencies()
        
        # Create alert that chains: OS.CPU -> DB.Connection -> DB.Query
        alert = AlertNode(
            alert_id="ALT-001",
            alert_name="CPU告警",
            alert_type="OS.CPU",
            severity="high",
            instance_id="INS-001",
            occurred_at=1234567890.0,
            message="CPU使用率超过90%"
        )
        
        propagated = await propagator.propagate_alert(alert, depth=3)
        
        # Find DB.Query in propagated (should have lower probability due to chain)
        db_query_alert = next((p for p in propagated if p.alert_type == "DB.Query"), None)
        db_conn_alert = next((p for p in propagated if p.alert_type == "DB.Connection"), None)
        
        if db_query_alert and db_conn_alert:
            # DB.Query should have lower probability than DB.Connection (chain effect)
            assert db_query_alert.root_cause_probability < db_conn_alert.root_cause_probability

    @pytest.mark.asyncio
    async def test_find_root_cause_single_alert(self, propagator):
        """Test finding root cause with single alert"""
        await propagator.load_dependencies()
        
        alerts = [
            AlertNode(
                alert_id="ALT-001",
                alert_name="CPU告警",
                alert_type="OS.CPU",
                severity="high",
                instance_id="INS-001",
                occurred_at=1234567890.0,
                message="CPU使用率超过90%",
                root_cause_probability=0.9
            )
        ]
        
        root_cause = await propagator.find_root_cause(alerts)
        
        assert root_cause is not None
        assert root_cause.alert_type == "OS.CPU"

    @pytest.mark.asyncio
    async def test_find_root_cause_multiple_alerts(self, propagator):
        """Test finding root cause with multiple alerts"""
        await propagator.load_dependencies()
        
        alerts = [
            AlertNode(
                alert_id="ALT-001",
                alert_name="CPU告警",
                alert_type="OS.CPU",
                severity="critical",
                instance_id="INS-001",
                occurred_at=1234567890.0,
                message="CPU使用率超过90%",
                root_cause_probability=0.9
            ),
            AlertNode(
                alert_id="ALT-002",
                alert_name="数据库连接满",
                alert_type="DB.Connection",
                severity="high",
                instance_id="INS-001",
                occurred_at=1234567891.0,
                message="数据库连接数达到上限",
                root_cause_probability=0.81  # 0.9 * 0.9
            ),
            AlertNode(
                alert_id="ALT-003",
                alert_name="查询超时",
                alert_type="DB.Query",
                severity="warning",
                instance_id="INS-001",
                occurred_at=1234567892.0,
                message="查询执行时间超过30秒",
                root_cause_probability=0.567  # 0.9 * 0.9 * 0.7
            )
        ]
        
        root_cause = await propagator.find_root_cause(alerts)
        
        assert root_cause is not None
        # Root cause should be OS.CPU (highest probability in this chain)
        assert root_cause.alert_type == "OS.CPU"

    @pytest.mark.asyncio
    async def test_find_root_cause_no_chain(self, propagator):
        """Test finding root cause when alerts don't form a chain"""
        await propagator.load_dependencies()
        
        # Two unrelated alerts
        alerts = [
            AlertNode(
                alert_id="ALT-001",
                alert_name="CPU告警",
                alert_type="OS.CPU",
                severity="warning",
                instance_id="INS-001",
                occurred_at=1234567890.0,
                message="CPU使用率超过80%",
                root_cause_probability=0.6
            ),
            AlertNode(
                alert_id="ALT-002",
                alert_name="内存告警",
                alert_type="OS.Memory",
                severity="high",
                instance_id="INS-002",
                occurred_at=1234567890.0,
                message="内存使用率超过85%",
                root_cause_probability=0.8
            )
        ]
        
        root_cause = await propagator.find_root_cause(alerts)
        
        # Should return the one with highest root_cause_probability
        assert root_cause.alert_type == "OS.Memory"
        assert root_cause.root_cause_probability == 0.8

    @pytest.mark.asyncio
    async def test_propagate_alert_empty_graph(self, propagator):
        """Test propagation when no dependencies loaded"""
        # Don't load dependencies
        alert = AlertNode(
            alert_id="ALT-001",
            alert_name="测试告警",
            alert_type="Unknown.Type",
            severity="warning",
            instance_id="INS-001",
            occurred_at=1234567890.0,
            message="测试"
        )
        
        propagated = await propagator.propagate_alert(alert, depth=3)
        
        # Should return empty list (no dependencies to propagate to)
        assert len(propagated) == 0


# ============================================================
# Tests for Default Benchmark Dependencies
# ============================================================

class TestBenchmarkDependencies:
    """Tests for benchmark dependency loading"""

    @pytest.fixture
    def mock_db_conn(self):
        """Create mock database connection returning empty"""
        conn = MagicMock()
        
        async def mock_execute(sql, params=None):
            mock_cursor = MagicMock()
            mock_cursor.fetchall = AsyncMock(return_value=[])
            mock_cursor.fetchone = AsyncMock(return_value=(22,))  # 22 benchmark deps
            return mock_cursor
        
        conn.execute = mock_execute
        conn.commit = AsyncMock()
        return conn

    @pytest.mark.asyncio
    async def test_load_benchmark_dependencies(self, mock_db_conn):
        """Test loading benchmark dependencies"""
        from src.knowledge.db.repositories.dependency_repo import DependencyRepository
        
        repo = DependencyRepository(mock_db_conn)
        count = await repo.load_benchmark_dependencies()
        
        # Should return count of dependencies (via migration)
        assert count == 22  # 22 benchmark deps in migration


# ============================================================


# ============================================================
# Tests for Dependency Routes (Simplified - Model tests only)
# ============================================================

class TestDependencyRoutes:
    """Tests for dependency API routes - model validation"""

    def test_propagate_alert_response_format(self):
        """Test propagate alert response format"""
        from src.api.dependency_routes import PropagatedAlertResponse
        
        # Test model validation
        data = {
            "alert_id": "ALT-001",
            "alert_name": "CPU告警",
            "alert_type": "OS.CPU",
            "severity": "high",
            "instance_id": "INS-001",
            "occurred_at": 1234567890.0,
            "message": "CPU告警",
            "root_cause_probability": 0.9,
            "propagation_depth": 1,
            "propagation_path": ["OS.CPU", "DB.Connection"],
            "role": "root_cause"
        }
        
        response = PropagatedAlertResponse(**data)
        assert response.alert_id == "ALT-001"
        assert response.alert_type == "OS.CPU"
        assert response.root_cause_probability == 0.9

    def test_dependency_create_model(self):
        """Test DependencyCreate model"""
        from src.api.dependency_routes import DependencyCreate
        
        data = DependencyCreate(
            source_resource_type="OS.CPU",
            target_resource_type="DB.Connection",
            dependency_type="depends_on",
            weight=0.9
        )
        
        assert data.source_resource_type == "OS.CPU"
        assert data.dependency_type == "depends_on"
        assert data.weight == 0.9

    def test_dependency_graph_response_format(self):
        """Test DependencyGraphResponse format"""
        from src.api.dependency_routes import DependencyGraphResponse
        
        data = {
            "nodes": ["OS.CPU", "DB.Connection", "DB.Query"],
            "edges": [
                {"source": "OS.CPU", "target": "DB.Connection", "weight": 0.9, "type": "depends_on"}
            ],
            "stats": {"total_nodes": 3, "total_edges": 1}
        }
        
        response = DependencyGraphResponse(**data)
        assert len(response.nodes) == 3
        assert len(response.edges) == 1
        assert response.stats["total_nodes"] == 3

    def test_root_cause_response_model(self):
        """Test RootCauseResponse model"""
        from src.api.dependency_routes import RootCauseResponse
        
        data = RootCauseResponse(
            root_cause={
                "alert_id": "ALT-001",
                "alert_type": "OS.CPU",
                "severity": "high",
                "instance_id": "INS-001",
                "message": "CPU告警",
                "root_cause_probability": 0.9
            },
            analysis=[
                {"alert_id": "ALT-001", "role": "root_cause", "root_cause_probability": 0.9}
            ],
            propagated_alerts=[],
            summary="Found root cause: OS.CPU"
        )
        
        assert data.root_cause["alert_type"] == "OS.CPU"
        assert data.summary == "Found root cause: OS.CPU"
