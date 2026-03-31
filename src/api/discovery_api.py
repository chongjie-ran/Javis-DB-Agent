"""
发现服务REST API

提供本地数据库发现的API接口：
- GET  /api/v1/discovery/instances      - 列出已纳管实例
- POST /api/v1/discovery/scan           - 触发本地扫描
- GET  /api/v1/discovery/instances/{id} - 获取实例详情
- DELETE /api/v1/discovery/instances/{id} - 移除实例
- GET  /api/v1/discovery/stats         - 获取纳管统计
- GET  /api/v1/discovery/schemas       - 获取schema知识
- GET  /api/v1/discovery/search         - 语义搜索知识库
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.discovery.service import DiscoveryService
from src.discovery.knowledge_base import LocalKnowledgeBase, SchemaKnowledge

router = APIRouter(prefix="/api/v1/discovery")


# ============ Request/Response Models ============

class InstanceResponse(BaseModel):
    id: str
    db_type: str
    host: str
    port: int
    version: str
    status: str
    discovered_at: str
    onboarded_at: Optional[str] = None


class ScanResponse(BaseModel):
    session_id: str
    discovered_count: int
    identified_count: int
    registered_count: int
    new_count: int
    errors: List[str]


class StatsResponse(BaseModel):
    registry: Dict[str, Any]
    knowledge_base: Optional[Dict[str, int]] = None


class SchemaResponse(BaseModel):
    instance_id: str
    db_name: str
    table_count: int
    version: str
    captured_at: str
    tables: List[Dict]


class SearchResponse(BaseModel):
    query: str
    collection: str
    results: List[Dict]


# ============ 全局服务实例 ============

_discovery_service: Optional[DiscoveryService] = None
_knowledge_base: Optional[LocalKnowledgeBase] = None


def get_discovery_service() -> DiscoveryService:
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = DiscoveryService()
    return _discovery_service


def get_knowledge_base() -> LocalKnowledgeBase:
    global _knowledge_base
    if _knowledge_base is None:
        try:
            _knowledge_base = LocalKnowledgeBase()
        except RuntimeError:
            # ChromaDB未安装
            raise HTTPException(status_code=503, detail="Knowledge base not available")
    return _knowledge_base


# ============ API Endpoints ============

@router.get("/instances", response_model=List[InstanceResponse])
async def list_instances(status: Optional[str] = None):
    """列出已纳管实例"""
    svc = get_discovery_service()
    instances = svc.get_all_instances()
    
    if status:
        instances = [i for i in instances if i.status == status]
    
    return [
        InstanceResponse(
            id=i.id,
            db_type=i.db_type,
            host=i.host,
            port=i.port,
            version=i.version,
            status=i.status,
            discovered_at=i.discovered_at,
            onboarded_at=i.onboarded_at,
        )
        for i in instances
    ]


@router.post("/scan", response_model=ScanResponse)
async def trigger_scan(
    auto_onboard: bool = True,
    capture_knowledge: bool = True,
):
    """触发本地数据库扫描"""
    svc = get_discovery_service()
    
    # 如果需要捕获知识，初始化知识库
    if capture_knowledge:
        try:
            kb = get_knowledge_base()
            svc.kb = kb
        except HTTPException:
            capture_knowledge = False
    
    result = await svc.discover_and_onboard(
        auto_onboard=auto_onboard,
        capture_knowledge=capture_knowledge,
    )
    
    return ScanResponse(
        session_id=result.session_id,
        discovered_count=len(result.discovered),
        identified_count=len(result.identified),
        registered_count=len(result.registered),
        new_count=result.new_count,
        errors=result.errors,
    )


@router.get("/instances/{instance_id}", response_model=InstanceResponse)
async def get_instance(instance_id: str):
    """获取实例详情"""
    svc = get_discovery_service()
    instance = svc.registry.get_by_id(instance_id)
    
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    return InstanceResponse(
        id=instance.id,
        db_type=instance.db_type,
        host=instance.host,
        port=instance.port,
        version=instance.version,
        status=instance.status,
        discovered_at=instance.discovered_at,
        onboarded_at=instance.onboarded_at,
    )


@router.delete("/instances/{instance_id}")
async def remove_instance(instance_id: str):
    """移除实例"""
    svc = get_discovery_service()
    success = svc.remove_instance(instance_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    return {"status": "removed", "instance_id": instance_id}


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """获取纳管统计"""
    svc = get_discovery_service()
    stats = svc.get_stats()
    return StatsResponse(**stats)


@router.get("/schemas", response_model=List[SchemaResponse])
async def get_schemas(instance_id: Optional[str] = None):
    """获取schema知识"""
    kb = get_knowledge_base()
    
    if instance_id:
        # 获取特定实例的schema
        results = kb.search_schemas(
            query="",
            instance_id=instance_id,
            top_k=10,
        )
        if not results:
            return []
        
        # 从metadata构建响应
        schemas = []
        for r in results:
            meta = r.get("metadata", {})
            schemas.append(SchemaResponse(
                instance_id=meta.get("instance_id", ""),
                db_name=meta.get("db_name", ""),
                table_count=meta.get("table_count", 0),
                version=meta.get("version", ""),
                captured_at=meta.get("captured_at", ""),
                tables=[],  # content中已有完整信息
            ))
        return schemas
    else:
        # 获取所有schema（取最新）
        results = kb.search_schemas(query="database schema", top_k=100)
        schemas = []
        seen = set()
        for r in results:
            meta = r.get("metadata", {})
            key = meta.get("instance_id", "")
            if key and key not in seen:
                seen.add(key)
                schemas.append(SchemaResponse(
                    instance_id=meta.get("instance_id", ""),
                    db_name=meta.get("db_name", ""),
                    table_count=meta.get("table_count", 0),
                    version=meta.get("version", ""),
                    captured_at=meta.get("captured_at", ""),
                    tables=[],
                ))
        return schemas


@router.get("/search", response_model=SearchResponse)
async def search_knowledge(
    q: str,
    collection: str = "schemas",
    db_type: Optional[str] = None,
    top_k: int = 5,
):
    """
    语义搜索知识库
    
    Args:
        q: 搜索查询
        collection: 集合类型 (schemas/configs/cases)
        db_type: 数据库类型过滤 (postgresql/mysql/mariadb)
        top_k: 返回结果数量
    """
    kb = get_knowledge_base()
    
    if collection == "schemas":
        results = kb.search_schemas(query=q, top_k=top_k)
    elif collection == "configs":
        results = kb.search_configs(query=q, db_type=db_type, top_k=top_k)
    elif collection == "cases":
        results = kb.search_cases(query=q, db_type=db_type, top_k=top_k)
    else:
        raise HTTPException(status_code=400, detail="Invalid collection")
    
    return SearchResponse(
        query=q,
        collection=collection,
        results=[
            {
                "id": r.get("id", ""),
                "content": r.get("content", "")[:500],  # 截断
                "distance": r.get("distance", 0),
                "metadata": r.get("metadata", {}),
            }
            for r in results
        ],
    )


@router.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "discovery_service": "available",
        "knowledge_base": "available" if _knowledge_base else "disabled",
    }
