"""Observation Point Repository - Data access layer for observation point metadata"""
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Any, List
from datetime import datetime


@dataclass
class ObservationPoint:
    """Observation point metadata - defines how to collect, represent, and detect anomalies for a metric"""
    id: str
    resource_type: str              # e.g., OS.CPU, DB.Connection
    metric_name: str                 # e.g., usage_percent, active_count
    collection_method: str           # How to collect this metric
    representation: str              # How to represent this metric (unit, range)
    anomaly_pattern: Optional[str] = None       # Description of anomaly pattern
    anomaly_condition: Optional[str] = None      # Anomaly condition expression
    unit: Optional[str] = None      # Unit of measurement
    severity: Optional[str] = None  # Default severity: critical, warning, info
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if isinstance(self.metadata, str):
            self.metadata = json.loads(self.metadata)

    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "id": self.id,
            "resource_type": self.resource_type,
            "metric_name": self.metric_name,
            "collection_method": self.collection_method,
            "representation": self.representation,
            "anomaly_pattern": self.anomaly_pattern,
            "anomaly_condition": self.anomaly_condition,
            "unit": self.unit,
            "severity": self.severity,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ObservationPointRepository:
    """Repository for observation point CRUD operations with async database access"""

    def __init__(self, db_pool: Any):
        """Initialize repository with database connection pool
        
        Args:
            db_pool: Async database connection pool (supports acquire/release)
        """
        self.db_pool = db_pool

    def _row_to_observation_point(self, row: dict) -> ObservationPoint:
        """Convert database row to ObservationPoint"""
        metadata = row.get("metadata", "{}")
        if isinstance(metadata, str):
            metadata = json.loads(metadata) if metadata else {}
        
        return ObservationPoint(
            id=row["id"],
            resource_type=row["resource_type"],
            metric_name=row["metric_name"],
            collection_method=row["collection_method"],
            representation=row["representation"],
            anomaly_pattern=row.get("anomaly_pattern"),
            anomaly_condition=row.get("anomaly_condition"),
            unit=row.get("unit"),
            severity=row.get("severity"),
            metadata=metadata or {},
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create_observation_point(self, op: ObservationPoint) -> ObservationPoint:
        """Create a new observation point
        
        Args:
            op: ObservationPoint to create
            
        Returns:
            Created ObservationPoint
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO observation_points 
                (id, resource_type, metric_name, collection_method, representation,
                 anomaly_pattern, anomaly_condition, unit, severity, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                op.id,
                op.resource_type,
                op.metric_name,
                op.collection_method,
                op.representation,
                op.anomaly_pattern,
                op.anomaly_condition,
                op.unit,
                op.severity,
                json.dumps(op.metadata) if op.metadata else "{}",
            )
            await conn.commit()
            
        return op

    async def get_observation_point_by_id(self, op_id: str) -> Optional[ObservationPoint]:
        """Get observation point by ID
        
        Args:
            op_id: Observation point ID
            
        Returns:
            ObservationPoint if found, None otherwise
        """
        async with self.db_pool.acquire() as conn:
            async with conn.execute(
                "SELECT * FROM observation_points WHERE id = $1",
                (op_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_observation_point(dict(row))
                return None

    async def get_observation_point_by_resource_metric(
        self, 
        resource_type: str, 
        metric_name: str
    ) -> Optional[ObservationPoint]:
        """Get observation point by resource type and metric name
        
        Args:
            resource_type: Resource type (e.g., OS.CPU)
            metric_name: Metric name (e.g., usage_percent)
            
        Returns:
            ObservationPoint if found, None otherwise
        """
        async with self.db_pool.acquire() as conn:
            async with conn.execute(
                """
                SELECT * FROM observation_points 
                WHERE resource_type = $1 AND metric_name = $2
                """,
                (resource_type, metric_name)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_observation_point(dict(row))
                return None

    async def list_observation_points(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ObservationPoint]:
        """List all observation points with pagination
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of ObservationPoint objects
        """
        async with self.db_pool.acquire() as conn:
            async with conn.execute(
                """
                SELECT * FROM observation_points 
                ORDER BY resource_type, metric_name
                LIMIT $1 OFFSET $2
                """,
                (limit, offset)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_observation_point(dict(row)) for row in rows]

    async def list_observation_points_by_resource_type(
        self,
        resource_type: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ObservationPoint]:
        """List observation points for a specific resource type
        
        Args:
            resource_type: Resource type (e.g., OS.CPU)
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of ObservationPoint objects
        """
        async with self.db_pool.acquire() as conn:
            async with conn.execute(
                """
                SELECT * FROM observation_points 
                WHERE resource_type = $1
                ORDER BY metric_name
                LIMIT $2 OFFSET $3
                """,
                (resource_type, limit, offset)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_observation_point(dict(row)) for row in rows]

    async def update_observation_point(self, op: ObservationPoint) -> ObservationPoint:
        """Update an observation point
        
        Args:
            op: ObservationPoint with updated values
            
        Returns:
            Updated ObservationPoint
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE observation_points SET
                    resource_type = $2,
                    metric_name = $3,
                    collection_method = $4,
                    representation = $5,
                    anomaly_pattern = $6,
                    anomaly_condition = $7,
                    unit = $8,
                    severity = $9,
                    metadata = $10
                WHERE id = $1
                """,
                op.id,
                op.resource_type,
                op.metric_name,
                op.collection_method,
                op.representation,
                op.anomaly_pattern,
                op.anomaly_condition,
                op.unit,
                op.severity,
                json.dumps(op.metadata) if op.metadata else "{}",
            )
            await conn.commit()
            
        return op

    async def delete_observation_point(self, op_id: str) -> bool:
        """Delete an observation point
        
        Args:
            op_id: Observation point ID to delete
            
        Returns:
            True if deleted
        """
        async with self.db_pool.acquire() as conn:
            cursor = await conn.execute(
                "DELETE FROM observation_points WHERE id = $1",
                (op_id,)
            )
            await conn.commit()
            # Check if any row was deleted
            async with conn.execute(
                "SELECT COUNT(*) FROM observation_points WHERE id = $1",
                (op_id,)
            ) as count_cursor:
                row = await count_cursor.fetchone()
                return row[0] == 0 if row else True

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    async def bulk_create_observation_points(self, ops: List[ObservationPoint]) -> int:
        """Bulk create observation points
        
        Args:
            ops: List of ObservationPoint objects to create
            
        Returns:
            Number of observation points created
        """
        async with self.db_pool.acquire() as conn:
            for op in ops:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO observation_points 
                    (id, resource_type, metric_name, collection_method, representation,
                     anomaly_pattern, anomaly_condition, unit, severity, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    op.id,
                    op.resource_type,
                    op.metric_name,
                    op.collection_method,
                    op.representation,
                    op.anomaly_pattern,
                    op.anomaly_condition,
                    op.unit,
                    op.severity,
                    json.dumps(op.metadata) if op.metadata else "{}",
                )
            await conn.commit()
            
        return len(ops)

    # =========================================================================
    # Query Operations
    # =========================================================================

    async def search_observation_points(
        self,
        resource_type: Optional[str] = None,
        metric_name: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> List[ObservationPoint]:
        """Search observation points with filters
        
        Args:
            resource_type: Filter by resource type (partial match)
            metric_name: Filter by metric name (partial match)
            severity: Filter by severity
            limit: Maximum number of results
            
        Returns:
            List of matching ObservationPoint objects
        """
        conditions = []
        params = []
        param_idx = 1

        if resource_type:
            conditions.append(f"resource_type LIKE ${param_idx}")
            params.append(f"%{resource_type}%")
            param_idx += 1

        if metric_name:
            conditions.append(f"metric_name LIKE ${param_idx}")
            params.append(f"%{metric_name}%")
            param_idx += 1

        if severity:
            conditions.append(f"severity = ${param_idx}")
            params.append(severity)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        async with self.db_pool.acquire() as conn:
            async with conn.execute(
                f"""
                SELECT * FROM observation_points 
                WHERE {where_clause}
                ORDER BY resource_type, metric_name
                LIMIT ${param_idx}
                """,
                (*params, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_observation_point(dict(row)) for row in rows]
