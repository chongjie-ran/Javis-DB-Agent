"""Tests for Observation Point Metadata Service - Round 20"""
import pytest
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from src.knowledge.db.repositories.observation_point_repo import (
    ObservationPointRepository,
    ObservationPoint,
)


# ============================================================
# Tests for ObservationPointService
# ============================================================

class TestObservationPointService:
    """Tests for ObservationPointService - core business logic"""

    @pytest.fixture
    def mock_repo(self):
        """Create mock repository"""
        repo = MagicMock(spec=ObservationPointRepository)
        return repo

    @pytest.fixture
    def sample_op_dict(self):
        """Sample observation point as dict"""
        return {
            "id": "op-cpu-001",
            "resource_type": "OS.CPU",
            "metric_name": "usage_percent",
            "collection_method": "/proc/stat, psutil.cpu_percent()",
            "representation": "percentage (0-100%)",
            "anomaly_pattern": "持续>90%超过5分钟",
            "anomaly_condition": "avg(5m) > 90",
            "unit": "percent",
            "severity": "warning",
            "metadata": {"source": "benchmark"},
        }

    @pytest.fixture
    def sample_op(self, sample_op_dict):
        """Sample ObservationPoint"""
        return ObservationPoint(**sample_op_dict)

    @pytest.fixture
    def service(self, mock_repo):
        """Create service with mock repo"""
        from src.knowledge.services.observation_point_service import ObservationPointService
        svc = ObservationPointService(mock_repo)
        return svc

    def test_get_observation_point(self, service, mock_repo, sample_op):
        """Test getting observation point metadata"""
        mock_repo.get_observation_point_by_resource_metric = AsyncMock(return_value=sample_op)
        
        result = service.get_observation_point("OS.CPU", "usage_percent")
        
        assert result is not None
        assert result["resource_type"] == "OS.CPU"
        assert result["metric_name"] == "usage_percent"
        assert "collection_method" in result
        assert "representation" in result
        mock_repo.get_observation_point_by_resource_metric.assert_called_once_with("OS.CPU", "usage_percent")

    def test_list_observation_points(self, service, mock_repo, sample_op):
        """Test listing all observation points"""
        mock_repo.list_observation_points = AsyncMock(return_value=[sample_op])
        
        result = service.list_observation_points()
        
        assert len(result) == 1
        assert result[0]["resource_type"] == "OS.CPU"
        mock_repo.list_observation_points.assert_called_once()

    def test_list_observation_points_by_entity_type(self, service, mock_repo, sample_op):
        """Test listing observation points by entity type"""
        mock_repo.list_observation_points_by_resource_type = AsyncMock(return_value=[sample_op])
        
        result = service.list_observation_points(entity_type="OS.CPU")
        
        assert len(result) == 1
        mock_repo.list_observation_points_by_resource_type.assert_called_with("OS.CPU")

    def test_add_observation_point(self, service, mock_repo, sample_op_dict, sample_op):
        """Test adding a new observation point"""
        mock_repo.create_observation_point = AsyncMock(return_value=sample_op)
        
        result = service.add_observation_point(sample_op_dict)
        
        assert result.resource_type == "OS.CPU"
        mock_repo.create_observation_point.assert_called_once()

    def test_generate_alert_context(self, service, mock_repo, sample_op):
        """Test generating alert context with observation point metadata"""
        mock_repo.get_observation_point_by_resource_metric = AsyncMock(return_value=sample_op)
        
        # Mock alert
        alert = MagicMock()
        alert.alert_id = "ALT-001"
        alert.instance_id = "INS-001"
        alert.severity = "warning"
        alert.metric_value = 95.0
        alert.threshold = 90.0
        alert.message = "CPU使用率超过90%"
        alert.resource_type = "OS.CPU"
        alert.metric = "usage_percent"
        alert.to_dict = lambda: {
            "alert_id": "ALT-001",
            "severity": "warning",
            "metric_value": 95.0,
            "threshold": 90.0,
            "message": "CPU使用率超过90%",
        }
        
        result = service.generate_alert_context(alert)
        
        assert "alert" in result
        assert "observation_point" in result
        assert result["observation_point"]["resource_type"] == "OS.CPU"
        assert result["observation_point"]["collection_method"] == "/proc/stat, psutil.cpu_percent()"
        assert result["observation_point"]["anomaly_pattern"] == "持续>90%超过5分钟"
        assert result["observation_point"]["anomaly_condition"] == "avg(5m) > 90"
        assert result["collection_info"] == "/proc/stat, psutil.cpu_percent()"
        assert "持续>90%超过5分钟" in result["explanation"]

    def test_generate_alert_context_not_found(self, service, mock_repo):
        """Test generating alert context when observation point not found"""
        mock_repo.get_observation_point_by_resource_metric = AsyncMock(return_value=None)
        
        alert = MagicMock()
        alert.alert_id = "ALT-001"
        alert.instance_id = "INS-001"
        alert.severity = "warning"
        alert.metric_value = 95.0
        alert.threshold = 90.0
        alert.message = "CPU使用率超过90%"
        alert.resource_type = "OS.CPU"
        alert.metric = "usage_percent"
        alert.to_dict = lambda: {
            "alert_id": "ALT-001",
            "severity": "warning",
        }
        
        result = service.generate_alert_context(alert)
        
        assert "alert" in result
        assert "observation_point" in result
        assert result["observation_point"] is None
        assert "explanation" in result
        assert "未找到" in result["explanation"]

    def test_generate_alert_context_with_dict(self, service, mock_repo, sample_op):
        """Test generating alert context when alert is a dict"""
        mock_repo.get_observation_point_by_resource_metric = AsyncMock(return_value=sample_op)
        
        alert = {
            "alert_id": "ALT-001",
            "severity": "critical",
            "resource_type": "OS.CPU",
            "metric": "usage_percent",
            "metric_value": 98.0,
            "threshold": 90.0,
        }
        
        result = service.generate_alert_context(alert)
        
        assert result["observation_point"]["resource_type"] == "OS.CPU"


