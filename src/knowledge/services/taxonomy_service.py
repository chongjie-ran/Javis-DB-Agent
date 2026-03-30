"""Taxonomy Service - Business logic layer for taxonomy operations"""
import json
from dataclasses import dataclass, field
from typing import Optional, Any
from src.knowledge.db.repositories.taxonomy_repo import (
    TaxonomyRepository,
    EntityType,
    ResourceType,
    ObservationPointType,
)


@dataclass
class EntityTreeNode:
    """Node in the entity tree representing a hierarchical taxonomy"""
    entity: EntityType
    resources: list[dict] = field(default_factory=list)  # List of {resource, observation_points}
    children: list["EntityTreeNode"] = field(default_factory=list)

    def to_dict(self, include_metadata: bool = True) -> dict:
        """Convert node to dictionary representation
        
        Args:
            include_metadata: Whether to include metadata fields
            
        Returns:
            Dictionary representation of the node
        """
        resources_list = []
        for r in self.resources:
            resource_obj = r["resource"]
            # Handle both ResourceType objects and dicts
            if hasattr(resource_obj, "id"):
                resource_dict = {
                    "id": resource_obj.id,
                    "name": resource_obj.name,
                    "category": resource_obj.category,
                    "description": resource_obj.description,
                }
                if include_metadata:
                    resource_dict["metadata"] = resource_obj.metadata
            else:
                resource_dict = dict(resource_obj)
                if not include_metadata and "metadata" in resource_dict:
                    del resource_dict["metadata"]

            obs_points_list = []
            for op in r["observation_points"]:
                # Handle both ObservationPointType objects and dicts
                if hasattr(op, "id"):
                    op_dict = {
                        "id": op.id,
                        "name": op.name,
                        "category": op.category,
                        "unit": op.unit,
                        "description": op.description,
                    }
                else:
                    op_dict = dict(op)
                obs_points_list.append(op_dict)

            resources_list.append({
                "resource": resource_dict,
                "observation_points": obs_points_list,
            })

        result = {
            "entity": {
                "id": self.entity.id,
                "name": self.entity.name,
                "category": self.entity.category,
                "description": self.entity.description,
                "parent_id": self.entity.parent_id,
            },
            "resources": resources_list,
            "children": [child.to_dict(include_metadata) for child in self.children],
        }

        if include_metadata:
            result["entity"]["metadata"] = self.entity.metadata

        return result


