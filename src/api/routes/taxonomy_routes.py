"""Taxonomy API Routes - REST endpoints for taxonomy operations"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.knowledge.services.taxonomy_service import TaxonomyService
from src.knowledge.db.repositories.taxonomy_repo import (
    TaxonomyRepository,
    EntityType,
    ResourceType,
    ObservationPointType,
)

router = APIRouter(prefix="/api/v1/taxonomy", tags=["taxonomy"])

# Global service instance
_taxonomy_service: Optional[TaxonomyService] = None
_taxonomy_repo: Optional[TaxonomyRepository] = None


def get_taxonomy_service() -> TaxonomyService:
    """Get or create taxonomy service instance"""
    global _taxonomy_service, _taxonomy_repo
    if _taxonomy_service is None:
        # This would be initialized from app startup
        # For now, return a placeholder that can be injected
        if _taxonomy_repo is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Taxonomy repository not initialized",
            )
        _taxonomy_service = TaxonomyService(taxonomy_repo=_taxonomy_repo)
    return _taxonomy_service


def init_taxonomy_routes(repo: TaxonomyRepository) -> None:
    """Initialize taxonomy routes with repository
    
    Args:
        repo: TaxonomyRepository instance
    """
    global _taxonomy_service, _taxonomy_repo
    _taxonomy_repo = repo
    _taxonomy_service = TaxonomyService(taxonomy_repo=repo)


# =============================================================================
# Request/Response Models
# =============================================================================


class EntityCreate(BaseModel):
    """Request model for creating an entity"""
    id: str = Field(..., description="Unique entity identifier")
    name: str = Field(..., description="Human-readable name")
    category: str = Field(..., description="Entity category (os, database, application, etc.)")
    description: Optional[str] = Field(None, description="Optional description")
    parent_id: Optional[str] = Field(None, description="Parent entity ID for hierarchy")
    metadata: Optional[dict] = Field(default_factory=dict, description="Optional metadata")


class ResourceCreate(BaseModel):
    """Request model for creating a resource"""
    id: str = Field(..., description="Unique resource identifier")
    name: str = Field(..., description="Human-readable name")
    entity_type_id: str = Field(..., description="Parent entity type ID")
    category: str = Field(..., description="Resource category (hardware, software, data, etc.)")
    description: Optional[str] = Field(None, description="Optional description")
    metadata: Optional[dict] = Field(default_factory=dict, description="Optional metadata")


class ObservationPointCreate(BaseModel):
    """Request model for creating an observation point"""
    id: str = Field(..., description="Unique observation point identifier")
    name: str = Field(..., description="Human-readable name")
    resource_type_id: str = Field(..., description="Parent resource type ID")
    category: str = Field(..., description="Observation category (load, performance, error, etc.)")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    description: Optional[str] = Field(None, description="Optional description")
    metadata: Optional[dict] = Field(default_factory=dict, description="Optional metadata")


class EntityResponse(BaseModel):
    """Response model for entity"""
    id: str
    name: str
    category: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    metadata: Optional[dict] = None


class ResourceResponse(BaseModel):
    """Response model for resource"""
    id: str
    name: str
    entity_type_id: str
    category: str
    description: Optional[str] = None
    metadata: Optional[dict] = None


class ObservationPointResponse(BaseModel):
    """Response model for observation point"""
    id: str
    name: str
    resource_type_id: str
    category: str
    unit: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None


class PaginatedResponse(BaseModel):
    """Paginated response wrapper"""
    items: list
    total: int
    limit: int
    offset: int


class EntityWithResourcesResponse(BaseModel):
    """Response model for entity with resources"""
    entity: EntityResponse
    resources: list[dict]


class ResourceWithObservationPointsResponse(BaseModel):
    """Response model for resource with observation points"""
    resource: ResourceResponse
    observation_points: list[ObservationPointResponse]


class EntityTreeResponse(BaseModel):
    """Response model for entity tree"""
    tree: list[dict]
    total: int


# =============================================================================
# Entity Endpoints
# =============================================================================


@router.get("/entities", response_model=PaginatedResponse)
async def list_entities(
    category: Optional[str] = Query(None, description="Filter by category"),
    parent_id: Optional[str] = Query(None, description="Filter by parent ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """List all entity types with optional filters
    
    Returns paginated list of entities.
    """
    try:
        service = get_taxonomy_service()
        entities = await service.list_entities(
            category=category,
            parent_id=parent_id,
            limit=limit,
            offset=offset,
        )
        return PaginatedResponse(
            items=[EntityResponse(
                id=e.id,
                name=e.name,
                category=e.category,
                description=e.description,
                parent_id=e.parent_id,
                metadata=e.metadata,
            ).model_dump() for e in entities],
            total=len(entities),
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/entities/{entity_id}", response_model=EntityWithResourcesResponse)
async def get_entity(entity_id: str):
    """Get entity with all its resources and observation points
    
    Returns entity details along with its resources and observation points.
    """
    try:
        service = get_taxonomy_service()
        result = await service.get_entity_with_resources(entity_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

        return EntityWithResourcesResponse(
            entity=EntityResponse(
                id=result["entity"].id,
                name=result["entity"].name,
                category=result["entity"].category,
                description=result["entity"].description,
                parent_id=result["entity"].parent_id,
                metadata=result["entity"].metadata,
            ).model_dump(),
            resources=[
                {
                    "resource": ResourceResponse(
                        id=r["resource"].id,
                        name=r["resource"].name,
                        entity_type_id=r["resource"].entity_type_id,
                        category=r["resource"].category,
                        description=r["resource"].description,
                        metadata=r["resource"].metadata,
                    ).model_dump(),
                    "observation_points": [
                        ObservationPointResponse(
                            id=op.id,
                            name=op.name,
                            resource_type_id=op.resource_type_id,
                            category=op.category,
                            unit=op.unit,
                            description=op.description,
                            metadata=op.metadata,
                        ).model_dump()
                        for op in r["observation_points"]
                    ],
                }
                for r in result["resources"]
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
async def create_entity(entity: EntityCreate):
    """Create a new entity type
    
    Creates a new entity in the taxonomy hierarchy.
    """
    try:
        service = get_taxonomy_service()
        result = await service.create_entity(
            id=entity.id,
            name=entity.name,
            category=entity.category,
            description=entity.description,
            parent_id=entity.parent_id,
            metadata=entity.metadata,
        )
        return EntityResponse(
            id=result.id,
            name=result.name,
            category=result.category,
            description=result.description,
            parent_id=result.parent_id,
            metadata=result.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(entity_id: str):
    """Delete an entity type
    
    Deletes entity and cascades to resources and observation points.
    """
    try:
        service = get_taxonomy_service()
        deleted = await service.delete_entity(entity_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# Resource Endpoints
# =============================================================================


@router.get("/resources/{entity_id}", response_model=EntityWithResourcesResponse)
async def list_resources_by_entity(entity_id: str):
    """Get resources for an entity
    
    Returns all resources belonging to the specified entity with their observation points.
    """
    try:
        service = get_taxonomy_service()
        result = await service.get_entity_with_resources(entity_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")

        return EntityWithResourcesResponse(
            entity=EntityResponse(
                id=result["entity"].id,
                name=result["entity"].name,
                category=result["entity"].category,
                description=result["entity"].description,
                parent_id=result["entity"].parent_id,
                metadata=result["entity"].metadata,
            ).model_dump(),
            resources=[
                {
                    "resource": ResourceResponse(
                        id=r["resource"].id,
                        name=r["resource"].name,
                        entity_type_id=r["resource"].entity_type_id,
                        category=r["resource"].category,
                        description=r["resource"].description,
                        metadata=r["resource"].metadata,
                    ).model_dump(),
                    "observation_points": [
                        ObservationPointResponse(
                            id=op.id,
                            name=op.name,
                            resource_type_id=op.resource_type_id,
                            category=op.category,
                            unit=op.unit,
                            description=op.description,
                            metadata=op.metadata,
                        ).model_dump()
                        for op in r["observation_points"]
                    ],
                }
                for r in result["resources"]
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(resource: ResourceCreate):
    """Create a new resource type
    
    Creates a new resource belonging to an entity.
    """
    try:
        service = get_taxonomy_service()
        result = await service.create_resource(
            id=resource.id,
            name=resource.name,
            entity_type_id=resource.entity_type_id,
            category=resource.category,
            description=resource.description,
            metadata=resource.metadata,
        )
        return ResourceResponse(
            id=result.id,
            name=result.name,
            entity_type_id=result.entity_type_id,
            category=result.category,
            description=result.description,
            metadata=result.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(resource_id: str):
    """Delete a resource type
    
    Deletes resource and cascades to observation points.
    """
    try:
        service = get_taxonomy_service()
        deleted = await service.delete_resource(resource_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# Observation Point Endpoints
# =============================================================================


@router.get("/observation-points/{resource_id}", response_model=ResourceWithObservationPointsResponse)
async def list_observation_points_by_resource(resource_id: str):
    """Get observation points for a resource
    
    Returns all observation points belonging to the specified resource.
    """
    try:
        service = get_taxonomy_service()
        result = await service.get_resource_with_observation_points(resource_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

        return ResourceWithObservationPointsResponse(
            resource=ResourceResponse(
                id=result["resource"].id,
                name=result["resource"].name,
                entity_type_id=result["resource"].entity_type_id,
                category=result["resource"].category,
                description=result["resource"].description,
                metadata=result["resource"].metadata,
            ).model_dump(),
            observation_points=[
                ObservationPointResponse(
                    id=op.id,
                    name=op.name,
                    resource_type_id=op.resource_type_id,
                    category=op.category,
                    unit=op.unit,
                    description=op.description,
                    metadata=op.metadata,
                ).model_dump()
                for op in result["observation_points"]
            ],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/observation-points", response_model=ObservationPointResponse, status_code=status.HTTP_201_CREATED)
async def create_observation_point(obs_point: ObservationPointCreate):
    """Create a new observation point type
    
    Creates a new observation point belonging to a resource.
    """
    try:
        service = get_taxonomy_service()
        result = await service.create_observation_point(
            id=obs_point.id,
            name=obs_point.name,
            resource_type_id=obs_point.resource_type_id,
            category=obs_point.category,
            unit=obs_point.unit,
            description=obs_point.description,
            metadata=obs_point.metadata,
        )
        return ObservationPointResponse(
            id=result.id,
            name=result.name,
            resource_type_id=result.resource_type_id,
            category=result.category,
            unit=result.unit,
            description=result.description,
            metadata=result.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/observation-points/{obs_point_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_observation_point(obs_point_id: str):
    """Delete an observation point type"""
    try:
        service = get_taxonomy_service()
        deleted = await service.delete_observation_point(obs_point_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Observation point not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# Tree Endpoint
# =============================================================================


@router.get("/tree", response_model=EntityTreeResponse)
async def get_entity_tree():
    """Get complete entity tree
    
    Returns the full taxonomy hierarchy with entities, resources, and observation points.
    """
    try:
        service = get_taxonomy_service()
        tree = await service.build_entity_tree()
        return EntityTreeResponse(
            tree=service.tree_to_dict(tree),
            total=len(tree),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# =============================================================================
# Utility Endpoints
# =============================================================================


@router.get("/categories")
async def get_categories():
    """Get all valid taxonomy categories
    
    Returns valid categories for entities, resources, and observation points.
    """
    return {
        "entity_categories": list(TaxonomyRepository.VALID_ENTITY_CATEGORIES),
        "resource_categories": list(TaxonomyRepository.VALID_RESOURCE_CATEGORIES),
        "observation_categories": list(TaxonomyRepository.VALID_OBSERVATION_CATEGORIES),
    }
