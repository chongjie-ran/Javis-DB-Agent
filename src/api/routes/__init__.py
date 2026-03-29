"""API route modules"""
from fastapi import APIRouter
from src.api.routes.evolution_routes import router as evolution_router
from src.api.routes.taxonomy_routes import router as taxonomy_router

router = APIRouter(prefix="/api/v1", tags=["knowledge"])
router.include_router(evolution_router)
router.include_router(taxonomy_router)
