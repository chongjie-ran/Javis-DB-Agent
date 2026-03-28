"""告警路由 - 增强版"""
import time
import random
from typing import Optional

from fastapi import APIRouter, Path, Query, HTTPException
from mock_zcloud_api.models_enhanced import (
    gen_enhanced_alert,
    gen_enhanced_instance,
    AlertCustomFields,
    AlertAnnotation,
    NestedAlert
)

router = APIRouter()

# 告警代码到名称的映射
ALERT_CODES = {
    "CPU_HIGH": {"name": "CPU使用率过高", "severity": "warning", "unit": "%"},
    "MEMORY_HIGH": {"name": "内存使用率过高", "severity": "warning", "unit": "%"},
    "DISK_HIGH": {"name": "磁盘使用率过高", "severity": "warning", "unit": "%"},
    "LOCK_WAIT_TIMEOUT": {"name": "锁等待超时", "severity": "warning", "unit": "秒"},
    "CONNECTION_HIGH": {"name": "连接数过高", "severity": "warning", "unit": ""},
    "SLOW_QUERY": {"name": "慢查询检测", "severity": "info", "unit": "秒"},
    "REPLICATION_LAG": {"name": "复制延迟", "severity": "warning", "unit": "秒"},
    "BACKUP_FAILED": {"name": "备份失败", "severity": "critical", "unit": ""},
    "CRITICAL_ERROR": {"name": "严重错误", "severity": "critical", "unit": ""},
}

# 预生成的告警池
_cached_alerts = {}


def _init_cached_alerts():
    """初始化告警缓存池"""
    global _cached_alerts
    if not _cached_alerts:
        now = time.time()
        alert_codes = list(ALERT_CODES.keys())
        instances = [
            ("INS-001", "PROD-ORDER-DB"),
            ("INS-002", "PROD-USER-DB"),
            ("INS-003", "PROD-ANALYTICS-DB"),
            ("INS-004", "PROD-PAYMENT-DB"),
            ("INS-005", "PROD-LOGISTICS-DB"),
        ]
        
        for i in range(1, 51):
            alert_code = random.choice(alert_codes)
            instance = random.choice(instances)
            info = ALERT_CODES[alert_code]
            
            # 生成合理的指标值
            if alert_code == "CPU_HIGH":
                metric_value = random.uniform(80, 98)
                threshold = 80.0
            elif alert_code == "MEMORY_HIGH":
                metric_value = random.uniform(85, 97)
                threshold = 85.0
            elif alert_code == "DISK_HIGH":
                metric_value = random.uniform(85, 98)
                threshold = 85.0
            elif alert_code == "LOCK_WAIT_TIMEOUT":
                metric_value = random.uniform(60, 600)
                threshold = 60.0
            elif alert_code == "CONNECTION_HIGH":
                metric_value = random.uniform(400, 495)
                threshold = 400.0
            elif alert_code == "SLOW_QUERY":
                metric_value = random.uniform(5, 120)
                threshold = 5.0
            elif alert_code == "REPLICATION_LAG":
                metric_value = random.uniform(10, 300)
                threshold = 10.0
            else:
                metric_value = 0.0
                threshold = 0.0
            
            alert_id = f"ALT-20260328-{str(i).zfill(3)}"
            _cached_alerts[alert_id] = gen_enhanced_alert(
                alert_id=alert_id,
                alert_code=alert_code,
                severity=info["severity"],
                instance_id=instance[0],
                instance_name=instance[1],
                metric_value=round(metric_value, 1),
                threshold=threshold
            )


@router.get("/alerts")
async def list_alerts(
    instance_id: Optional[str] = Query(None, description="实例ID"),
    severity: Optional[str] = Query(None, description="严重级别: critical/warning/info"),
    status: Optional[str] = Query(None, description="状态: firing/resolved"),
    alert_code: Optional[str] = Query(None, description="告警代码"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """查询告警列表"""
    _init_cached_alerts()
    
    results = []
    for alert in _cached_alerts.values():
        # 过滤条件
        if instance_id and alert.instance_id != instance_id:
            continue
        if severity and alert.severity != severity:
            continue
        if status and alert.status != status:
            continue
        if alert_code and alert.alert_code != alert_code:
            continue
        results.append(alert)
    
    # 分页
    total = len(results)
    results = results[offset:offset + limit]
    
    return {
        "code": 0,
        "message": "success",
        "data": [alert.model_dump() for alert in results],
        "total": total,
        "limit": limit,
        "offset": offset,
        "timestamp": time.time()
    }


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str = Path(..., description="告警ID")):
    """获取告警详情"""
    _init_cached_alerts()
    
    alert = _cached_alerts.get(alert_id)
    if not alert:
        # 动态生成一个
        alert = gen_enhanced_alert(
            alert_id=alert_id,
            alert_code="CPU_HIGH",
            severity="warning",
            instance_id="INS-001",
            instance_name="PROD-ORDER-DB",
            metric_value=85.5,
            threshold=80.0
        )
    
    return {
        "code": 0,
        "message": "success",
        "data": alert.model_dump()
    }


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str = Path(..., description="告警ID"),
    acknowledged_by: str = Query(..., description="确认人"),
    comment: Optional[str] = Query(None, description="备注")
):
    """确认告警"""
    _init_cached_alerts()
    
    if alert_id not in _cached_alerts:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert = _cached_alerts[alert_id]
    alert.acknowledged = True
    alert.annotations.acknowledged_by = acknowledged_by
    alert.annotations.acknowledged_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "alert_id": alert_id,
            "acknowledged": True,
            "acknowledged_by": acknowledged_by,
            "acknowledged_at": alert.annotations.acknowledged_at
        }
    }


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str = Path(..., description="告警ID"),
    resolved_by: str = Query(..., description="解决人"),
    resolution: str = Query(..., description="解决方案"),
    resolution_type: str = Query("fixed", description="解决类型: fixed/ignored/false_positive")
):
    """解决告警"""
    _init_cached_alerts()
    
    if alert_id not in _cached_alerts:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert = _cached_alerts[alert_id]
    alert.status = "resolved"
    alert.annotations.resolved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "alert_id": alert_id,
            "status": "resolved",
            "resolved_by": resolved_by,
            "resolved_at": alert.annotations.resolved_at,
            "resolution": resolution,
            "resolution_type": resolution_type
        }
    }


@router.get("/alerts/stats/summary")
async def get_alert_stats(
    instance_id: Optional[str] = Query(None, description="实例ID")
):
    """获取告警统计摘要"""
    _init_cached_alerts()
    
    stats = {
        "total": 0,
        "firing": 0,
        "resolved": 0,
        "by_severity": {
            "critical": 0,
            "warning": 0,
            "info": 0
        },
        "by_type": {}
    }
    
    for alert in _cached_alerts.values():
        if instance_id and alert.instance_id != instance_id:
            continue
        
        stats["total"] += 1
        if alert.status == "firing":
            stats["firing"] += 1
        else:
            stats["resolved"] += 1
        
        stats["by_severity"][alert.severity] = stats["by_severity"].get(alert.severity, 0) + 1
        stats["by_type"][alert.alert_code] = stats["by_type"].get(alert.alert_code, 0) + 1
    
    return {
        "code": 0,
        "message": "success",
        "data": stats,
        "timestamp": time.time()
    }


@router.get("/alerts/{alert_id}/related")
async def get_related_alerts(
    alert_id: str = Path(..., description="告警ID"),
    limit: int = Query(10, ge=1, le=50, description="返回数量")
):
    """获取关联告警"""
    _init_cached_alerts()
    
    if alert_id not in _cached_alerts:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    source_alert = _cached_alerts[alert_id]
    
    # 查找同一实例的同类型告警
    related = []
    for alert in _cached_alerts.values():
        if alert.alert_id == alert_id:
            continue
        if alert.instance_id == source_alert.instance_id:
            if alert.alert_code == source_alert.alert_code or alert.severity == source_alert.severity:
                related.append(alert)
                if len(related) >= limit:
                    break
    
    return {
        "code": 0,
        "message": "success",
        "data": [alert.model_dump() for alert in related],
        "total": len(related)
    }
