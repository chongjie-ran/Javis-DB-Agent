"""Resource Dependency Repository - Data access layer for resource dependencies"""
import json
import uuid
from dataclasses import dataclass, field
from typing import Optional, Any, List, Dict
from datetime import datetime


@dataclass
class ResourceDependency:
    """Resource dependency entity"""
    id: str
    source_resource_type: str
    target_resource_type: str
    dependency_type: str  # 'depends_on', 'used_by', 'calls'
    weight: float = 1.0
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        elif isinstance(self.metadata, str):
            self.metadata = json.loads(self.metadata)


class DependencyRepository:
    """Repository for resource dependency CRUD operations"""

    VALID_DEPENDENCY_TYPES = {"depends_on", "used_by", "calls"}

    def __init__(self, db_conn: Any):
        """Initialize repository with database connection
        
        Args:
            db_conn: Async database connection
        """
        self.db = db_conn

    def _generate_id(self) -> str:
        """Generate unique ID"""
        return f"dep-{uuid.uuid4().hex[:12]}"

    async def create(self, data: dict) -> dict:
        """Create a new dependency
        
        Args:
            data: Dependency data dict with keys:
                - source_resource_type: Source resource type
                - target_resource_type: Target resource type
                - dependency_type: Type ('depends_on', 'used_by', 'calls')
                - weight: Propagation weight (0.0-1.0)
                - metadata: Optional metadata dict
        
        Returns:
            Created dependency dict
        """
        dep_id = data.get("id") or self._generate_id()
        source = data["source_resource_type"]
        target = data["target_resource_type"]
        dep_type = data["dependency_type"]
        
        if dep_type not in self.VALID_DEPENDENCY_TYPES:
            raise ValueError(f"Invalid dependency_type: {dep_type}")
        
        weight = float(data.get("weight", 1.0))
        metadata = json.dumps(data.get("metadata", {}), ensure_ascii=False)
        
        sql = """
            INSERT INTO resource_dependencies 
            (id, source_resource_type, target_resource_type, dependency_type, weight, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        
        await self.db.execute(
            sql, 
            (dep_id, source, target, dep_type, weight, metadata)
        )
        await self.db.commit()
        
        return {
            "id": dep_id,
            "source_resource_type": source,
            "target_resource_type": target,
            "dependency_type": dep_type,
            "weight": weight,
            "metadata": data.get("metadata", {})
        }

    async def get_by_id(self, dep_id: str) -> Optional[dict]:
        """Get dependency by ID
        
        Args:
            dep_id: Dependency ID
        
        Returns:
            Dependency dict or None
        """
        sql = "SELECT * FROM resource_dependencies WHERE id = ?"
        cursor = await self.db.execute(sql, (dep_id,))
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_dict(row)

    async def get_by_types(
        self, 
        source_type: str, 
        target_type: str, 
        dependency_type: str
    ) -> Optional[dict]:
        """Get dependency by source and target types
        
        Args:
            source_type: Source resource type
            target_type: Target resource type
            dependency_type: Dependency type
        
        Returns:
            Dependency dict or None
        """
        sql = """
            SELECT * FROM resource_dependencies 
            WHERE source_resource_type = ? AND target_resource_type = ? AND dependency_type = ?
        """
        cursor = await self.db.execute(sql, (source_type, target_type, dependency_type))
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_dict(row)

    async def list_all(self) -> List[dict]:
        """List all dependencies
        
        Returns:
            List of dependency dicts
        """
        sql = "SELECT * FROM resource_dependencies ORDER BY created_at DESC"
        cursor = await self.db.execute(sql)
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def list_by_source(self, source_type: str) -> List[dict]:
        """List dependencies by source resource type
        
        Args:
            source_type: Source resource type
        
        Returns:
            List of dependency dicts
        """
        sql = """
            SELECT * FROM resource_dependencies 
            WHERE source_resource_type = ? 
            ORDER BY weight DESC
        """
        cursor = await self.db.execute(sql, (source_type,))
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def list_by_target(self, target_type: str) -> List[dict]:
        """List dependencies by target resource type
        
        Args:
            target_type: Target resource type
        
        Returns:
            List of dependency dicts
        """
        sql = """
            SELECT * FROM resource_dependencies 
            WHERE target_resource_type = ? 
            ORDER BY weight DESC
        """
        cursor = await self.db.execute(sql, (target_type,))
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def list_by_type(self, dependency_type: str) -> List[dict]:
        """List dependencies by type
        
        Args:
            dependency_type: Dependency type
        
        Returns:
            List of dependency dicts
        """
        if dependency_type not in self.VALID_DEPENDENCY_TYPES:
            raise ValueError(f"Invalid dependency_type: {dependency_type}")
        
        sql = """
            SELECT * FROM resource_dependencies 
            WHERE dependency_type = ? 
            ORDER BY weight DESC
        """
        cursor = await self.db.execute(sql, (dependency_type,))
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def update(self, dep_id: str, data: dict) -> Optional[dict]:
        """Update a dependency
        
        Args:
            dep_id: Dependency ID
            data: Update data dict
        
        Returns:
            Updated dependency dict or None
        """
        existing = await self.get_by_id(dep_id)
        if existing is None:
            return None
        
        updates = []
        params = []
        
        if "source_resource_type" in data:
            updates.append("source_resource_type = ?")
            params.append(data["source_resource_type"])
        
        if "target_resource_type" in data:
            updates.append("target_resource_type = ?")
            params.append(data["target_resource_type"])
        
        if "dependency_type" in data:
            if data["dependency_type"] not in self.VALID_DEPENDENCY_TYPES:
                raise ValueError(f"Invalid dependency_type: {data['dependency_type']}")
            updates.append("dependency_type = ?")
            params.append(data["dependency_type"])
        
        if "weight" in data:
            weight = float(data["weight"])
            if not (0.0 <= weight <= 1.0):
                raise ValueError("weight must be between 0.0 and 1.0")
            updates.append("weight = ?")
            params.append(weight)
        
        if "metadata" in data:
            updates.append("metadata = ?")
            params.append(json.dumps(data["metadata"], ensure_ascii=False))
        
        if not updates:
            return existing
        
        params.append(dep_id)
        sql = f"UPDATE resource_dependencies SET {', '.join(updates)} WHERE id = ?"
        
        await self.db.execute(sql, tuple(params))
        await self.db.commit()
        
        return await self.get_by_id(dep_id)

    async def delete(self, dep_id: str) -> bool:
        """Delete a dependency
        
        Args:
            dep_id: Dependency ID
        
        Returns:
            True if deleted, False if not found
        """
        sql = "DELETE FROM resource_dependencies WHERE id = ?"
        cursor = await self.db.execute(sql, (dep_id,))
        await self.db.commit()
        
        # Check if any row was deleted
        cursor2 = await self.db.execute("SELECT changes()")
        row = await cursor2.fetchone()
        return row[0] > 0 if row else False

    async def upsert(self, data: dict) -> dict:
        """Insert or update a dependency (upsert)
        
        If the dependency with same source/target/type exists, update it.
        Otherwise, insert a new one.
        
        Args:
            data: Dependency data dict
        
        Returns:
            Upserted dependency dict
        """
        source = data["source_resource_type"]
        target = data["target_resource_type"]
        dep_type = data["dependency_type"]
        
        existing = await self.get_by_types(source, target, dep_type)
        
        if existing:
            return await self.update(existing["id"], data)
        else:
            return await self.create(data)

    async def load_benchmark_dependencies(self) -> int:
        """Load benchmark dependencies from predefined rules
        
        This loads standard resource dependency rules that are typical
        in database system environments.
        
        Returns:
            Number of dependencies loaded
        """
        # Benchmark dependencies are pre-loaded via migration V003
        # This method is for programmatic loading if needed
        cursor = await self.db.execute("SELECT COUNT(*) FROM resource_dependencies")
        row = await cursor.fetchone()
        return row[0] if row else 0

    def _row_to_dict(self, row: Any) -> dict:
        """Convert database row to dict
        
        Args:
            row: Database row
        
        Returns:
            Dictionary representation
        """
        if row is None:
            return None
        
        metadata = row["metadata"] if "metadata" in row.keys() else "{}"
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        return {
            "id": row["id"],
            "source_resource_type": row["source_resource_type"],
            "target_resource_type": row["target_resource_type"],
            "dependency_type": row["dependency_type"],
            "weight": row["weight"],
            "metadata": metadata,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }
