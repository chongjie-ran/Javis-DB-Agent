"""Coverage Assessor - Evaluates knowledge base coverage against taxonomy

Analyzes what percentage of taxonomy entities/resources/observation-points
are covered by existing alert rules in the knowledge base.
"""
import structlog
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = structlog.get_logger()


@dataclass
class CoverageReport:
    """Coverage assessment report"""
    total_entities: int = 0
    total_resources: int = 0
    total_observation_points: int = 0
    covered_entities: int = 0
    covered_resources: int = 0
    covered_observation_points: int = 0
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    entity_filter: Optional[str] = None

    @property
    def entity_coverage_rate(self) -> float:
        """Entity coverage rate (0.0 - 1.0)"""
        if self.total_entities == 0:
            return 1.0
        return self.covered_entities / self.total_entities

    @property
    def resource_coverage_rate(self) -> float:
        """Resource coverage rate (0.0 - 1.0)"""
        if self.total_resources == 0:
            return 1.0
        return self.covered_resources / self.total_resources

    @property
    def observation_coverage_rate(self) -> float:
        """Observation point coverage rate (0.0 - 1.0)"""
        if self.total_observation_points == 0:
            return 1.0
        return self.covered_observation_points / self.total_observation_points

    @property
    def overall_coverage_rate(self) -> float:
        """Overall coverage rate weighted by level"""
        total = self.total_entities + self.total_resources + self.total_observation_points
        if total == 0:
            return 1.0
        covered = self.covered_entities + self.covered_resources + self.covered_observation_points
        return covered / total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_entities": self.total_entities,
            "total_resources": self.total_resources,
            "total_observation_points": self.total_observation_points,
            "covered_entities": self.covered_entities,
            "covered_resources": self.covered_resources,
            "covered_observation_points": self.covered_observation_points,
            "entity_coverage_rate": round(self.entity_coverage_rate, 4),
            "resource_coverage_rate": round(self.resource_coverage_rate, 4),
            "observation_coverage_rate": round(self.observation_coverage_rate, 4),
            "overall_coverage_rate": round(self.overall_coverage_rate, 4),
            "gaps": self.gaps,
            "entity_filter": self.entity_filter,
        }


class CoverageAssessor:
    """Assesses knowledge base coverage against taxonomy

    Compares existing alert rules against the taxonomy hierarchy:
    Entity → Resource → ObservationPoint

    Identifies gaps where monitoring coverage is missing.
    """

    def __init__(
        self,
        taxonomy_repo: Any,
        alert_rule_repo: Any,
    ):
        """
        Initialize CoverageAssessor

        Args:
            taxonomy_repo: TaxonomyRepository instance
            alert_rule_repo: AlertRuleRepository instance
        """
        self._taxonomy_repo = taxonomy_repo
        self._alert_rule_repo = alert_rule_repo

    async def assess(self, entity_type: str = None) -> CoverageReport:
        """Assess knowledge base coverage

        Walks the taxonomy hierarchy and compares against alert rules
        to identify uncovered entities, resources, and observation points.

        Args:
            entity_type: Optional entity type filter (e.g. "os.linux", "db.postgresql")

        Returns:
            CoverageReport with coverage statistics and gaps
        """
        logger.info("coverage_assessment.started", entity_filter=entity_type)

        # Collect existing alert rules
        existing_rules = await self._alert_rule_repo.list_all(enabled_only=True)
        covered_entities: set = set()
        covered_resources: set = set()
        covered_observation_points: set = set()

        for rule in existing_rules:
            if rule.get("entity_type"):
                covered_entities.add(rule["entity_type"])
            if rule.get("resource_type"):
                covered_resources.add(rule["resource_type"])
            if rule.get("observation_point"):
                covered_observation_points.add(rule["observation_point"])

        # Walk taxonomy to build coverage map
        gaps: List[Dict[str, Any]] = []
        total_entities = 0
        total_resources = 0
        total_obs_points = 0

        # Get entity types
        entities = await self._taxonomy_repo.list_entity_types(
            category=None,
            parent_id=None,
            limit=500,
            offset=0,
        )

        # Filter by parent (root entities) - or by specific entity_type
        if entity_type:
            filtered_entities = [e for e in entities if e.id == entity_type]
        else:
            filtered_entities = [e for e in entities if e.parent_id is None]

        for entity in filtered_entities:
            total_entities += 1
            entity_id = entity.id

            # Check if entity is covered
            if entity_id not in covered_entities:
                gaps.append({
                    "gap_type": "entity",
                    "entity_type": entity_id,
                    "resource_type": None,
                    "observation_point": None,
                    "description": f"Entity '{entity_id}' ({entity.name}) has no alert rules"
                })

            # Get resources for this entity
            resources = await self._taxonomy_repo.list_resource_types_by_entity(
                entity_type_id=entity_id,
                category=None,
                limit=500,
                offset=0,
            )

            for resource in resources:
                total_resources += 1
                resource_id = resource.id

                if resource_id not in covered_resources:
                    gaps.append({
                        "gap_type": "resource",
                        "entity_type": entity_id,
                        "resource_type": resource_id,
                        "observation_point": None,
                        "description": f"Resource '{resource_id}' ({resource.name}) has no alert rules"
                    })

                # Get observation points for this resource
                obs_points = await self._taxonomy_repo.list_observation_points_by_resource(
                    resource_type_id=resource_id,
                    category=None,
                    limit=500,
                    offset=0,
                )

                for obs_point in obs_points:
                    total_obs_points += 1
                    obs_id = obs_point.id

                    if obs_id not in covered_observation_points:
                        gaps.append({
                            "gap_type": "observation_point",
                            "entity_type": entity_id,
                            "resource_type": resource_id,
                            "observation_point": obs_id,
                            "description": f"Observation point '{obs_id}' ({obs_point.name}) has no alert rules"
                        })

        # Recalculate covered counts based on what we found
        covered_entities_count = total_entities - len([g for g in gaps if g["gap_type"] == "entity"])
        covered_resources_count = total_resources - len([g for g in gaps if g["gap_type"] == "resource"])
        covered_obs_points_count = total_obs_points - len([g for g in gaps if g["gap_type"] == "observation_point"])

        report = CoverageReport(
            total_entities=total_entities,
            total_resources=total_resources,
            total_observation_points=total_obs_points,
            covered_entities=covered_entities_count,
            covered_resources=covered_resources_count,
            covered_observation_points=covered_obs_points_count,
            gaps=gaps,
            entity_filter=entity_type,
        )

        logger.info(
            "coverage_assessment.completed",
            overall_rate=report.overall_coverage_rate,
            total_gaps=len(gaps),
            covered_entities=covered_entities_count,
            total_entities=total_entities,
        )

        return report