# ============================================================
# Tests for ObservationPoint Model
# ============================================================

class TestObservationPointModel:
    """Tests for ObservationPoint dataclass"""

    def test_observation_point_creation(self):
        """Test creating an ObservationPoint"""
        op = ObservationPoint(
            id="op-test-001",
            resource_type="OS.CPU",
            metric_name="usage_percent",
            collection_method="/proc/stat",
            representation="percentage",
            anomaly_pattern="持续>90%",
            anomaly_condition="avg(5m) > 90",
            unit="percent",
            severity="warning",
            metadata={"key": "value"},
        )
        
        assert op.id == "op-test-001"
        assert op.resource_type == "OS.CPU"
        assert op.metric_name == "usage_percent"
        assert op.metadata["key"] == "value"

    def test_observation_point_to_dict(self):
        """Test converting ObservationPoint to dict"""
        op = ObservationPoint(
            id="op-test-001",
            resource_type="OS.CPU",
            metric_name="usage_percent",
            collection_method="/proc/stat",
            representation="percentage",
            anomaly_pattern="持续>90%",
            anomaly_condition="avg(5m) > 90",
            unit="percent",
            severity="warning",
            metadata={},
        )
        
        d = op.to_dict()
        
        assert d["id"] == "op-test-001"
        assert d["resource_type"] == "OS.CPU"
        assert d["collection_method"] == "/proc/stat"
        assert d["anomaly_pattern"] == "持续>90%"

    def test_observation_point_metadata_default(self):
        """Test that metadata defaults to empty dict"""
        op = ObservationPoint(
            id="op-test-001",
            resource_type="OS.CPU",
            metric_name="usage_percent",
            collection_method="/proc/stat",
            representation="percentage",
        )
        
        assert op.metadata == {}


# ============================================================
# Tests for Alert Context Integration
# ============================================================

