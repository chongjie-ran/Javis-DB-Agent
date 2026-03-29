"""知识库API路由"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from enum import Enum

from src.knowledge.db.database import get_knowledge_db, close_knowledge_db
from src.knowledge.services.knowledge_base_service import KnowledgeBaseService, ContentType


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


# ============ 请求/响应模型 ============

class SeverityEnum(str, Enum):
    """严重程度枚举"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class ContentTypeEnum(str, Enum):
    """内容类型枚举"""
    ALERT_RULE = "alert_rule"
    SOP = "sop"
    CASE = "case"


# Alert Rule 模型
class AlertRuleCreate(BaseModel):
    id: str
    name: str
    condition: str
    severity: SeverityEnum
    entity_type: Optional[str] = None
    resource_type: Optional[str] = None
    observation_point: Optional[str] = None
    recommendation: Optional[str] = None
    enabled: int = 1
    metadata: Optional[dict] = None


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    condition: Optional[str] = None
    severity: Optional[SeverityEnum] = None
    entity_type: Optional[str] = None
    resource_type: Optional[str] = None
    observation_point: Optional[str] = None
    recommendation: Optional[str] = None
    enabled: Optional[int] = None
    metadata: Optional[dict] = None


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    condition: str
    severity: str
    entity_type: Optional[str] = None
    resource_type: Optional[str] = None
    observation_point: Optional[str] = None
    recommendation: Optional[str] = None
    enabled: int
    metadata: dict


# SOP 模型
class SOPCreate(BaseModel):
    id: str
    title: str
    alert_rule_id: Optional[str] = None
    steps: List[dict] = Field(default_factory=list)
    enabled: int = 1
    metadata: Optional[dict] = None


class SOPUpdate(BaseModel):
    title: Optional[str] = None
    alert_rule_id: Optional[str] = None
    steps: Optional[List[dict]] = None
    enabled: Optional[int] = None
    metadata: Optional[dict] = None


class SOPResponse(BaseModel):
    id: str
    title: str
    alert_rule_id: Optional[str] = None
    steps: List[dict]
    enabled: int
    metadata: dict


# Case 模型
class CaseCreate(BaseModel):
    id: str
    title: str
    alert_rule_id: Optional[str] = None
    symptoms: List[str] = Field(default_factory=list)
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    outcome: Optional[str] = None
    metadata: Optional[dict] = None


class CaseUpdate(BaseModel):
    title: Optional[str] = None
    alert_rule_id: Optional[str] = None
    symptoms: Optional[List[str]] = None
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    outcome: Optional[str] = None
    metadata: Optional[dict] = None


class CaseResponse(BaseModel):
    id: str
    title: str
    alert_rule_id: Optional[str] = None
    symptoms: List[str]
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    outcome: Optional[str] = None
    metadata: dict


# Search 模型
class SearchResult(BaseModel):
    content_type: str
    content_id: str
    title: str
    content: str
    score: float
    metadata: dict


# ============ 依赖项 ============

async def get_kb_service():
    """获取知识库服务"""
    conn = await get_knowledge_db()
    service = KnowledgeBaseService(conn)
    try:
        yield service
    finally:
        await close_knowledge_db(conn)


# ============ 告警规则路由 ============

