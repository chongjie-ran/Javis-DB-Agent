"""实例管理路由 - 增强版"""
import time
import random
from typing import Optional

from fastapi import APIRouter, Path, Query, HTTPException
from mock_javis_api.models_enhanced import (
    gen_enhanced_instance,
    gen_enhanced_sessions,
    gen_enhanced_locks,
    gen_enhanced_tablespaces
)

router = APIRouter()

# 实例缓存
_cached_instances = {}


def _init_cached_instances():
    """初始化实例缓存"""
    global _cached_instances
    if not _cached_instances:
        instances = [
            ("INS-001", "PROD-ORDER-DB", "postgresql", "primary"),
            ("INS-002", "PROD-USER-DB", "postgresql", "primary"),
            ("INS-003", "PROD-ANALYTICS-DB", "mysql", "primary"),
            ("INS-004", "PROD-PAYMENT-DB", "postgresql", "primary"),
            ("INS-005", "PROD-LOGISTICS-DB", "mysql", "primary"),
            ("INS-006", "PROD-HISTORY-DB", "postgresql", "standby"),
            ("INS-007", "STAGE-ORDER-DB", "postgresql", "primary"),
            ("INS-008", "DEV-USER-DB", "mysql", "primary"),
        ]
        
        for inst_id, inst_name, db_type, role in instances:
            _cached_instances[inst_id] = gen_enhanced_instance(
                instance_id=inst_id,
                instance_name=inst_name,
                db_type=db_type,
                role=role,
                custom_override={"status": "running"}
            )


@router.get("/instances")
async def list_instances(
    status: Optional[str] = Query(None, description="实例状态"),
    db_type: Optional[str] = Query(None, description="数据库类型"),
    region: Optional[str] = Query(None, description="区域"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """列出实例"""
    _init_cached_instances()
    
    results = []
    for inst in _cached_instances.values():
        if status and inst.status != status:
            continue
        if db_type and inst.db_type != db_type:
            continue
        if region and inst.region != region:
            continue
        results.append(inst)
    
    total = len(results)
    results = results[offset:offset + limit]
    
    return {
        "code": 0,
        "message": "success",
        "data": [inst.model_dump() for inst in results],
        "total": total,
        "limit": limit,
        "offset": offset,
        "timestamp": time.time()
    }


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str = Path(..., description="实例ID")):
    """获取实例详情"""
    _init_cached_instances()
    
    if instance_id not in _cached_instances:
        # 动态生成
        inst = gen_enhanced_instance(
            instance_id=instance_id,
            instance_name=f"DB-{instance_id}",
            db_type="postgresql",
            role="primary"
        )
    else:
        inst = _cached_instances[instance_id]
    
    return {
        "code": 0,
        "message": "success",
        "data": inst.model_dump()
    }


@router.get("/instances/{instance_id}/metrics")
async def get_instance_metrics(
    instance_id: str = Path(..., description="实例ID"),
    metrics: Optional[str] = Query(None, description="指标类型，逗号分隔"),
    start_time: Optional[float] = Query(None, description="开始时间戳"),
    end_time: Optional[float] = Query(None, description="结束时间戳")
):
    """获取实例指标"""
    _init_cached_instances()
    
    if instance_id not in _cached_instances:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    now = time.time()
    if not end_time:
        end_time = now
    if not start_time:
        start_time = now - 3600  # 默认1小时
    
    # 解析指标
    metric_list = metrics.split(",") if metrics else ["cpu", "memory", "disk", "connections"]
    
    # 生成60个数据点
    points = []
    step = (end_time - start_time) / 60
    for i in range(60):
        ts = start_time + step * i
        point = {"timestamp": ts}
        if "cpu" in metric_list:
            point["cpu"] = round(random.uniform(20, 90), 2)
        if "memory" in metric_list:
            point["memory"] = round(random.uniform(40, 85), 2)
        if "disk" in metric_list:
            point["disk"] = round(random.uniform(30, 75), 2)
        if "connections" in metric_list:
            point["connections"] = random.randint(50, 400)
        points.append(point)
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "instance_id": instance_id,
            "metrics": metric_list,
            "data_points": points,
            "start_time": start_time,
            "end_time": end_time,
            "count": len(points)
        },
        "timestamp": now
    }


@router.get("/instances/{instance_id}/sessions")
async def get_sessions(
    instance_id: str = Path(..., description="实例ID"),
    status: Optional[str] = Query(None, description="会话状态"),
    username: Optional[str] = Query(None, description="用户名"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """获取会话列表"""
    sessions = gen_enhanced_sessions(limit=50)
    
    # 过滤
    if status:
        sessions = [s for s in sessions if s.status == status]
    if username:
        sessions = [s for s in sessions if username.lower() in s.username.lower()]
    
    total = len(sessions)
    sessions = sessions[offset:offset + limit]
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "instance_id": instance_id,
            "sessions": [s.model_dump() for s in sessions],
            "total": total,
            "active_count": sum(1 for s in sessions if s.status == "ACTIVE"),
            "limit": limit,
            "offset": offset
        },
        "timestamp": time.time()
    }


@router.get("/instances/{instance_id}/locks")
async def get_locks(
    instance_id: str = Path(..., description="实例ID"),
    include_blocker: bool = Query(True, description="包含阻塞者信息")
):
    """获取锁等待信息"""
    locks = gen_enhanced_locks(limit=5)
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "instance_id": instance_id,
            "locks": [lock.model_dump() for lock in locks],
            "total_blocked": len(locks),
            "deadlock_count": 0
        },
        "timestamp": time.time()
    }


@router.get("/instances/{instance_id}/tablespaces")
async def get_tablespaces(
    instance_id: str = Path(..., description="实例ID"),
    tablespace_name: Optional[str] = Query(None, description="表空间名称")
):
    """获取表空间信息"""
    tablespaces = gen_enhanced_tablespaces()
    
    if tablespace_name:
        tablespaces = [t for t in tablespaces if t.tablespace_name == tablespace_name]
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "instance_id": instance_id,
            "tablespaces": [t.model_dump() for t in tablespaces],
            "total_count": len(tablespaces)
        },
        "timestamp": time.time()
    }


@router.get("/instances/{instance_id}/health")
async def get_health_score(instance_id: str = Path(..., description="实例ID")):
    """获取健康评分"""
    _init_cached_instances()
    
    if instance_id not in _cached_instances:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    # 计算健康分
    health_score = random.randint(70, 99)
    
    findings = []
    if health_score < 80:
        findings.append({"type": "性能", "severity": "warning", "description": "CPU使用率偏高"})
    if health_score < 90:
        findings.append({"type": "容量", "severity": "info", "description": "表空间使用率偏高"})
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "instance_id": instance_id,
            "health_score": health_score,
            "status": "healthy" if health_score >= 80 else "degraded",
            "findings": findings
        },
        "timestamp": time.time()
    }
