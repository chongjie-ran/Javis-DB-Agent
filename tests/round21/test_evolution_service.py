"""Tests for knowledge base evolution service (Round 21)"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass


class TestCoverageAssessor:
    """Test CoverageAssessor - evaluates knowledge base coverage"""

    @pytest.fixture
    def mock_taxonomy_repo(self):
        """Mock taxonomy repository"""
        repo = MagicMock()
        return repo

    @pytest.fixture
    def mock_alert_rule_repo(self):
        """Mock alert rule repository"""
        repo = MagicMock()
        return repo

    @pytest.fixture
    def assessor(self, mock_taxonomy_repo, mock_alert_rule_repo):
        """Create CoverageAssessor with mock repos"""
        from src.knowledge.evolution.coverage_assessor import CoverageAssessor
        assessor = CoverageAssessor(
            taxonomy_repo=mock_taxonomy_repo,
            alert_rule_repo=mock_alert_rule_repo
        )
        return assessor

    @pytest.mark.asyncio
    async def test_assess_coverage_full(self, assessor, mock_taxonomy_repo, mock_alert_rule_repo):
        """Test full coverage assessment across all entity types"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType, ResourceType, ObservationPointType

        # Mock entity types
        mock_taxonomy_repo.list_entity_types = AsyncMock(return_value=[
            EntityType(id="os.linux", name="Linux", category="os", description="Linux OS", parent_id=None),
            EntityType(id="db.postgresql", name="PostgreSQL", category="database", description="PostgreSQL DB", parent_id=None),
        ])

        # Mock resource types per entity
        async def mock_resources(entity_type_id, category=None, limit=100, offset=0):
            if entity_type_id == "os.linux":
                return [
                    ResourceType(id="os.linux.cpu", name="CPU", entity_type_id="os.linux", category="compute", description=None),
                    ResourceType(id="os.linux.memory", name="Memory", entity_type_id="os.linux", category="memory", description=None),
                ]
            elif entity_type_id == "db.postgresql":
                return [
                    ResourceType(id="db.postgresql.session", name="Session", entity_type_id="db.postgresql", category="service", description=None),
                ]
            return []

        mock_taxonomy_repo.list_resource_types_by_entity = AsyncMock(side_effect=mock_resources)

        # Mock observation points per resource
        async def mock_obs_points(resource_type_id, category=None, limit=100, offset=0):
            if resource_type_id == "os.linux.cpu":
                return [
                    ObservationPointType(id="os.linux.cpu.utilization", name="CPU Util", resource_type_id="os.linux.cpu", category="performance", unit="percent", description=None),
                ]
            elif resource_type_id == "os.linux.memory":
                return [
                    ObservationPointType(id="os.linux.memory.used", name="Memory Used", resource_type_id="os.linux.memory", category="performance", unit="percent", description=None),
                ]
            elif resource_type_id == "db.postgresql.session":
                return []
            return []

        mock_taxonomy_repo.list_observation_points_by_resource = AsyncMock(side_effect=mock_obs_points)

        # Mock alert rules - covers only os.linux.cpu
        mock_alert_rule_repo.list_all = AsyncMock(return_value=[
            {"id": "alert-001", "entity_type": "os.linux", "resource_type": "os.linux.cpu", "observation_point": "os.linux.cpu.utilization", "severity": "warning"},
        ])

        # Run assessment
        report = await assessor.assess()

        assert report.total_entities == 2
        assert report.total_resources == 3
        # db.postgresql.session has 0 obs points in this test, so total = 2 (cpu.utilization + memory.used)
        assert report.total_observation_points == 2
        assert report.covered_entities == 1
        assert report.covered_resources == 1
        assert report.covered_observation_points == 1
        # Linux CPU covered, but not Linux Memory nor PostgreSQL Session
        assert len(report.gaps) > 0

    @pytest.mark.asyncio
    async def test_assess_coverage_by_entity_type(self, assessor, mock_taxonomy_repo, mock_alert_rule_repo):
        """Test coverage assessment filtered by entity type"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType, ResourceType, ObservationPointType

        mock_taxonomy_repo.list_entity_types = AsyncMock(return_value=[
            EntityType(id="os.linux", name="Linux", category="os", description="Linux OS", parent_id=None),
        ])
        mock_taxonomy_repo.list_resource_types_by_entity = AsyncMock(return_value=[
            ResourceType(id="os.linux.cpu", name="CPU", entity_type_id="os.linux", category="compute", description=None),
        ])
        mock_taxonomy_repo.list_observation_points_by_resource = AsyncMock(return_value=[
            ObservationPointType(id="os.linux.cpu.utilization", name="CPU Util", resource_type_id="os.linux.cpu", category="performance", unit="percent", description=None),
        ])
        mock_alert_rule_repo.list_all = AsyncMock(return_value=[])

        report = await assessor.assess(entity_type="os.linux")

        assert report.total_entities == 1
        assert report.entity_filter == "os.linux"

    @pytest.mark.asyncio
    async def test_assess_coverage_empty_knowledge_base(self, assessor, mock_taxonomy_repo, mock_alert_rule_repo):
        """Test assessment when knowledge base has no alert rules"""
        from src.knowledge.db.repositories.taxonomy_repo import EntityType, ResourceType, ObservationPointType

        mock_taxonomy_repo.list_entity_types = AsyncMock(return_value=[
            EntityType(id="os.linux", name="Linux", category="os", description="Linux OS", parent_id=None),
        ])
        mock_taxonomy_repo.list_resource_types_by_entity = AsyncMock(return_value=[
            ResourceType(id="os.linux.cpu", name="CPU", entity_type_id="os.linux", category="compute", description=None),
        ])
        mock_taxonomy_repo.list_observation_points_by_resource = AsyncMock(return_value=[
            ObservationPointType(id="os.linux.cpu.utilization", name="CPU Util", resource_type_id="os.linux.cpu", category="performance", unit="percent", description=None),
        ])
        mock_alert_rule_repo.list_all = AsyncMock(return_value=[])

        report = await assessor.assess()

        assert report.covered_entities == 0
        assert report.covered_resources == 0
        assert report.covered_observation_points == 0
        assert len(report.gaps) == 3  # entity, resource, obs_point


class TestKnowledgeGenerator:
    """Test KnowledgeGenerator - generates knowledge from coverage gaps"""

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client"""
        client = MagicMock()
        # Track call count to return appropriate responses
        call_count = {"count": 0}
        async def mock_complete(prompt, **kwargs):
            call_count["count"] += 1
            # Check more specific patterns first to avoid false matches
            # SOP prompt contains both "告警规则" AND "标准操作程序" - check SOP first
            if "标准操作" in prompt or ("SOP" in prompt and "steps" in prompt):
                return '{"title": "CPU高负载告警处理流程", "steps": [{"step": 1, "action": "查看CPU使用率"}]}'
            elif "案例" in prompt or ("case" in prompt.lower() and "symptoms" in prompt.lower()):
                return '{"title": "CPU高负载故障案例", "symptoms": {"cpu_utilization": 95}, "root_cause": "进程异常", "solution": "重启进程", "outcome": "恢复"}'
            elif "告警规则" in prompt or "alert_rule" in prompt.lower():
                return '{"name": "CPU高负载告警", "condition": "cpu_utilization > 80", "severity": "warning", "recommendation": "检查进程负载"}'
            return '{"name": "Generated", "condition": "metric > 0", "severity": "warning"}'
        client.complete = AsyncMock(side_effect=mock_complete)
        client.chat = AsyncMock(return_value={"message": {"content": '{"name": "Generated Alert"}'}})
        return client

    @pytest.fixture
    def generator(self, mock_llm_client):
        """Create KnowledgeGenerator with mock LLM"""
        from src.knowledge.evolution.knowledge_generator import KnowledgeGenerator
        return KnowledgeGenerator(llm_client=mock_llm_client)

    @pytest.mark.asyncio
    async def test_generate_alert_rule_from_gap(self, generator):
        """Test generating an alert rule from a coverage gap"""
        gap = {
            "gap_type": "observation_point",
            "entity_type": "os.linux",
            "resource_type": "os.linux.memory",
            "observation_point": "os.linux.memory.used",
            "description": "No alert rule for memory usage on Linux"
        }

        rule = await generator.generate_alert_rule(gap)

        assert rule is not None
        assert "name" in rule
        assert "condition" in rule
        assert "severity" in rule
        assert rule.get("entity_type") == "os.linux"
        assert rule.get("resource_type") == "os.linux.memory"
        assert rule.get("observation_point") == "os.linux.memory.used"

    @pytest.mark.asyncio
    async def test_generate_sop_for_alert_rule(self, generator):
        """Test generating SOP for an alert rule"""
        alert_rule = {
            "id": "alert-001",
            "name": "CPU高负载告警",
            "condition": "cpu_utilization > 80",
            "severity": "warning",
            "recommendation": "检查进程负载"
        }

        sop = await generator.generate_sop(alert_rule)

        assert sop is not None
        assert "id" in sop
        assert "title" in sop
        assert "steps" in sop
        assert sop["alert_rule_id"] == "alert-001"

    @pytest.mark.asyncio
    async def test_generate_case_from_scenario(self, generator):
        """Test generating a case from a scenario"""
        scenario = {
            "entity_type": "db.postgresql",
            "resource_type": "db.postgresql.lock",
            "symptoms": {"waiting_sessions": 10, "lock_wait_time_ms": 5000},
            "root_cause": "长事务持有锁",
            "solution": "Kill blocking session"
        }

        case = await generator.generate_case(scenario)

        assert case is not None
        assert "id" in case
        assert "title" in case
        assert "symptoms" in case

    @pytest.mark.asyncio
    async def test_generate_alert_rule_with_llm_failure(self, generator):
        """Test graceful handling when LLM fails"""
        generator._llm.complete = AsyncMock(side_effect=Exception("LLM unavailable"))

        gap = {
            "gap_type": "observation_point",
            "entity_type": "os.linux",
            "resource_type": "os.linux.cpu",
            "observation_point": "os.linux.cpu.iowait",
        }

        # Should return a fallback rule rather than raising
        rule = await generator.generate_alert_rule(gap)
        assert rule is not None
        assert "name" in rule  # fallback name


