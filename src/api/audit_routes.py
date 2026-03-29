"""审计日志查看器API路由 - P0-2: 审计日志查看器"""
import time
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Query, Header, HTTPException
from pydantic import BaseModel, Field
from src.api.schemas import APIResponse

router = APIRouter(prefix="/api/v1/audit", tags=["审计日志"])


# ============ P0-2: 审计日志查看器 ============

class AuditLogItem(BaseModel):
    """审计日志条目"""
    id: str
    timestamp: float
    timestamp_str: str
    action: str
    user_id: str
    session_id: str = ""
    agent_name: str = ""
    tool_name: str = ""
    risk_level: int = 0
    result: str = ""
    ip_address: str = ""
    duration_ms: int = 0
    prev_hash: str = ""
    hash: str = ""
    chain_valid: bool = True


class AuditListResponse(BaseModel):
    code: int = 0
    message: str = "success"
    logs: list[AuditLogItem] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class ChainVerification(BaseModel):
    """哈希链验证结果"""
    is_valid: bool
    error_message: Optional[str] = None
    broken_index: Optional[int] = None
    total_records: int = 0
    first_record: Optional[str] = None
    last_record: Optional[str] = None
    genesis_hash: str = ""
    checked_at: float = 0


def _log_to_item(log) -> AuditLogItem:
    """将AuditLog转换为API响应格式"""
    return AuditLogItem(
        id=log.id,
        timestamp=log.timestamp,
        timestamp_str=log.timestamp_str,
        action=log.action.value if hasattr(log.action, 'value') else str(log.action),
        user_id=log.user_id,
        session_id=log.session_id,
        agent_name=log.agent_name,
        tool_name=log.tool_name,
        risk_level=log.risk_level,
        result=log.result,
        ip_address=log.ip_address,
        duration_ms=log.duration_ms,
        prev_hash=log.prev_hash[:16] + "..." if log.prev_hash else "",
        hash=log.hash[:16] + "..." if log.hash else "",
        chain_valid=True,
    )


@router.get("/logs", response_model=AuditListResponse)
async def list_audit_logs(
    user_id: Optional[str] = Query(None, description="用户ID"),
    session_id: Optional[str] = Query(None, description="会话ID"),
    action: Optional[str] = Query(None, description="动作类型"),
    tool_name: Optional[str] = Query(None, description="工具名称"),
    start_time: Optional[float] = Query(None, description="开始时间戳"),
    end_time: Optional[float] = Query(None, description="结束时间戳"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """
    查询审计日志
    
    支持筛选条件:
    - user_id: 用户ID
    - session_id: 会话ID
    - action: 动作类型 (session.create/agent.invoke/tool.call等)
    - tool_name: 工具名称
    - start_time / end_time: 时间范围
    """
    from src.gateway.audit import get_audit_logger, AuditAction
    
    audit = get_audit_logger()
    
    # 转换action字符串到枚举
    action_enum = None
    if action:
        try:
            action_enum = AuditAction(action)
        except ValueError:
            pass  # 未知action类型，不筛选
    
    logs = audit.query(
        user_id=user_id,
        session_id=session_id,
        action=action_enum,
        tool_name=tool_name,
        start_time=start_time,
        end_time=end_time,
        limit=page_size * page,  # 取足够多再分页
    )
    
    total = len(logs)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = logs[start:end]
    
    return AuditListResponse(
        logs=[_log_to_item(log) for log in page_items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/logs/{log_id}", response_model=APIResponse)
async def get_audit_log(log_id: str):
    """
    获取单条审计日志详情
    """
    from src.gateway.audit import get_audit_logger
    
    audit = get_audit_logger()
    for log in audit._logs:
        if log.id == log_id:
            item = _log_to_item(log)
            # 完整哈希（非截断）
            item.prev_hash = log.prev_hash
            item.hash = log.hash
            return APIResponse(data=item.model_dump())
    raise HTTPException(status_code=404, detail=f"日志不存在: {log_id}")


@router.get("/chain/verify", response_model=ChainVerification)
async def verify_chain():
    """
    验证哈希链完整性
    
    检查审计日志是否被篡改
    - 验证每条记录的前驱哈希是否匹配
    - 验证每条记录的自身哈希是否正确
    """
    from src.gateway.audit import get_audit_logger, GENESIS_HASH
    
    audit = get_audit_logger()
    is_valid, error_msg, broken_idx = audit.verify_chain()
    stats = audit.get_stats()
    
    return ChainVerification(
        is_valid=is_valid,
        error_message=error_msg,
        broken_index=broken_idx,
        total_records=stats["total_records"],
        first_record=stats["first_record"],
        last_record=stats["last_record"],
        genesis_hash=GENESIS_HASH,
        checked_at=time.time(),
    )


@router.get("/chain/suspicious", response_model=APIResponse)
async def detect_suspicious(
    hours: int = Query(24, ge=1, le=720, description="检测最近N小时的记录")
):
    """
    篡改检测
    
    返回可疑记录列表
    """
    from src.gateway.audit import get_audit_logger
    
    audit = get_audit_logger()
    check_from = time.time() - hours * 3600
    suspicious = audit.detect_tampering(check_from=check_from)
    return APIResponse(data={
        "suspicious_records": suspicious,
        "total_checked": len(audit._logs),
        "hours": hours,
    })


@router.get("/stats", response_model=APIResponse)
async def audit_stats():
    """
    获取审计统计信息
    """
    from src.gateway.audit import get_audit_logger, AuditAction
    
    audit = get_audit_logger()
    stats = audit.get_stats()
    
    # 动作类型统计
    action_counts: dict = {}
    for log in audit._logs:
        action_str = log.action.value if hasattr(log.action, 'value') else str(log.action)
        action_counts[action_str] = action_counts.get(action_str, 0) + 1
    
    # 用户统计
    user_counts: dict = {}
    for log in audit._logs:
        if log.user_id:
            user_counts[log.user_id] = user_counts.get(log.user_id, 0) + 1
    
    return APIResponse(data={
        **stats,
        "action_counts": action_counts,
        "user_counts": user_counts,
    })


@router.get("/actions", response_model=APIResponse)
async def list_action_types():
    """
    获取所有可用的审计动作类型
    """
    from src.gateway.audit import AuditAction
    return APIResponse(data={
        "actions": [
            {"value": a.value, "name": a.name}
            for a in AuditAction
        ]
    })
