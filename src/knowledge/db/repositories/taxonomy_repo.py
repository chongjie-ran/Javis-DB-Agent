"""Taxonomy Repository - Data access layer for taxonomy entities"""
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from datetime import datetime


@dataclass
class EntityType:
    """Entity type representation (OS, Database, Application, etc.)"""
    id: str
    name: str
    category: str  # 'os', 'database', 'application', 'network', 'storage', 'security', 'middleware'
    description: Optional[str] = None
    parent_id: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if isinstance(self.metadata, str):
            self.metadata = json.loads(self.metadata)


@dataclass
class ResourceType:
    """Resource type representation (CPU, Memory, Session, etc.)"""
    id: str
    name: str
    entity_type_id: str
    category: str  # 'hardware', 'software', 'data', 'network', 'memory', 'compute', 'storage', 'service', 'process'
    description: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if isinstance(self.metadata, str):
            self.metadata = json.loads(self.metadata)


@dataclass
class ObservationPointType:
    """Observation point type representation (load, performance, error, etc.)"""
    id: str
    name: str
    resource_type_id: str
    category: str  # 'load', 'performance', 'error', 'security', 'config', 'health', 'availability', 'throughput', 'latency'
    unit: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if isinstance(self.metadata, str):
            self.metadata = json.loads(self.metadata)