class TaxonomyService:
    """Service layer for taxonomy business logic
    
    Provides high-level operations for managing the Entity-Resource-ObservationPoint
    taxonomy hierarchy with caching and tree-building capabilities.
    """

    def __init__(self, taxonomy_repo: Optional[TaxonomyRepository] = None):
        """Initialize service with optional repository
        
        Args:
            taxonomy_repo: Optional TaxonomyRepository instance.
                           If not provided, will be created on first use.
        """
        self._repo = taxonomy_repo
        self._entity_cache: dict[str, EntityType] = {}
        self._resource_cache: dict[str, ResourceType] = {}

    @property
    def repo(self) -> TaxonomyRepository:
        """Get or create repository instance"""
        if self._repo is None:
            raise RuntimeError("TaxonomyRepository not initialized. Call set_repo() first.")
        return self._repo

    def set_repo(self, repo: TaxonomyRepository) -> None:
        """Set repository instance
        
        Args:
            repo: TaxonomyRepository instance
        """
        self._repo = repo

    # =========================================================================
    # Entity Operations
    # =========================================================================

    async def create_entity(
        self,
        id: str,
        name: str,
        category: str,
        description: Optional[str] = None,
        parent_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> EntityType:
        """Create a new entity type
        
        Args:
            id: Unique entity identifier
            name: Human-readable name
            category: Entity category (os, database, application, etc.)
            description: Optional description
            parent_id: Optional parent entity ID for hierarchy
            metadata: Optional metadata dictionary
            
        Returns:
            Created EntityType
        """
        entity = EntityType(
            id=id,
            name=name,
            category=category,
            description=description,
            parent_id=parent_id,
            metadata=metadata or {},
        )

        # Validate parent exists if specified
        if parent_id:
            parent = await self.repo.get_entity_type_by_id(parent_id)
            if not parent:
                raise ValueError(f"Parent entity not found: {parent_id}")

        result = await self.repo.create_entity_type(entity)
        self._entity_cache[id] = result
        return result

    async def get_entity(self, entity_id: str) -> Optional[EntityType]:
        """Get entity by ID
        
        Args:
            entity_id: Entity type ID
            
        Returns:
            EntityType if found, None otherwise
        """
        # Check cache first
        if entity_id in self._entity_cache:
            return self._entity_cache[entity_id]

        result = await self.repo.get_entity_type_by_id(entity_id)
        if result:
            self._entity_cache[entity_id] = result
        return result

    async def list_entities(
        self,
        category: Optional[str] = None,
        parent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EntityType]:
        """List entities with optional filters
        
        Args:
            category: Filter by category
            parent_id: Filter by parent ID (None for root entities)
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of EntityType objects
        """
        # Handle "null" string as None
        if parent_id == "null":
            parent_id = None
        return await self.repo.list_entity_types(
            category=category,
            parent_id=parent_id,
            limit=limit,
            offset=offset,
        )

    async def update_entity(self, entity: EntityType) -> EntityType:
        """Update an entity type
        
        Args:
            entity: EntityType with updated values
            
        Returns:
            Updated EntityType
        """
        result = await self.repo.update_entity_type(entity)
        self._entity_cache[entity.id] = result
        return result

    async def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity type
        
        Args:
            entity_id: Entity type ID to delete
            
        Returns:
            True if deleted
        """
        result = await self.repo.delete_entity_type(entity_id)
        if result and entity_id in self._entity_cache:
            del self._entity_cache[entity_id]
        return result

    async def get_entity_with_resources(self, entity_id: str) -> Optional[dict]:
        """Get entity with all its resources and observation points
        
        Args:
            entity_id: Entity type ID
            
        Returns:
            Dictionary with entity, resources, and observation_points if found
        """
        entity = await self.get_entity(entity_id)
        if not entity:
            return None

        resources = await self.repo.list_resource_types_by_entity(entity_id)
        resource_list = []

        for resource in resources:
            obs_points = await self.repo.list_observation_points_by_resource(resource.id)
            resource_list.append(
                {
                    "resource": resource,
                    "observation_points": obs_points,
                }
            )

        return {
            "entity": entity,
            "resources": resource_list,
        }

    # =========================================================================
    # Resource Operations
    # =========================================================================

    async def create_resource(
        self,
        id: str,
        name: str,
        entity_type_id: str,
        category: str,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ResourceType:
        """Create a new resource type
        
        Args:
            id: Unique resource identifier
            name: Human-readable name
            entity_type_id: Parent entity type ID
            category: Resource category (hardware, software, data, etc.)
            description: Optional description
            metadata: Optional metadata dictionary
            
        Returns:
            Created ResourceType
        """
        # Validate entity exists
        entity = await self.get_entity(entity_type_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type_id}")

        resource = ResourceType(
            id=id,
            name=name,
            entity_type_id=entity_type_id,
            category=category,
            description=description,
            metadata=metadata or {},
        )

        result = await self.repo.create_resource_type(resource)
        self._resource_cache[id] = result
        return result

    async def get_resource(self, resource_id: str) -> Optional[ResourceType]:
        """Get resource by ID
        
        Args:
            resource_id: Resource type ID
            
        Returns:
            ResourceType if found, None otherwise
        """
        if resource_id in self._resource_cache:
            return self._resource_cache[resource_id]

        result = await self.repo.get_resource_type_by_id(resource_id)
        if result:
            self._resource_cache[resource_id] = result
        return result

    async def list_resources_by_entity(
        self,
        entity_type_id: str,
        category: Optional[str] = None,
    ) -> list[ResourceType]:
        """List resources for an entity
        
        Args:
            entity_type_id: Entity type ID
            category: Optional category filter
            
        Returns:
            List of ResourceType objects
        """
        return await self.repo.list_resource_types_by_entity(
            entity_type_id=entity_type_id,
            category=category,
        )

    async def delete_resource(self, resource_id: str) -> bool:
        """Delete a resource type
        
        Args:
            resource_id: Resource type ID to delete
            
        Returns:
            True if deleted
        """
        result = await self.repo.delete_resource_type(resource_id)
        if result and resource_id in self._resource_cache:
            del self._resource_cache[resource_id]
        return result

    async def get_resource_with_observation_points(self, resource_id: str) -> Optional[dict]:
        """Get resource with its observation points
        
        Args:
            resource_id: Resource type ID
            
        Returns:
            Dictionary with resource and observation_points if found
        """
        resource = await self.get_resource(resource_id)
        if not resource:
            return None

        obs_points = await self.repo.list_observation_points_by_resource(resource_id)

        return {
            "resource": resource,
            "observation_points": obs_points,
        }

    # =========================================================================
    # Observation Point Operations
    # =========================================================================

    async def create_observation_point(
        self,
        id: str,
        name: str,
        resource_type_id: str,
        category: str,
        unit: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ObservationPointType:
        """Create a new observation point type
        
        Args:
            id: Unique observation point identifier
            name: Human-readable name
            resource_type_id: Parent resource type ID
            category: Observation category (load, performance, error, etc.)
            unit: Unit of measurement
            description: Optional description
            metadata: Optional metadata dictionary
            
        Returns:
            Created ObservationPointType
        """
        # Validate resource exists
        resource = await self.get_resource(resource_type_id)
        if not resource:
            raise ValueError(f"Resource not found: {resource_type_id}")

        obs_point = ObservationPointType(
            id=id,
            name=name,
            resource_type_id=resource_type_id,
            category=category,
            unit=unit,
            description=description,
            metadata=metadata or {},
        )

        return await self.repo.create_observation_point_type(obs_point)

    async def list_observation_points_by_resource(
        self,
        resource_type_id: str,
        category: Optional[str] = None,
    ) -> list[ObservationPointType]:
        """List observation points for a resource
        
        Args:
            resource_type_id: Resource type ID
            category: Optional category filter
            
        Returns:
            List of ObservationPointType objects
        """
        return await self.repo.list_observation_points_by_resource(
            resource_type_id=resource_type_id,
            category=category,
        )

    async def delete_observation_point(self, obs_point_id: str) -> bool:
        """Delete an observation point type
        
        Args:
            obs_point_id: Observation point type ID to delete
            
        Returns:
            True if deleted
        """
        return await self.repo.delete_observation_point_type(obs_point_id)

    # =========================================================================
    # Tree Operations
    # =========================================================================

    async def build_entity_tree(self) -> list[EntityTreeNode]:
        """Build complete entity tree with resources and observation points
        
        Returns:
            List of root EntityTreeNode objects with nested children
        """
        # Get all entities
        all_entities = await self.repo.list_entity_types(limit=1000)

        # Get all resources
        all_resources_by_entity: dict[str, list[ResourceType]] = {}
        for entity in all_entities:
            resources = await self.repo.list_resource_types_by_entity(entity.id, limit=1000)
            all_resources_by_entity[entity.id] = resources

        # Get all observation points
        all_obs_points_by_resource: dict[str, list[ObservationPointType]] = {}
        for entity_id, resources in all_resources_by_entity.items():
            for resource in resources:
                obs_points = await self.repo.list_observation_points_by_resource(resource.id, limit=1000)
                all_obs_points_by_resource[resource.id] = obs_points

        # Build entity map
        entity_map: dict[str, EntityTreeNode] = {}
        for entity in all_entities:
            # Get resources and observation points
            resources = all_resources_by_entity.get(entity.id, [])
            resource_nodes = []
            for resource in resources:
                obs_points = all_obs_points_by_resource.get(resource.id, [])
                resource_nodes.append({
                    "resource": resource,
                    "observation_points": obs_points,
                })

            node = EntityTreeNode(
                entity=entity,
                resources=resource_nodes,
                children=[],
            )
            entity_map[entity.id] = node

        # Build parent-child relationships
        roots: list[EntityTreeNode] = []
        for entity in all_entities:
            node = entity_map[entity.id]
            if entity.parent_id and entity.parent_id in entity_map:
                entity_map[entity.parent_id].children.append(node)
            elif entity.parent_id is None:
                roots.append(node)

        return roots

    def build_entity_tree_sync(self) -> list[EntityTreeNode]:
        """Synchronous version of build_entity_tree - for testing
        
        Note: This requires _entity_cache and _resource_cache to be populated
        """
        # Build from cache
        entity_map: dict[str, EntityTreeNode] = {}

        for entity_id, entity in self._entity_cache.items():
            resource_list = []
            resource_nodes = []

            # Find resources for this entity
            for resource_id, resource in self._resource_cache.items():
                if resource.entity_type_id == entity_id:
                    resource_nodes.append({
                        "resource": resource,
                        "observation_points": [],
                    })

            node = EntityTreeNode(
                entity=entity,
                resources=resource_nodes,
                children=[],
            )
            entity_map[entity_id] = node

        # Build parent-child relationships
        roots: list[EntityTreeNode] = []
        for entity_id, node in entity_map.items():
            if node.entity.parent_id and node.entity.parent_id in entity_map:
                entity_map[node.entity.parent_id].children.append(node)
            elif node.entity.parent_id is None:
                roots.append(node)

        return roots

    def tree_to_dict(self, tree: list[EntityTreeNode]) -> list[dict]:
        """Convert tree to dictionary format
        
        Args:
            tree: List of EntityTreeNode objects
            
        Returns:
            List of dictionary representations
        """
        return [node.to_dict() for node in tree]

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    async def bulk_import_taxonomy(
        self,
        entities: list[EntityType],
        resources: list[ResourceType],
        observation_points: list[ObservationPointType],
    ) -> dict:
        """Bulk import taxonomy data
        
        Args:
            entities: List of entity types to import
            resources: List of resource types to import
            observation_points: List of observation point types to import
            
        Returns:
            Dictionary with counts of imported items
        """
        # Import entities first
        await self.repo.bulk_create_entity_types(entities)

        # Then resources
        await self.repo.bulk_create_resource_types(resources)

        # Finally observation points
        await self.repo.bulk_create_observation_point_types(observation_points)

        return {
            "entities": len(entities),
            "resources": len(resources),
            "observation_points": len(observation_points),
        }

    # =========================================================================
    # Cache Management
    # =========================================================================

    def clear_cache(self) -> None:
        """Clear all caches"""
        self._entity_cache.clear()
        self._resource_cache.clear()

    def warm_cache(self, entity_ids: Optional[list[str]] = None) -> None:
        """Warm cache with entity and resource data
        
        Args:
            entity_ids: Optional list of entity IDs to warm. If None, warms all.
        """
        import asyncio

        async def _warm():
            if entity_ids:
                for entity_id in entity_ids:
                    entity = await self.repo.get_entity_type_by_id(entity_id)
                    if entity:
                        self._entity_cache[entity_id] = entity
                        resources = await self.repo.list_resource_types_by_entity(entity_id)
                        for resource in resources:
                            self._resource_cache[resource.id] = resource
            else:
                # Warm all
                entities = await self.repo.list_entity_types(limit=10000)
                for entity in entities:
                    self._entity_cache[entity.id] = entity
                    resources = await self.repo.list_resource_types_by_entity(entity.id, limit=1000)
                    for resource in resources:
                        self._resource_cache[resource.id] = resource

        asyncio.run(_warm())