class TestAlertContextIntegration:
    """Tests for alert context generation with various alert types"""

    @pytest.fixture
    def service_with_repo(self):
        """Create service with real repo for integration tests"""
        from src.knowledge.db.repositories.observation_point_repo import ObservationPointRepository
        from src.knowledge.services.observation_point_service import ObservationPointService
        
        mock_conn = MagicMock()
        repo = ObservationPointRepository(mock_conn)
        return ObservationPointService(repo)

    def test_cpu_alert_context(self, service_with_repo):
        """Test CPU alert context generation"""
        cpu_op = ObservationPoint(
            id="op-cpu-001",
            resource_type="OS.CPU",
            metric_name="usage_percent",
            collection_method="/proc/stat, psutil.cpu_percent()",
            representation="percentage (0-100%)",
            anomaly_pattern="持续>90%超过5分钟",
            anomaly_condition="avg(5m) > 90",
            unit="percent",
            severity="warning",
            metadata={},
        )
        
        service_with_repo._repo.get_observation_point_by_resource_metric = AsyncMock(return_value=cpu_op)
        
        alert = MagicMock()
        alert.alert_id = "ALT-CPU-001"
        alert.instance_id = "INS-001"
        alert.severity = "critical"
        alert.metric_value = 95.5
        alert.threshold = 90.0
        alert.message = "CPU使用率持续超过90%"
        alert.resource_type = "OS.CPU"
        alert.metric = "usage_percent"
        alert.to_dict = lambda: {"alert_id": "ALT-CPU-001", "severity": "critical"}
        
        result = service_with_repo.generate_alert_context(alert)
        
        assert result["observation_point"]["anomaly_pattern"] == "持续>90%超过5分钟"
        assert "collection_method" in result["observation_point"]
        assert result["observation_point"]["collection_method"] == "/proc/stat, psutil.cpu_percent()"
        assert result["collection_info"] == "/proc/stat, psutil.cpu_percent()"
        assert "95.5" in result["anomaly_explanation"]
        assert "90.0" in result["anomaly_explanation"]

    def test_memory_alert_context(self, service_with_repo):
        """Test memory alert context generation"""
        mem_op = ObservationPoint(
            id="op-mem-001",
            resource_type="OS.Memory",
            metric_name="usage_percent",
            collection_method="/proc/meminfo, psutil.virtual_memory()",
            representation="percentage (0-100%)",
            anomaly_pattern="持续>85%超过10分钟",
            anomaly_condition="avg(10m) > 85",
            unit="percent",
            severity="warning",
            metadata={},
        )
        
        service_with_repo._repo.get_observation_point_by_resource_metric = AsyncMock(return_value=mem_op)
        
        alert = MagicMock()
        alert.alert_id = "ALT-MEM-001"
        alert.instance_id = "INS-001"
        alert.severity = "warning"
        alert.metric_value = 88.0
        alert.threshold = 85.0
        alert.message = "内存使用率超过85%"
        alert.resource_type = "OS.Memory"
        alert.metric = "usage_percent"
        alert.to_dict = lambda: {"alert_id": "ALT-MEM-001", "severity": "warning"}
        
        result = service_with_repo.generate_alert_context(alert)
        
        assert result["observation_point"]["anomaly_pattern"] == "持续>85%超过10分钟"
        assert result["observation_point"]["anomaly_condition"] == "avg(10m) > 85"

    def test_db_conn_alert_context(self, service_with_repo):
        """Test DB connection alert context generation"""
        db_op = ObservationPoint(
            id="op-db-conn-001",
            resource_type="DB.Connection",
            metric_name="active_count",
            collection_method="SHOW STATUS / pg_stat_activity",
            representation="count",
            anomaly_pattern="连接数>最大连接数80%",
            anomaly_condition="current > max_connections * 0.8",
            unit="count",
            severity="warning",
            metadata={},
        )
        
        service_with_repo._repo.get_observation_point_by_resource_metric = AsyncMock(return_value=db_op)
        
        alert = MagicMock()
        alert.alert_id = "ALT-DB-001"
        alert.instance_id = "INS-DB-001"
        alert.severity = "warning"
        alert.metric_value = 160.0
        alert.threshold = 150.0
        alert.message = "数据库连接数超过最大连接数80%"
        alert.resource_type = "DB.Connection"
        alert.metric = "active_count"
        alert.to_dict = lambda: {"alert_id": "ALT-DB-001", "severity": "warning"}
        
        result = service_with_repo.generate_alert_context(alert)
        
        assert result["observation_point"]["anomaly_pattern"] == "连接数>最大连接数80%"
        assert result["observation_point"]["collection_method"] == "SHOW STATUS / pg_stat_activity"

    def test_async_service_methods(self, service_with_repo):
        """Test async versions of service methods"""
        cpu_op = ObservationPoint(
            id="op-cpu-001",
            resource_type="OS.CPU",
            metric_name="usage_percent",
            collection_method="/proc/stat",
            representation="percentage",
            anomaly_pattern="持续>90%",
            anomaly_condition="avg(5m) > 90",
            unit="percent",
            severity="warning",
            metadata={},
        )
        
        service_with_repo._repo.get_observation_point_by_resource_metric = AsyncMock(return_value=cpu_op)
        service_with_repo._repo.list_observation_points = AsyncMock(return_value=[cpu_op])
        
        # Test async get
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            service_with_repo.get_observation_point_async("OS.CPU", "usage_percent")
        )
        assert result["resource_type"] == "OS.CPU"
        
        # Test async list
        result = asyncio.get_event_loop().run_until_complete(
            service_with_repo.list_observation_points_async()
        )
        assert len(result) == 1