class TaxonomyRepository:
    """Repository for taxonomy CRUD operations with async database access"""

    VALID_ENTITY_CATEGORIES = {"os", "database", "application", "network", "storage", "security", "middleware"}
    VALID_RESOURCE_CATEGORIES = {"hardware", "software", "data", "network", "memory", "compute", "storage", "service", "process"}
    VALID_OBSERVATION_CATEGORIES = {"load", "performance", "error", "security", "config", "health", "availability", "throughput", "latency"}

    def __init__(self, db_pool: Any):
        """Initialize repository with database connection pool
        
        Args:
            db_pool: Async database connection pool (supports acquire/release)
        """
        self.db_pool = db_pool

    # =========================================================================
    # Entity Type Operations
    # =========================================================================

    async def create_entity_type(self, entity: EntityType) -> EntityType:
        """Create a new entity type
        
        Args:
            entity: EntityType to create
            
        Returns:
            Created EntityType with timestamps
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO entity_types (id, name, category, description, parent_id, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                entity.id,
                entity.name,
                entity.category,
                entity.description,
                entity.parent_id,
                json.dumps(entity.metadata) if entity.metadata else None,
            )
            await conn.execute("UPDATE entity_types SET updated_at = CURRENT_TIMESTAMP WHERE id = $1", entity.id)
            return await self.get_entity_type_by_id(entity.id)

    async def get_entity_type_by_id(self, entity_id: str) -> Optional[EntityType]:
        """Get entity type by ID
        
        Args:
            entity_id: Entity type ID
            
        Returns:
            EntityType if found, None otherwise
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM entity_types WHERE id = $1",
                entity_id,
            )
            if row is None:
                return None
            return EntityType(
                id=row["id"],
                name=row["name"],
                category=row["category"],
                description=row["description"],
                parent_id=row["parent_id"],
                metadata=row["metadata"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def list_entity_types(
        self,
        category: Optional[str] = None,
        parent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EntityType]:
        """List entity types with optional filters
        
        Args:
            category: Filter by category
            parent_id: Filter by parent ID (None for root entities)
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of EntityType objects
        """
        async with self.db_pool.acquire() as conn:
            query = "SELECT * FROM entity_types WHERE 1=1"
            params = []
            param_idx = 1

            if category is not None:
                query += f" AND category = ${param_idx}"
                params.append(category)
                param_idx += 1

            if parent_id is not None:
                query += f" AND parent_id = ${param_idx}"
                params.append(parent_id)
                param_idx += 1
            elif parent_id is not None and parent_id == "null":
                query += " AND parent_id IS NULL"

            query += f" ORDER BY id LIMIT ${param_idx} OFFSET ${param_idx + 1}"
            params.extend([limit, offset])

            rows = await conn.fetch(query, *params)
            return [
                EntityType(
                    id=row["id"],
                    name=row["name"],
                    category=row["category"],
                    description=row["description"],
                    parent_id=row["parent_id"],
                    metadata=row["metadata"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    async def update_entity_type(self, entity: EntityType) -> EntityType:
        """Update an existing entity type
        
        Args:
            entity: EntityType with updated values
            
        Returns:
            Updated EntityType
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE entity_types 
                SET name = $2, category = $3, description = $4, parent_id = $5, metadata = $6, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                entity.id,
                entity.name,
                entity.category,
                entity.description,
                entity.parent_id,
                json.dumps(entity.metadata) if entity.metadata else None,
            )
            return await self.get_entity_type_by_id(entity.id)

    async def delete_entity_type(self, entity_id: str) -> bool:
        """Delete an entity type (cascades to resources and observation points)
        
        Args:
            entity_id: Entity type ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM entity_types WHERE id = $1",
                entity_id,
            )
            return result != "DELETE 0"

    async def bulk_create_entity_types(self, entities: list[EntityType]) -> list[EntityType]:
        """Bulk create entity types in a single transaction
        
        Args:
            entities: List of EntityType objects to create
            
        Returns:
            List of created EntityType objects
        """
        async with self.db_pool.acquire() as conn:
            for entity in entities:
                await conn.execute(
                    """
                    INSERT INTO entity_types (id, name, category, description, parent_id, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        category = EXCLUDED.category,
                        description = EXCLUDED.description,
                        parent_id = EXCLUDED.parent_id,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    entity.id,
                    entity.name,
                    entity.category,
                    entity.description,
                    entity.parent_id,
                    json.dumps(entity.metadata) if entity.metadata else None,
                )
            await conn.commit()
        return entities

    # =========================================================================
    # Resource Type Operations
    # =========================================================================

    async def create_resource_type(self, resource: ResourceType) -> ResourceType:
        """Create a new resource type
        
        Args:
            resource: ResourceType to create
            
        Returns:
            Created ResourceType with timestamps
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO resource_types (id, name, entity_type_id, category, description, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                resource.id,
                resource.name,
                resource.entity_type_id,
                resource.category,
                resource.description,
                json.dumps(resource.metadata) if resource.metadata else None,
            )
            await conn.execute("UPDATE resource_types SET updated_at = CURRENT_TIMESTAMP WHERE id = $1", resource.id)
            return await self.get_resource_type_by_id(resource.id)

    async def get_resource_type_by_id(self, resource_id: str) -> Optional[ResourceType]:
        """Get resource type by ID
        
        Args:
            resource_id: Resource type ID
            
        Returns:
            ResourceType if found, None otherwise
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM resource_types WHERE id = $1",
                resource_id,
            )
            if row is None:
                return None
            return ResourceType(
                id=row["id"],
                name=row["name"],
                entity_type_id=row["entity_type_id"],
                category=row["category"],
                description=row["description"],
                metadata=row["metadata"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def list_resource_types_by_entity(
        self,
        entity_type_id: str,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ResourceType]:
        """List resource types for a specific entity
        
        Args:
            entity_type_id: Entity type ID to filter by
            category: Optional category filter
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of ResourceType objects
        """
        async with self.db_pool.acquire() as conn:
            query = "SELECT * FROM resource_types WHERE entity_type_id = $1"
            params = [entity_type_id]
            param_idx = 2

            if category is not None:
                query += f" AND category = ${param_idx}"
                params.append(category)
                param_idx += 1

            query += f" ORDER BY id LIMIT ${param_idx} OFFSET ${param_idx + 1}"
            params.extend([limit, offset])

            rows = await conn.fetch(query, *params)
            return [
                ResourceType(
                    id=row["id"],
                    name=row["name"],
                    entity_type_id=row["entity_type_id"],
                    category=row["category"],
                    description=row["description"],
                    metadata=row["metadata"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    async def update_resource_type(self, resource: ResourceType) -> ResourceType:
        """Update an existing resource type
        
        Args:
            resource: ResourceType with updated values
            
        Returns:
            Updated ResourceType
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE resource_types 
                SET name = $2, entity_type_id = $3, category = $4, description = $5, metadata = $6, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                resource.id,
                resource.name,
                resource.entity_type_id,
                resource.category,
                resource.description,
                json.dumps(resource.metadata) if resource.metadata else None,
            )
            return await self.get_resource_type_by_id(resource.id)

    async def delete_resource_type(self, resource_id: str) -> bool:
        """Delete a resource type (cascades to observation points)
        
        Args:
            resource_id: Resource type ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM resource_types WHERE id = $1",
                resource_id,
            )
            return result != "DELETE 0"

    async def bulk_create_resource_types(self, resources: list[ResourceType]) -> list[ResourceType]:
        """Bulk create resource types in a single transaction
        
        Args:
            resources: List of ResourceType objects to create
            
        Returns:
            List of created ResourceType objects
        """
        async with self.db_pool.acquire() as conn:
            for resource in resources:
                await conn.execute(
                    """
                    INSERT INTO resource_types (id, name, entity_type_id, category, description, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        entity_type_id = EXCLUDED.entity_type_id,
                        category = EXCLUDED.category,
                        description = EXCLUDED.description,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    resource.id,
                    resource.name,
                    resource.entity_type_id,
                    resource.category,
                    resource.description,
                    json.dumps(resource.metadata) if resource.metadata else None,
                )
            await conn.commit()
        return resources

    # =========================================================================
    # Observation Point Type Operations
    # =========================================================================

    async def create_observation_point_type(self, obs_point: ObservationPointType) -> ObservationPointType:
        """Create a new observation point type
        
        Args:
            obs_point: ObservationPointType to create
            
        Returns:
            Created ObservationPointType with timestamps
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                obs_point.id,
                obs_point.name,
                obs_point.resource_type_id,
                obs_point.category,
                obs_point.unit,
                obs_point.description,
                json.dumps(obs_point.metadata) if obs_point.metadata else None,
            )
            await conn.execute(
                "UPDATE observation_point_types SET updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                obs_point.id,
            )
            return await self.get_observation_point_type_by_id(obs_point.id)

    async def get_observation_point_type_by_id(self, obs_point_id: str) -> Optional[ObservationPointType]:
        """Get observation point type by ID
        
        Args:
            obs_point_id: Observation point type ID
            
        Returns:
            ObservationPointType if found, None otherwise
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM observation_point_types WHERE id = $1",
                obs_point_id,
            )
            if row is None:
                return None
            return ObservationPointType(
                id=row["id"],
                name=row["name"],
                resource_type_id=row["resource_type_id"],
                category=row["category"],
                unit=row["unit"],
                description=row["description"],
                metadata=row["metadata"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def list_observation_points_by_resource(
        self,
        resource_type_id: str,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ObservationPointType]:
        """List observation point types for a specific resource
        
        Args:
            resource_type_id: Resource type ID to filter by
            category: Optional category filter
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of ObservationPointType objects
        """
        async with self.db_pool.acquire() as conn:
            query = "SELECT * FROM observation_point_types WHERE resource_type_id = $1"
            params = [resource_type_id]
            param_idx = 2

            if category is not None:
                query += f" AND category = ${param_idx}"
                params.append(category)
                param_idx += 1

            query += f" ORDER BY id LIMIT ${param_idx} OFFSET ${param_idx + 1}"
            params.extend([limit, offset])

            rows = await conn.fetch(query, *params)
            return [
                ObservationPointType(
                    id=row["id"],
                    name=row["name"],
                    resource_type_id=row["resource_type_id"],
                    category=row["category"],
                    unit=row["unit"],
                    description=row["description"],
                    metadata=row["metadata"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    async def update_observation_point_type(self, obs_point: ObservationPointType) -> ObservationPointType:
        """Update an existing observation point type
        
        Args:
            obs_point: ObservationPointType with updated values
            
        Returns:
            Updated ObservationPointType
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE observation_point_types 
                SET name = $2, resource_type_id = $3, category = $4, unit = $5, description = $6, metadata = $7, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                obs_point.id,
                obs_point.name,
                obs_point.resource_type_id,
                obs_point.category,
                obs_point.unit,
                obs_point.description,
                json.dumps(obs_point.metadata) if obs_point.metadata else None,
            )
            return await self.get_observation_point_type_by_id(obs_point.id)

    async def delete_observation_point_type(self, obs_point_id: str) -> bool:
        """Delete an observation point type
        
        Args:
            obs_point_id: Observation point type ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM observation_point_types WHERE id = $1",
                obs_point_id,
            )
            return result != "DELETE 0"

    async def bulk_create_observation_point_types(
        self, obs_points: list[ObservationPointType]
    ) -> list[ObservationPointType]:
        """Bulk create observation point types in a single transaction
        
        Args:
            obs_points: List of ObservationPointType objects to create
            
        Returns:
            List of created ObservationPointType objects
        """
        async with self.db_pool.acquire() as conn:
            for obs_point in obs_points:
                await conn.execute(
                    """
                    INSERT INTO observation_point_types (id, name, resource_type_id, category, unit, description, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        resource_type_id = EXCLUDED.resource_type_id,
                        category = EXCLUDED.category,
                        unit = EXCLUDED.unit,
                        description = EXCLUDED.description,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    obs_point.id,
                    obs_point.name,
                    obs_point.resource_type_id,
                    obs_point.category,
                    obs_point.unit,
                    obs_point.description,
                    json.dumps(obs_point.metadata) if obs_point.metadata else None,
                )
            await conn.commit()
        return obs_points

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def get_entity_hierarchy(self, root_id: Optional[str] = None) -> dict:
        """Get entity hierarchy as nested dictionary
        
        Args:
            root_id: Optional root entity ID to start from
            
        Returns:
            Nested dictionary representing entity hierarchy
        """
        async with self.db_pool.acquire() as conn:
            query = "SELECT * FROM entity_types ORDER BY id"
            if root_id:
                query = "SELECT * FROM entity_types WHERE id = $1 OR parent_id = $1 ORDER BY id"
                rows = await conn.fetch(query, root_id)
            else:
                rows = await conn.fetch(query)

            # Build hierarchy
            entities = {
                row["id"]: {
                    **dict(row),
                    "children": [],
                }
                for row in rows
            }

            roots = []
            for entity_id, entity in entities.items():
                if entity["parent_id"] and entity["parent_id"] in entities:
                    entities[entity["parent_id"]]["children"].append(entity)
                elif entity["parent_id"] is None:
                    roots.append(entity)

            return {"roots": roots, "total": len(rows)}

    async def get_resource_tree(self, entity_id: str) -> dict:
        """Get full resource tree for an entity
        
        Args:
            entity_id: Entity type ID
            
        Returns:
            Dictionary with entity, resources, and observation points
        """
        entity = await self.get_entity_type_by_id(entity_id)
        if not entity:
            return {}

        resources = await self.list_resource_types_by_entity(entity_id)
        resource_list = []

        for resource in resources:
            obs_points = await self.list_observation_points_by_resource(resource.id)
            resource_list.append(
                {
                    "resource": resource,
                    "observation_points": obs_points,
                }
            )

        return {"entity": entity, "resources": resource_list}

    async def validate_category(
        self,
        entity_type: str,
        category: str,
    ) -> bool:
        """Validate if a category is valid for the given entity type
        
        Args:
            entity_type: Type of entity ('entity', 'resource', 'observation')
            category: Category to validate
            
        Returns:
            True if valid, False otherwise
        """
        if entity_type == "entity":
            return category in self.VALID_ENTITY_CATEGORIES
        elif entity_type == "resource":
            return category in self.VALID_RESOURCE_CATEGORIES
        elif entity_type == "observation":
            return category in self.VALID_OBSERVATION_CATEGORIES
        return False
