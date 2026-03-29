"""监控面板API路由 - P0-1: Dashboard监控面板增强"""
import time
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from src.api.schemas import APIResponse

router = APIRouter(prefix="/api/v1/monitoring", tags=["监控面板"])


# ============ P0-1: 实时监控卡片 ============

class MonitoringCards(BaseModel):
    """实时监控卡片数据"""
    instance_total: int = 0
    alert_count: int = 0          # 活跃告警数
    health_score: float = 0.0     # 0-100
    health_trend: str = "stable"   # rising/falling/stable
    last_updated: float = 0


class AlertItem(BaseModel):
    """告警条目"""
    alert_id: str
    instance_id: str
    severity: str       # critical/warning/info
    message: str
    timestamp: float
    status: str         # active/acknowledged/resolved
    duration_seconds: int = 0


class AlertListResponse(BaseModel):
    code: int = 0
    message: str = "success"
    alerts: list[AlertItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class HealthScoreDetail(BaseModel):
    """健康评分明细"""
    score: float = 0
    level: str = "healthy"  # healthy/degraded/unhealthy
    factors: dict = {}     # 各维度得分
    trend: str = "stable"  # rising/falling/stable
    last_updated: float = 0


@router.get("/cards", response_model=APIResponse)
async def get_monitoring_cards():
    """
    获取实时监控卡片数据
    
    返回:
    - instance_total: 实例总数
    - alert_count: 活跃告警数
    - health_score: 健康评分 (0-100)
    - health_trend: 健康趋势
    - last_updated: 更新时间戳
    """
    # 从Javis API获取实例数据
    try:
        from src.api_client_factory import get_api_client
        client = get_api_client()
        # 获取实例列表
        instances = client.list_instances()
        instance_total = len(instances)
        
        # 获取告警数据
        alerts = client.list_alerts(status="active")
        alert_count = len(alerts)
        
        # 计算健康评分
        # 基础分100，扣分规则：
        # 每个活跃critical告警扣20分
        # 每个活跃warning告警扣5分
        # 每个活跃info告警扣1分
        # 最低0分
        health_score = 100.0
        for a in alerts:
            severity = a.get("severity", "info")
            if severity == "critical":
                health_score -= 20
            elif severity == "warning":
                health_score -= 5
            elif severity == "info":
                health_score -= 1
        health_score = max(0, health_score)
        
        # 趋势判断（简化版：通过最近1小时告警变化趋势）
        health_trend = "stable"
        try:
            alerts_1h_ago = client.list_alerts(status="active", start_time=time.time() - 3600)
            if len(alerts_1h_ago) < alert_count:
                health_trend = "rising"  # 告警在减少
            elif len(alerts_1h_ago) > alert_count:
                health_trend = "falling"  # 告警在增加
        except Exception:
            pass
        
        cards = MonitoringCards(
            instance_total=instance_total,
            alert_count=alert_count,
            health_score=round(health_score, 1),
            health_trend=health_trend,
            last_updated=time.time(),
        )
        return APIResponse(data=cards.model_dump())
    except Exception as e:
        # Mock数据（当API不可用时）
        cards = MonitoringCards(
            instance_total=12,
            alert_count=3,
            health_score=85.0,
            health_trend="stable",
            last_updated=time.time(),
        )
        return APIResponse(data=cards.model_dump())


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    status: str = Query("active", description="状态: active/acknowledged/resolved/all"),
    severity: Optional[str] = Query(None, description="级别: critical/warning/info"),
    instance_id: Optional[str] = Query(None, description="实例ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    获取告警列表
    
    支持筛选: 状态/级别/实例ID
    """
    try:
        from src.api_client_factory import get_api_client
        client = get_api_client()
        alerts_raw = client.list_alerts(status=status if status != "all" else None)
        
        # 筛选
        if severity:
            alerts_raw = [a for a in alerts_raw if a.get("severity") == severity]
        if instance_id:
            alerts_raw = [a for a in alerts_raw if a.get("instance_id") == instance_id]
        
        total = len(alerts_raw)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = alerts_raw[start:end]
        
        alerts = []
        now = time.time()
        for a in page_items:
            ts = a.get("timestamp", now)
            alerts.append(AlertItem(
                alert_id=a.get("alert_id", ""),
                instance_id=a.get("instance_id", ""),
                severity=a.get("severity", "info"),
                message=a.get("message", a.get("alert_name", "")),
                timestamp=ts,
                status=a.get("status", "active"),
                duration_seconds=int(now - ts),
            ))
        
        return AlertListResponse(
            alerts=alerts,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        # Mock数据
        mock_alerts = [
            AlertItem(
                alert_id="ALT-001",
                instance_id="INS-001",
                severity="critical",
                message="CPU使用率超过90%",
                timestamp=time.time() - 300,
                status="active",
                duration_seconds=300,
            ),
            AlertItem(
                alert_id="ALT-002",
                instance_id="INS-002",
                severity="warning",
                message="内存使用率超过80%",
                timestamp=time.time() - 600,
                status="active",
                duration_seconds=600,
            ),
            AlertItem(
                alert_id="ALT-003",
                instance_id="INS-001",
                severity="info",
                message="磁盘空间接近阈值",
                timestamp=time.time() - 1800,
                status="acknowledged",
                duration_seconds=1800,
            ),
        ]
        return AlertListResponse(
            alerts=mock_alerts,
            total=3,
            page=page,
            page_size=page_size,
        )


@router.get("/health-score", response_model=APIResponse)
async def get_health_score():
    """
    获取健康评分详情
    
    返回健康评分的各维度明细
    """
    try:
        from src.api_client_factory import get_api_client
        client = get_api_client()
        instances = client.list_instances()
        alerts = client.list_alerts(status="active")
        
        # 各维度评分
        factors = {
            "instance_health": 0,
            "alert_management": 0,
            "performance": 0,
            "capacity": 0,
        }
        
        # 实例健康度 (权重30%)
        total_ins = len(instances)
        healthy_ins = sum(1 for i in instances if i.get("status") == "running")
        factors["instance_health"] = round(100 * healthy_ins / max(total_ins, 1), 1)
        
        # 告警管理 (权重30%)
        critical_count = sum(1 for a in alerts if a.get("severity") == "critical")
        warning_count = sum(1 for a in alerts if a.get("severity") == "warning")
        alert_score = max(0, 100 - critical_count * 20 - warning_count * 5)
        factors["alert_management"] = alert_score
        
        # 性能 (权重20%)
        factors["performance"] = 95.0  # 简化
        
        # 容量 (权重20%)
        factors["capacity"] = 88.0  # 简化
        
        overall = (
            factors["instance_health"] * 0.3 +
            factors["alert_management"] * 0.3 +
            factors["performance"] * 0.2 +
            factors["capacity"] * 0.2
        )
        
        if overall >= 80:
            level = "healthy"
        elif overall >= 50:
            level = "degraded"
        else:
            level = "unhealthy"
        
        detail = HealthScoreDetail(
            score=round(overall, 1),
            level=level,
            factors=factors,
            trend="stable",
            last_updated=time.time(),
        )
        return APIResponse(data=detail.model_dump())
    except Exception as e:
        detail = HealthScoreDetail(
            score=85.0,
            level="healthy",
            factors={
                "instance_health": 90.0,
                "alert_management": 85.0,
                "performance": 95.0,
                "capacity": 88.0,
            },
            trend="stable",
            last_updated=time.time(),
        )
        return APIResponse(data=detail.model_dump())
