"""Evolution API Routes - Round 21
REST endpoints for knowledge base self-evolution
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.knowledge.evolution import (
    EvolutionService,
    CoverageAssessor,
    KnowledgeGenerator,
)
from src.knowledge.services.knowledge_base_service import KnowledgeBaseService
from src.knowledge.db.repositories.taxonomy_repo import TaxonomyRepository
from src.knowledge.db.repositories.alert_rule_repo import AlertRuleRepository
from src.knowledge.db.database import get_knowledge_db
from src.llm.ollama_client import OllamaClient

router = APIRouter(prefix="/api/v1/knowledge/evolution", tags=["knowledge", "evolution"])

# Global instances
_evolution_service: Optional[EvolutionService] = None
_coverage_assessor: Optional[CoverageAssessor] = None
_knowledge_generator: Optional[KnowledgeGenerator] = None
_kb_service: Optional[KnowledgeBaseService] = None


async def _ensure_initialized():
    """Ensure all services are initialized"""
    global _evolution_service, _coverage_assessor, _knowledge_generator, _kb_service

    if _evolution_service is not None:
        return

    conn = await get_knowledge_db()

    # Create repositories
    taxonomy_repo = TaxonomyRepository(conn)
    alert_rule_repo = AlertRuleRepository(conn)

    # Create LLM client
    llm_client = OllamaClient()

    # Create services
    _coverage_assessor = CoverageAssessor(
        taxonomy_repo=taxonomy_repo,
        alert_rule_repo=alert_rule_repo,
    )
    _knowledge_generator = KnowledgeGenerator(llm_client=llm_client)
    _kb_service = KnowledgeBaseService(conn)
    _evolution_service = EvolutionService(
        coverage_assessor=_coverage_assessor,
        knowledge_generator=_knowledge_generator,
        kb_service=_kb_service,
    )


def get_evolution_service() -> EvolutionService:
    """Get evolution service instance"""
    if _evolution_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evolution service not initialized"
        )
    return _evolution_service


# =============================================================================
# Request/Response Models
# =============================================================================


class AssessCoverageRequest(BaseModel):
    """Request to assess coverage"""
    entity_type: Optional[str] = Field(None, description="Filter by entity type (e.g., 'os.linux')")


class GenerateKnowledgeRequest(BaseModel):
    """Request to generate knowledge from a gap"""
    gap_type: str = Field(..., description="Gap type: entity, resource, or observation_point")
    entity_type: str = Field(..., description="Entity type ID")
    resource_type: Optional[str] = Field(None, description="Resource type ID")
    observation_point: Optional[str] = Field(None, description="Observation point ID")
    description: Optional[str] = Field(None, description="Gap description")


class ValidateKnowledgeRequest(BaseModel):
    """Request to validate a candidate knowledge item"""
    type: str = Field(..., description="Knowledge type: alert_rule, sop, case")
    name: Optional[str] = Field(None, description="Name/title")
    title: Optional[str] = Field(None, description="Title (for SOP/case)")
    condition: Optional[str] = Field(None, description="Alert condition")
    severity: Optional[str] = Field(None, description="Severity: critical/warning/info")
    entity_type: Optional[str] = Field(None, description="Entity type")
    resource_type: Optional[str] = Field(None, description="Resource type")
    observation_point: Optional[str] = Field(None, description="Observation point")
    steps: Optional[List[Dict]] = Field(None, description="SOP steps")
    metadata: Optional[Dict] = Field(None, description="Additional metadata")


class EvolveRequest(BaseModel):
    """Request to execute evolution"""
    entity_type: Optional[str] = Field(None, description="Filter by entity type")


class CoverageResponse(BaseModel):
    """Coverage assessment response"""
    total_entities: int
    total_resources: int
    total_observation_points: int
    covered_entities: int
    covered_resources: int
    covered_observation_points: int
    entity_coverage_rate: float
    resource_coverage_rate: float
    observation_coverage_rate: float
    overall_coverage_rate: float
    gaps: List[Dict[str, Any]]
    entity_filter: Optional[str]


class KnowledgeCandidateResponse(BaseModel):
    """Generated knowledge candidate"""
    type: str
    id: str
    name: Optional[str] = None
    title: Optional[str] = None
    condition: Optional[str] = None
    severity: Optional[str] = None
    steps: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None


class ValidationResponse(BaseModel):
    """Validation result"""
    valid: bool
    errors: List[str]
    warnings: List[str]
    conflicts: List[Dict[str, Any]]


class EvolutionResultResponse(BaseModel):
    """Evolution execution result"""
    total_gaps: int
    candidates_generated: int
    validated_count: int
    updated_count: int
    conflicts: int
    errors: int
    success: bool
    details: List[Dict[str, Any]]


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/assess", response_model=CoverageResponse)
async def assess_coverage(request: AssessCoverageRequest = None):
    """Assess knowledge base coverage against taxonomy

    Returns coverage statistics and identified gaps where
    alert rules are missing.
    """
    await _ensure_initialized()
    service = get_evolution_service()

    entity_type = request.entity_type if request else None
    report = await service.assess_coverage(entity_type=entity_type)
    return report


@router.post("/generate", response_model=List[KnowledgeCandidateResponse])
async def generate_knowledge(request: GenerateKnowledgeRequest):
    """Generate candidate knowledge from a coverage gap

    Generates alert rule and SOP based on the gap information.
    """
    await _ensure_initialized()
    service = get_evolution_service()

    gap = {
        "gap_type": request.gap_type,
        "entity_type": request.entity_type,
        "resource_type": request.resource_type,
        "observation_point": request.observation_point,
        "description": request.description or f"Gap in {request.gap_type}: {request.entity_type}",
    }

    candidates = await service.generate_knowledge(gap)
    return candidates


@router.post("/validate", response_model=ValidationResponse)
async def validate_knowledge(request: ValidateKnowledgeRequest):
    """Validate a candidate knowledge item

    Checks syntax, semantics, and conflicts with existing knowledge.
    """
    await _ensure_initialized()
    service = get_evolution_service()

    candidate = {
        "type": request.type,
        "name": request.name or request.title,
        "title": request.title,
        "condition": request.condition,
        "severity": request.severity,
        "entity_type": request.entity_type,
        "resource_type": request.resource_type,
        "observation_point": request.observation_point,
        "steps": request.steps,
        "metadata": request.metadata,
    }

    result = await service.validate_knowledge(candidate)
    return result


@router.post("/evolve", response_model=EvolutionResultResponse)
async def evolve(request: EvolveRequest = None):
    """Execute the self-evolution loop

    Full flow: assess coverage → generate knowledge → validate → update knowledge base

    This may generate new alert rules, SOPs, and cases based on
    identified coverage gaps.
    """
    await _ensure_initialized()
    service = get_evolution_service()

    entity_type = request.entity_type if request else None
    result = await service.evolve(entity_type=entity_type)
    return result.to_dict()


@router.get("/status")
async def evolution_status():
    """Get evolution service status"""
    await _ensure_initialized()
    return {
        "status": "ready",
        "coverage_assessor": _coverage_assessor is not None,
        "knowledge_generator": _knowledge_generator is not None,
        "kb_service": _kb_service is not None,
    }