class TestEvolutionService:
    """Test EvolutionService - orchestrates the full evolution loop"""

    @pytest.fixture
    def mock_coverage_assessor(self):
        assessor = MagicMock()
        assessor.assess = AsyncMock()
        return assessor

    @pytest.fixture
    def mock_knowledge_generator(self):
        generator = MagicMock()
        generator.generate_alert_rule = AsyncMock()
        generator.generate_sop = AsyncMock()
        generator.generate_case = AsyncMock()
        return generator

    @pytest.fixture
    def mock_kb_service(self):
        kb = MagicMock()
        kb.create_alert_rule = AsyncMock(return_value={"id": "new-alert-001"})
        kb.create_sop = AsyncMock(return_value={"id": "new-sop-001"})
        kb.create_case = AsyncMock(return_value={"id": "new-case-001"})
        kb.list_alert_rules = AsyncMock(return_value=[])
        return kb

    @pytest.fixture
    def evolution_service(self, mock_coverage_assessor, mock_knowledge_generator, mock_kb_service):
        """Create EvolutionService with mock dependencies"""
        from src.knowledge.evolution.evolution_service import EvolutionService
        service = EvolutionService(
            coverage_assessor=mock_coverage_assessor,
            knowledge_generator=mock_knowledge_generator,
            kb_service=mock_kb_service
        )
        return service

    @pytest.mark.asyncio
    async def test_evolve_full_loop(self, evolution_service, mock_coverage_assessor, mock_knowledge_generator):
        """Test full evolution: assess → generate → validate → update"""
        from src.knowledge.evolution.coverage_assessor import CoverageReport
        from dataclasses import asdict

        # Mock coverage report with gaps
        mock_coverage_assessor.assess = AsyncMock(return_value=CoverageReport(
            total_entities=2,
            total_resources=3,
            total_observation_points=5,
            covered_entities=1,
            covered_resources=1,
            covered_observation_points=1,
            gaps=[
                {"gap_type": "observation_point", "entity_type": "os.linux", "resource_type": "os.linux.memory", "observation_point": "os.linux.memory.used"}
            ],
            entity_filter=None
        ))

        # Mock knowledge generator outputs
        mock_knowledge_generator.generate_alert_rule = AsyncMock(return_value={
            "id": "gen-alert-001",
            "name": "Memory高负载告警",
            "condition": "memory_used > 80",
            "severity": "warning",
            "entity_type": "os.linux",
            "resource_type": "os.linux.memory",
            "observation_point": "os.linux.memory.used"
        })
        mock_knowledge_generator.generate_sop = AsyncMock(return_value={
            "id": "gen-sop-001",
            "title": "Memory告警处理SOP",
            "alert_rule_id": "gen-alert-001",
            "steps": [{"step": 1, "action": "检查内存使用"}]
        })

        # Run evolution
        result = await evolution_service.evolve()

        assert result.total_gaps == 1
        # Each gap generates alert_rule + SOP = 2 candidates
        assert result.candidates_generated == 2
        assert result.validated_count >= 0
        assert result.success is True
        mock_coverage_assessor.assess.assert_called_once()

    @pytest.mark.asyncio
    async def test_evolve_no_gaps(self, evolution_service, mock_coverage_assessor):
        """Test evolution when there are no coverage gaps"""
        from src.knowledge.evolution.coverage_assessor import CoverageReport

        mock_coverage_assessor.assess = AsyncMock(return_value=CoverageReport(
            total_entities=2,
            total_resources=3,
            total_observation_points=5,
            covered_entities=2,
            covered_resources=3,
            covered_observation_points=5,
            gaps=[],
            entity_filter=None
        ))

        result = await evolution_service.evolve()

        assert result.total_gaps == 0
        assert result.candidates_generated == 0
        assert result.success is True

    @pytest.mark.asyncio
    async def test_validate_knowledge_valid(self, evolution_service):
        """Test validation of a valid candidate"""
        candidate = {
            "type": "alert_rule",
            "name": "CPU高负载告警",
            "condition": "cpu_utilization > 80",
            "severity": "warning",
            "entity_type": "os.linux",
            "resource_type": "os.linux.cpu"
        }

        result = await evolution_service.validate_knowledge(candidate)

        assert result["valid"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_validate_knowledge_invalid_missing_fields(self, evolution_service):
        """Test validation rejects candidate with missing required fields"""
        candidate = {
            "type": "alert_rule",
            "name": "CPU告警",
            # missing condition, severity
        }

        result = await evolution_service.validate_knowledge(candidate)

        assert result["valid"] is False
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_validate_knowledge_conflict(self, evolution_service, mock_kb_service):
        """Test validation detects conflict with existing knowledge"""
        # Existing rule
        mock_kb_service.list_alert_rules = AsyncMock(return_value=[
            {"id": "existing-001", "name": "CPU高负载告警", "entity_type": "os.linux", "resource_type": "os.linux.cpu", "severity": "warning"}
        ])

        candidate = {
            "type": "alert_rule",
            "name": "CPU高负载告警",
            "condition": "cpu_utilization > 80",
            "severity": "warning",
            "entity_type": "os.linux",
            "resource_type": "os.linux.cpu"
        }

        result = await evolution_service.validate_knowledge(candidate)

        assert result["valid"] is False
        assert any("conflict" in e.lower() for e in result.get("errors", [])) or len(result.get("conflicts", [])) > 0

    @pytest.mark.asyncio
    async def test_assess_coverage_api(self, evolution_service, mock_coverage_assessor):
        """Test assess_coverage public API"""
        from src.knowledge.evolution.coverage_assessor import CoverageReport

        mock_coverage_assessor.assess = AsyncMock(return_value=CoverageReport(
            total_entities=1,
            total_resources=1,
            total_observation_points=1,
            covered_entities=0,
            covered_resources=0,
            covered_observation_points=0,
            gaps=[{"gap_type": "entity"}],
            entity_filter=None
        ))

        result = await evolution_service.assess_coverage()

        assert "total_entities" in result
        assert "gaps" in result
        mock_coverage_assessor.assess.assert_called_once_with(entity_type=None)

    @pytest.mark.asyncio
    async def test_generate_knowledge_api(self, evolution_service, mock_knowledge_generator):
        """Test generate_knowledge public API"""
        gap = {
            "gap_type": "resource",
            "entity_type": "os.linux",
            "resource_type": "os.linux.network"
        }

        mock_knowledge_generator.generate_alert_rule = AsyncMock(return_value={
            "id": "net-alert-001",
            "name": "Network告警",
            "condition": "net_errors > 0",
            "severity": "warning",
            "entity_type": "os.linux",
            "resource_type": "os.linux.network"
        })
        mock_knowledge_generator.generate_sop = AsyncMock(return_value={
            "id": "net-sop-001",
            "title": "Network告警处理",
            "alert_rule_id": "net-alert-001",
            "steps": []
        })

        candidates = await evolution_service.generate_knowledge(gap)

        assert len(candidates) >= 1
        assert any(c["type"] == "alert_rule" for c in candidates)