@router.get("/alerts", response_model=dict)
async def list_alerts(
    severity: Optional[SeverityEnum] = None,
    enabled_only: bool = Query(False),
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """列出告警规则"""
    if severity:
        results = await service.list_alert_rules_by_severity(severity.value)
    else:
        results = await service.list_alert_rules(enabled_only=enabled_only)
    
    return {"code": 0, "data": results}


@router.get("/alerts/{alert_id}", response_model=dict)
async def get_alert(
    alert_id: str,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """获取告警规则详情"""
    result = await service.get_alert_rule(alert_id)
    if not result:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    
    return {"code": 0, "data": result}


@router.post("/alerts", response_model=dict)
async def create_alert(
    alert: AlertRuleCreate,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """创建告警规则"""
    data = alert.model_dump()
    if data.get("severity"):
        data["severity"] = data["severity"].value if hasattr(data["severity"], "value") else data["severity"]
    
    try:
        result = await service.create_alert_rule(data)
        return {"code": 0, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/alerts/{alert_id}", response_model=dict)
async def update_alert(
    alert_id: str,
    alert: AlertRuleUpdate,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """更新告警规则"""
    data = alert.model_dump(exclude_unset=True)
    if "severity" in data and data["severity"]:
        data["severity"] = data["severity"].value if hasattr(data["severity"], "value") else data["severity"]
    
    result = await service.update_alert_rule(alert_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    
    return {"code": 0, "data": result}


@router.delete("/alerts/{alert_id}", response_model=dict)
async def delete_alert(
    alert_id: str,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """删除告警规则"""
    success = await service.delete_alert_rule(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    
    return {"code": 0, "message": "删除成功"}


# ============ SOP路由 ============

@router.get("/sops", response_model=dict)
async def list_sops(
    alert_rule_id: Optional[str] = None,
    enabled_only: bool = Query(False),
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """列出SOP"""
    if alert_rule_id:
        results = await service.list_sops_by_alert_rule(alert_rule_id)
    else:
        results = await service.list_sops(enabled_only=enabled_only)
    
    return {"code": 0, "data": results}


@router.get("/sops/{sop_id}", response_model=dict)
async def get_sop(
    sop_id: str,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """获取SOP详情"""
    result = await service.get_sop(sop_id)
    if not result:
        raise HTTPException(status_code=404, detail="SOP不存在")
    
    return {"code": 0, "data": result}


@router.post("/sops", response_model=dict)
async def create_sop(
    sop: SOPCreate,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """创建SOP"""
    data = sop.model_dump()
    try:
        result = await service.create_sop(data)
        return {"code": 0, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/sops/{sop_id}", response_model=dict)
async def update_sop(
    sop_id: str,
    sop: SOPUpdate,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """更新SOP"""
    data = sop.model_dump(exclude_unset=True)
    result = await service.update_sop(sop_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="SOP不存在")
    
    return {"code": 0, "data": result}


@router.delete("/sops/{sop_id}", response_model=dict)
async def delete_sop(
    sop_id: str,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """删除SOP"""
    success = await service.delete_sop(sop_id)
    if not success:
        raise HTTPException(status_code=404, detail="SOP不存在")
    
    return {"code": 0, "message": "删除成功"}


# ============ 案例路由 ============

@router.get("/cases", response_model=dict)
async def list_cases(
    alert_rule_id: Optional[str] = None,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """列出案例"""
    if alert_rule_id:
        results = await service.list_cases_by_alert_rule(alert_rule_id)
    else:
        results = await service.list_cases()
    
    return {"code": 0, "data": results}


@router.get("/cases/{case_id}", response_model=dict)
async def get_case(
    case_id: str,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """获取案例详情"""
    result = await service.get_case(case_id)
    if not result:
        raise HTTPException(status_code=404, detail="案例不存在")
    
    return {"code": 0, "data": result}


@router.post("/cases", response_model=dict)
async def create_case(
    case: CaseCreate,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """创建案例"""
    data = case.model_dump()
    try:
        result = await service.create_case(data)
        return {"code": 0, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/cases/{case_id}", response_model=dict)
async def update_case(
    case_id: str,
    case: CaseUpdate,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """更新案例"""
    data = case.model_dump(exclude_unset=True)
    result = await service.update_case(case_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="案例不存在")
    
    return {"code": 0, "data": result}


@router.delete("/cases/{case_id}", response_model=dict)
async def delete_case(
    case_id: str,
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """删除案例"""
    success = await service.delete_case(case_id)
    if not success:
        raise HTTPException(status_code=404, detail="案例不存在")
    
    return {"code": 0, "message": "删除成功"}


# ============ 搜索路由 ============

@router.get("/search", response_model=dict)
async def search_knowledge(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    type: Optional[List[ContentTypeEnum]] = Query(None, description="限定内容类型"),
    limit: int = Query(10, ge=1, le=100),
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """统一搜索接口"""
    content_types = [t.value for t in type] if type else None
    results = await service.unified_search(q, content_types=content_types)
    
    # 限制返回数量
    results = results[:limit]
    
    return {
        "code": 0,
        "data": {
            "query": q,
            "count": len(results),
            "results": [r.__dict__ for r in results]
        }
    }


# ============ 统计路由 ============

@router.get("/stats", response_model=dict)
async def get_stats(
    service: KnowledgeBaseService = Depends(get_kb_service)
):
    """获取知识库统计信息"""
    stats = await service.get_stats()
    return {"code": 0, "data": stats}


# ============================================================
# 观察点元数据路由 - Round 20
# ============================================================

from src.knowledge.db.repositories.observation_point_repo import ObservationPointRepository
from src.knowledge.services.observation_point_service import ObservationPointService


class ObservationPointCreate(BaseModel):
    """观察点创建模型"""
    id: str
    resource_type: str
    metric_name: str
    collection_method: str
    representation: str
    anomaly_pattern: Optional[str] = None
    anomaly_condition: Optional[str] = None
    unit: Optional[str] = None
    severity: Optional[str] = None
    metadata: Optional[dict] = None


async def get_op_service():
    """获取观察点服务"""
    conn = await get_knowledge_db()
    repo = ObservationPointRepository(conn)
    service = ObservationPointService(repo)
    try:
        yield service
    finally:
        await close_knowledge_db(conn)


@router.get("/observation-points", response_model=dict)
async def list_observation_points(
    resource_type: Optional[str] = Query(None, description="资源类型过滤，如 OS.CPU"),
    limit: int = Query(100, ge=1, le=500),
    service: ObservationPointService = Depends(get_op_service)
):
    """列出所有观察点
    
    可按资源类型过滤。
    """
    if resource_type:
        results = service.list_observation_points(entity_type=resource_type)
    else:
        results = service.list_observation_points()
    
    return {"code": 0, "data": results, "count": len(results)}


@router.get("/observation-points/{op_id}", response_model=dict)
async def get_observation_point(
    op_id: str,
    service: ObservationPointService = Depends(get_op_service)
):
    """获取观察点详情"""
    conn = await get_knowledge_db()
    repo = ObservationPointRepository(conn)
    
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    op = loop.run_until_complete(repo.get_observation_point_by_id(op_id))
    await close_knowledge_db(conn)
    
    if not op:
        raise HTTPException(status_code=404, detail="观察点不存在")
    
    return {"code": 0, "data": op.to_dict()}


@router.get("/observation-points/resource/{resource_type}", response_model=dict)
async def get_observation_points_by_resource(
    resource_type: str,
    service: ObservationPointService = Depends(get_op_service)
):
    """获取指定资源类型的所有观察点"""
    results = service.list_observation_points(entity_type=resource_type)
    
    return {"code": 0, "data": results, "count": len(results)}


@router.post("/observation-points", response_model=dict)
async def create_observation_point(
    op: ObservationPointCreate,
    service: ObservationPointService = Depends(get_op_service)
):
    """创建新的观察点"""
    op_data = op.model_dump()
    try:
        result = service.add_observation_point(op_data)
        return {"code": 0, "data": result.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/alert-context/{alert_id}", response_model=dict)
async def get_alert_context(
    alert_id: str,
    service: ObservationPointService = Depends(get_op_service)
):
    """获取告警上下文（包含观察点元数据）
    
    根据alert_id查询告警信息，并关联对应的观察点元数据，
    生成增强的告警上下文，包含采集方法、表示方法、异常模式等信息。
    
    注意：此接口需要配合告警服务使用，alert_id用于定位告警，
    实际的resource_type和metric从告警数据中提取。
    """
    # 获取告警上下文
    # 这里简化处理，实际应该从告警服务获取告警详情
    # 但为了不影响现有架构，我们返回提示信息
    return {
        "code": 0,
        "data": {
            "message": "请提供告警的resource_type和metric参数以获取完整的观察点上下文",
            "alert_id": alert_id,
            "hint": "使用 GET /api/v1/knowledge/alert-context/{alert_id}?resource_type=OS.CPU&metric=usage_percent"
        }
    }


@router.get("/alert-context", response_model=dict)
async def get_alert_context_by_params(
    resource_type: str = Query(..., description="资源类型，如 OS.CPU"),
    metric: str = Query(..., description="指标名称，如 usage_percent"),
    alert_data: Optional[str] = Query(None, description="告警数据JSON字符串")
):
    """获取告警上下文（通过查询参数）
    
    提供resource_type和metric，直接获取对应的观察点元数据。
    可选提供alert_data用于生成完整的告警上下文。
    """
    conn = await get_knowledge_db()
    repo = ObservationPointRepository(conn)
    service = ObservationPointService(repo)
    
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    op_dict = service.get_observation_point(resource_type, metric)
    await close_knowledge_db(conn)
    
    if not op_dict:
        return {
            "code": 0,
            "data": {
                "observation_point": None,
                "explanation": f"未找到指标「{resource_type}.{metric}」的观察点元数据",
            }
        }
    
    # 如果提供了告警数据，生成完整上下文
    if alert_data:
        import json
        try:
            alert = json.loads(alert_data)
            context = service.generate_alert_context(alert)
            context["observation_point"] = op_dict
            return {"code": 0, "data": context}
        except json.JSONDecodeError:
            pass
    
    return {
        "code": 0,
        "data": {
            "resource_type": resource_type,
            "metric": metric,
            "observation_point": op_dict,
            "explanation": f"指标「{resource_type}.{metric}」的采集方法为: {op_dict.get('collection_method', 'N/A')}",
        }
    }
