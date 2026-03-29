"""Dependency Propagation API Routes - Round 19
REST endpoints for resource dependency management and alert propagation
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.knowledge.db.repositories.dependency_repo import DependencyRepository
from src.knowledge.services.dependency_propagator import DependencyPropagator
from src.knowledge.db.database import get_knowledge_db


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])

# Global instances
_dependency_repo: Optional[DependencyRepository] = None
_dependency_propagator: Optional[DependencyPropagator] = None


def get_dependency_repository() -> DependencyRepository:
    """Get or create dependency repository"""
    global _dependency_repo
    if _dependency_repo is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dependency repository not initialized"
        )
    return _dependency_repo


def get_propagator() -> DependencyPropagator:
    """Get or create dependency propagator"""
    global _dependency_propagator
    if _dependency_propagator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dependency propagator not initialized"
        )
    return _dependency_propagator


async def init_dependency_routes() -> None:
    """Initialize dependency routes with database connection"""
    global _dependency_repo, _dependency_propagator
    conn = await get_knowledge_db()
    conn.row_factory = None  # Use dict-like access
    _dependency_repo = DependencyRepository(conn)
    _dependency_propagator = DependencyPropagator(_dependency_repo)
    _dependency_propagator.load_dependencies()  # Pre-load


# ============================================================
# Request/Response Models
# ============================================================


class DependencyCreate(BaseModel):
    """Request model for creating a dependency"""
    source_resource_type: str = Field(..., description="Source resource type (e.g., OS.CPU)")
    target_resource_type: str = Field(..., description="Target resource type (e.g., DB.Connection)")
    dependency_type: str = Field(..., description="Dependency type: 'depends_on', 'used_by', 'calls'")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Propagation weight (0.0-1.0)")
    metadata: Optional[dict] = Field(default_factory=dict, description="Optional metadata")


class DependencyUpdate(BaseModel):
    """Request model for updating a dependency"""
    source_resource_type: Optional[str] = None
    target_resource_type: Optional[str] = None
    dependency_type: Optional[str] = None
    weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    metadata: Optional[dict] = None


class DependencyResponse(BaseModel):
    """Response model for a dependency"""
    id: str
    source_resource_type: str
    target_resource_type: str
    dependency_type: str
    weight: float
    metadata: dict


class PropagatedAlertResponse(BaseModel):
    """Response model for a propagated alert"""
    alert_id: str
    alert_name: str
    alert_type: str
    severity: str
    instance_id: str
    occurred_at: float
    message: str
    root_cause_probability: float
    propagation_depth: int
    propagation_path: List[str]
    role: str


class RootCauseResponse(BaseModel):
    """Response model for root cause analysis"""
    root_cause: Optional[dict]
    analysis: List[dict]
    propagated_alerts: List[dict]
    summary: str


class DependencyGraphResponse(BaseModel):
    """Response model for dependency graph"""
    nodes: List[str]
    edges: List[dict]
    stats: dict


# ============================================================
# API Endpoints
# ============================================================


@router.get("/dependencies", response_model=dict)
async def list_dependencies(
    source_type: Optional[str] = Query(None, description="Filter by source resource type"),
    target_type: Optional[str] = Query(None, description="Filter by target resource type"),
    dependency_type: Optional[str] = Query(None, description="Filter by dependency type"),
):
    """
    获取所有资源依赖关系
    
    GET /api/v1/knowledge/dependencies
    
    Returns:
        List of dependencies
    """
    repo = get_dependency_repository()
    
    try:
        if source_type:
            deps = await repo.list_by_source(source_type)
        elif target_type:
            deps = await repo.list_by_target(target_type)
        elif dependency_type:
            deps = await repo.list_by_type(dependency_type)
        else:
            deps = await repo.list_all()
        
        return {"dependencies": deps, "total": len(deps)}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/dependencies", response_model=DependencyResponse, status_code=status.HTTP_201_CREATED)
async def create_dependency(data: DependencyCreate):
    """
    添加资源依赖关系
    
    POST /api/v1/knowledge/dependencies
    
    Args:
        data: Dependency creation data
    
    Returns:
        Created dependency
    """
    repo = get_dependency_repository()
    
    try:
        dep = await repo.create(data.model_dump())
        return dep
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/dependencies/{dep_id}", response_model=DependencyResponse)
async def get_dependency(dep_id: str):
    """
    获取指定依赖关系
    
    GET /api/v1/knowledge/dependencies/{dep_id}
    """
    repo = get_dependency_repository()
    dep = await repo.get_by_id(dep_id)
    
    if dep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dependency {dep_id} not found"
        )
    
    return dep


@router.put("/dependencies/{dep_id}", response_model=DependencyResponse)
async def update_dependency(dep_id: str, data: DependencyUpdate):
    """
    更新依赖关系
    
    PUT /api/v1/knowledge/dependencies/{dep_id}
    """
    repo = get_dependency_repository()
    
    try:
        dep = await repo.update(dep_id, data.model_dump(exclude_none=True))
        if dep is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dependency {dep_id} not found"
            )
        return dep
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/dependencies/{dep_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dependency(dep_id: str):
    """
    删除依赖关系
    
    DELETE /api/v1/knowledge/dependencies/{dep_id}
    """
    repo = get_dependency_repository()
    deleted = await repo.delete(dep_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dependency {dep_id} not found"
        )


@router.get("/dependency-graph", response_model=DependencyGraphResponse)
async def get_dependency_graph():
    """
    获取资源依赖图谱
    
    GET /api/v1/knowledge/dependency-graph
    
    Returns:
        Dependency graph with nodes and edges
    """
    propagator = get_propagator()
    graph = propagator.get_dependency_graph()
    return graph


@router.post("/dependencies/bulk", response_model=dict)
async def bulk_create_dependencies(dependencies: List[DependencyCreate]):
    """
    批量创建依赖关系
    
    POST /api/v1/knowledge/dependencies/bulk
    """
    repo = get_dependency_repository()
    
    created = []
    errors = []
    
    for i, data in enumerate(dependencies):
        try:
            dep = await repo.create(data.model_dump())
            created.append(dep)
        except ValueError as e:
            errors.append({"index": i, "error": str(e)})
    
    return {
        "created": created,
        "errors": errors,
        "total_created": len(created),
        "total_errors": len(errors)
    }


# ============================================================
# Alert Propagation Endpoints
# ============================================================


@router.get("/propagate/{alert_id}", response_model=dict)
async def propagate_alert(
    alert_id: str,
    alert_type: str = Query(..., description="Alert type (e.g., OS.CPU)"),
    severity: str = Query("warning", description="Alert severity"),
    instance_id: str = Query(..., description="Instance ID"),
    message: str = Query("", description="Alert message"),
    depth: int = Query(3, ge=1, le=5, description="Propagation depth"),
):
    """
    传播告警到依赖资源
    
    GET /api/v1/knowledge/propagate/{alert_id}
    
    将告警沿着资源依赖链向下传播，计算每个传播告警的根因概率。
    
    Args:
        alert_id: Original alert ID
        alert_type: Alert type (resource type)
        severity: Alert severity
        instance_id: Instance ID
        message: Alert message
        depth: Propagation depth (1-5)
    
    Returns:
        Original alert and propagated alerts with root cause probabilities
    """
    import time
    
    propagator = get_propagator()
    
    # Create a mock alert object for propagation
    class MockAlert:
        def __init__(self):
            self.alert_id = alert_id
            self.alert_name = f"{alert_type}告警"
            self.alert_type = alert_type
            self.severity = severity
            self.instance_id = instance_id
            self.occurred_at = time.time()
            self.message = message
    
    alert = MockAlert()
    propagated = propagator.propagate_alert(alert, depth=depth)
    
    # Convert to response format
    propagated_data = [
        {
            "alert_id": p.alert_id,
            "alert_name": p.alert_name,
            "alert_type": p.alert_type,
            "severity": p.severity,
            "instance_id": p.instance_id,
            "occurred_at": p.occurred_at,
            "message": p.message,
            "root_cause_probability": p.root_cause_probability,
            "propagation_depth": p.propagation_depth,
            "propagation_path": p.propagation_path,
            "role": p.role
        }
        for p in propagated
    ]
    
    return {
        "original_alert": {
            "alert_id": alert_id,
            "alert_type": alert_type,
            "severity": severity,
            "instance_id": instance_id,
            "message": message
        },
        "propagated_alerts": propagated_data,
        "total_propagated": len(propagated_data),
        "depth_used": depth
    }


@router.get("/root-cause", response_model=RootCauseResponse)
async def analyze_root_cause(
    alert_ids: str = Query(..., description="Comma-separated alert IDs"),
    alert_types: str = Query(..., description="Comma-separated alert types"),
    severities: str = Query("warning,warning,warning", description="Comma-separated severities"),
    instance_ids: str = Query(..., description="Comma-separated instance IDs"),
    messages: str = Query("", description="Comma-separated messages"),
    depth: int = Query(3, ge=1, le=5, description="Propagation depth"),
):
    """
    根因分析 - 找到告警链的根因
    
    GET /api/v1/knowledge/root-cause
    
    分析多个告警，基于依赖传播和规则推理找到最可能的根因。
    
    Args:
        alert_ids: Comma-separated alert IDs
        alert_types: Comma-separated alert types
        severities: Comma-separated severities
        instance_ids: Comma-separated instance IDs
        messages: Comma-separated messages
        depth: Propagation depth
    
    Returns:
        Root cause analysis result
    """
    import time
    
    # Parse inputs
    ids = alert_ids.split(",")
    types = alert_types.split(",")
    sev_list = severities.split(",")
    inst_list = instance_ids.split(",")
    msg_list = messages.split(",") if messages else [""]
    
    # Ensure same length
    min_len = min(len(ids), len(types), len(sev_list), len(inst_list))
    ids = ids[:min_len]
    types = types[:min_len]
    sev_list = sev_list[:min_len]
    inst_list = inst_list[:min_len]
    msg_list = msg_list[:min_len] if msg_list else [""]
    
    class MockAlert:
        def __init__(self, aid, atype, sev, iid, msg):
            self.alert_id = aid
            self.alert_name = f"{atype}告警"
            self.alert_type = atype
            self.severity = sev
            self.instance_id = iid
            self.occurred_at = time.time()
            self.message = msg
    
    alerts = [
        MockAlert(ids[i], types[i], sev_list[i], inst_list[i], msg_list[i] if i < len(msg_list) else "")
        for i in range(min_len)
    ]
    
    propagator = get_propagator()
    result = propagator.find_root_cause_with_propagation(alerts, depth=depth)
    
    # Format response
    root_cause_data = None
    if result.get("root_cause"):
        rc = result["root_cause"]
        root_cause_data = {
            "alert_id": rc.alert_id,
            "alert_type": rc.alert_type,
            "severity": rc.severity,
            "instance_id": rc.instance_id,
            "message": rc.message,
            "root_cause_probability": getattr(rc, 'root_cause_probability', 1.0)
        }
    
    propagated_data = []
    for p in result.get("propagated_alerts", []):
        propagated_data.append({
            "alert_id": p.alert_id,
            "alert_type": p.alert_type,
            "severity": p.severity,
            "instance_id": p.instance_id,
            "root_cause_probability": p.root_cause_probability,
            "propagation_depth": p.propagation_depth,
            "propagation_path": p.propagation_path,
            "role": p.role
        })
    
    return RootCauseResponse(
        root_cause=root_cause_data,
        analysis=result.get("analysis", []),
        propagated_alerts=propagated_data,
        summary=result.get("summary", "")
    )


@router.get("/upstream/{resource_type}")
async def get_upstream_dependencies(resource_type: str):
    """
    获取资源的上游依赖
    
    GET /api/v1/knowledge/upstream/{resource_type}
    
    上游依赖是指影响该资源的资源类型。
    """
    propagator = get_propagator()
    upstream = propagator.get_upstream_dependencies(resource_type)
    
    return {
        "resource_type": resource_type,
        "upstream_dependencies": upstream,
        "total": len(upstream)
    }


@router.get("/downstream/{resource_type}")
async def get_downstream_dependencies(resource_type: str):
    """
    获取资源的下游依赖
    
    GET /api/v1/knowledge/downstream/{resource_type}
    
    下游依赖是指受该资源影响的资源类型。
    """
    propagator = get_propagator()
    downstream = propagator.get_downstream_dependencies(resource_type)
    
    return {
        "resource_type": resource_type,
        "downstream_dependencies": downstream,
        "total": len(downstream)
    }
