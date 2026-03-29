"""Knowledge Base Evolution Module - Round 21
Self-evolution loop driven by LLM + observability coverage assessment.
"""
from .evolution_service import EvolutionService
from .coverage_assessor import CoverageAssessor, CoverageReport
from .knowledge_generator import KnowledgeGenerator

__all__ = [
    "EvolutionService",
    "CoverageAssessor",
    "CoverageReport",
    "KnowledgeGenerator",
]
