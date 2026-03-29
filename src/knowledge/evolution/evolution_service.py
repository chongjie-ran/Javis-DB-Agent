"""Evolution Service - Orchestrates the knowledge base self-evolution loop

The self-evolution loop:
  [可观测数据] → [覆盖度评估] → [知识生成] → [知识验证] → [知识库更新]

This service coordinates:
1. Coverage assessment (CoverageAssessor)
2. Knowledge generation (KnowledgeGenerator)
3. Knowledge validation
4. Knowledge base update
"""
import structlog
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = structlog.get_logger()


@dataclass
class EvolutionResult:
    """Result of an evolution run"""
    total_gaps: int = 0
    candidates_generated: int = 0
    validated_count: int = 0
    updated_count: int = 0
    conflicts: int = 0
    errors: int = 0
    success: bool = False
    details: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_gaps": self.total_gaps,
            "candidates_generated": self.candidates_generated,
            "validated_count": self.validated_count,
            "updated_count": self.updated_count,
            "conflicts": self.conflicts,
            "errors": self.errors,
            "success": self.success,
            "details": self.details,
        }


class EvolutionService:
    """Knowledge base self-evolution service

    Orchestrates the full evolution loop:
    1. Assess coverage gaps
    2. Generate candidate knowledge (alert rules, SOPs, cases)
    3. Validate candidates
    4. Update knowledge base
    """

    def __init__(
        self,
        coverage_assessor: Any = None,
        knowledge_generator: Any = None,
        kb_service: Any = None,
    ):
        """
        Initialize EvolutionService

        Args:
            coverage_assessor: CoverageAssessor instance
            knowledge_generator: KnowledgeGenerator instance
            kb_service: KnowledgeBaseService instance
        """
        self._coverage_assessor = coverage_assessor
        self._knowledge_generator = knowledge_generator
        self._kb_service = kb_service

    # =========================================================================
    # Public API
    # =========================================================================

    async def assess_coverage(self, entity_type: str = None) -> Dict[str, Any]:
        """Assess knowledge base coverage

        Args:
            entity_type: Optional entity type filter

        Returns:
            Coverage report as dict
        """
        if self._coverage_assessor is None:
            return {"error": "CoverageAssessor not initialized"}

        report = await self._coverage_assessor.assess(entity_type=entity_type)
        return report.to_dict()

    async def generate_knowledge(self, gap: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate candidate knowledge from a coverage gap

        Generates an alert rule + associated SOP from a gap.

        Args:
            gap: Coverage gap dict

        Returns:
            List of candidate knowledge items
        """
        if self._knowledge_generator is None:
            logger.warning("knowledge_generator.not_initialized")
            return []

        candidates = []

        # Generate alert rule
        alert_rule = await self._knowledge_generator.generate_alert_rule(gap)
        if alert_rule:
            alert_rule["type"] = "alert_rule"
            candidates.append(alert_rule)

            # Generate SOP for the alert rule
            sop = await self._knowledge_generator.generate_sop(alert_rule)
            if sop:
                sop["type"] = "sop"
                candidates.append(sop)

        return candidates

    async def validate_knowledge(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a candidate knowledge item

        Checks:
        - Syntax validation (required fields present)
        - Semantic validation (field values valid)
        - Conflict detection (no duplicate with existing knowledge)

        Args:
            candidate: Candidate knowledge dict

        Returns:
            Validation result dict with valid, errors, conflicts
        """
        errors: List[str] = []
        warnings: List[str] = []
        conflicts: List[Dict[str, Any]] = []

        content_type = candidate.get("type", "unknown")

        # Syntax validation
        if content_type == "alert_rule":
            errors.extend(self._validate_alert_rule_syntax(candidate))
        elif content_type == "sop":
            errors.extend(self._validate_sop_syntax(candidate))
        elif content_type == "case":
            errors.extend(self._validate_case_syntax(candidate))

        # Semantic validation
        if content_type == "alert_rule":
            warnings.extend(self._validate_alert_rule_semantic(candidate))

        # Conflict detection
        if self._kb_service and content_type == "alert_rule":
            conflicts = await self._check_alert_rule_conflicts(candidate)

        valid = len(errors) == 0 and len(conflicts) == 0

        return {
            "valid": valid,
            "errors": errors,
            "warnings": warnings,
            "conflicts": conflicts,
        }

    async def evolve(self, entity_type: str = None) -> EvolutionResult:
        """Execute the full self-evolution loop

        Flow: assess → generate → validate → update

        Args:
            entity_type: Optional entity type filter

        Returns:
            EvolutionResult with statistics
        """
        logger.info("evolution.started", entity_type=entity_type)

        result = EvolutionResult()

        # Step 1: Assess coverage
        if self._coverage_assessor is None:
            logger.error("evolution.coverage_assessor_not_initialized")
            result.errors += 1
            return result

        coverage_report = await self._coverage_assessor.assess(entity_type=entity_type)
        gaps = coverage_report.gaps
        result.total_gaps = len(gaps)

        if not gaps:
            logger.info("evolution.no_gaps_found", entity_type=entity_type)
            result.success = True
            return result

        # Step 2: Generate candidates for each gap
        all_candidates: List[Dict[str, Any]] = []
        for gap in gaps:
            candidates = await self.generate_knowledge(gap)
            all_candidates.extend(candidates)

        result.candidates_generated = len(all_candidates)
        logger.info("evolution.candidates_generated", count=len(all_candidates))

        # Step 3: Validate each candidate
        validated_candidates: List[Dict[str, Any]] = []
        for candidate in all_candidates:
            validation = await self.validate_knowledge(candidate)
            candidate["_validation"] = validation
            result.validated_count += 1

            if validation["valid"]:
                validated_candidates.append(candidate)
            else:
                if validation.get("conflicts"):
                    result.conflicts += 1
                logger.debug("evolution.candidate_rejected", candidate_id=candidate.get("id"), errors=validation.get("errors"))

        # Step 4: Update knowledge base with validated candidates
        for candidate in validated_candidates:
            content_type = candidate.pop("type", None)
            candidate.pop("_validation", None)

            try:
                if content_type == "alert_rule":
                    if self._kb_service:
                        await self._kb_service.create_alert_rule(candidate)
                        result.updated_count += 1
                        logger.info("evolution.alert_rule_created", rule_id=candidate.get("id"))
                elif content_type == "sop":
                    if self._kb_service:
                        await self._kb_service.create_sop(candidate)
                        result.updated_count += 1
                        logger.info("evolution.sop_created", sop_id=candidate.get("id"))
                elif content_type == "case":
                    if self._kb_service:
                        await self._kb_service.create_case(candidate)
                        result.updated_count += 1
                        logger.info("evolution.case_created", case_id=candidate.get("id"))

                result.details.append({
                    "type": content_type,
                    "id": candidate.get("id"),
                    "status": "created"
                })
            except Exception as e:
                result.errors += 1
                logger.error("evolution.update_failed", candidate_id=candidate.get("id"), error=str(e))
                result.details.append({
                    "type": content_type,
                    "id": candidate.get("id"),
                    "status": "failed",
                    "error": str(e)
                })

        result.success = result.errors == 0
        logger.info(
            "evolution.completed",
            total_gaps=result.total_gaps,
            candidates_generated=result.candidates_generated,
            validated_count=result.validated_count,
            updated_count=result.updated_count,
            conflicts=result.conflicts,
            errors=result.errors,
            success=result.success,
        )

        return result

    # =========================================================================
    # Validation Helpers
    # =========================================================================

    def _validate_alert_rule_syntax(self, rule: Dict[str, Any]) -> List[str]:
        """Validate alert rule syntax (required fields)"""
        errors = []
        required_fields = ["name", "condition", "severity"]

        for field_name in required_fields:
            if not rule.get(field_name):
                errors.append(f"Missing required field: {field_name}")

        # Validate severity
        valid_severities = {"critical", "warning", "info"}
        severity = rule.get("severity", "")
        if severity and severity not in valid_severities:
            errors.append(f"Invalid severity '{severity}', must be one of {valid_severities}")

        return errors

    def _validate_sop_syntax(self, sop: Dict[str, Any]) -> List[str]:
        """Validate SOP syntax (required fields)"""
        errors = []
        if not sop.get("title"):
            errors.append("Missing required field: title")
        if not sop.get("steps"):
            errors.append("Missing required field: steps")
        elif not isinstance(sop["steps"], list):
            errors.append("Field 'steps' must be a list")
        elif len(sop["steps"]) == 0:
            errors.append("Field 'steps' cannot be empty")

        return errors

    def _validate_case_syntax(self, case: Dict[str, Any]) -> List[str]:
        """Validate case syntax (required fields)"""
        errors = []
        if not case.get("title"):
            errors.append("Missing required field: title")
        return errors

    def _validate_alert_rule_semantic(self, rule: Dict[str, Any]) -> List[str]:
        """Validate alert rule semantics (field values make sense)"""
        warnings = []

        # Check condition format (basic sanity check)
        condition = rule.get("condition", "")
        if condition and not any(op in condition for op in [">", "<", "=", "!=", ">=", "<="]):
            warnings.append(f"Condition '{condition}' may not contain comparison operators")

        # Check name is not too generic
        name = rule.get("name", "")
        generic_names = {"告警", "监控", "test", "测试", "temp"}
        if name and name.lower() in [n.lower() for n in generic_names]:
            warnings.append(f"Alert name '{name}' is too generic")

        return warnings

    async def _check_alert_rule_conflicts(self, rule: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for conflicts with existing alert rules"""
        conflicts = []

        if not self._kb_service:
            return conflicts

        try:
            existing_rules = await self._kb_service.list_alert_rules(enabled_only=False)

            for existing in existing_rules:
                # Check for same entity+resource+obs_point combination
                same_entity = existing.get("entity_type") == rule.get("entity_type")
                same_resource = existing.get("resource_type") == rule.get("resource_type")
                same_obs = existing.get("observation_point") == rule.get("observation_point")

                if same_entity and same_resource and same_obs:
                    # Check if severity is also the same (higher priority conflict)
                    same_severity = existing.get("severity") == rule.get("severity")

                    conflicts.append({
                        "existing_id": existing.get("id"),
                        "existing_name": existing.get("name"),
                        "match": "same_target",
                        "severity_match": same_severity,
                        "message": f"Alert rule for {rule.get('entity_type')}/{rule.get('resource_type')} already exists"
                    })
        except Exception as e:
            logger.warning("conflict_check.failed", error=str(e))

        return conflicts
