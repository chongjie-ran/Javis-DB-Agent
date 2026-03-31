"""
审批 API 路由

提供审批操作的 REST 接口：
- GET  /api/v1/approvals/<request_id>          查看审批请求详情
- POST /api/v1/approvals/<request_id>/approve   审批通过
- POST /api/v1/approvals/<request_id>/reject    审批拒绝
- GET  /api/v1/approvals/pending                列出所有待审批请求
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


# ---------------------------------------------------------------------------
# 依赖：获取 ApprovalGate 实例
# ---------------------------------------------------------------------------

def get_approval_gate():
    """
    从 app state 或 context 中获取 ApprovalGate 实例。

    使用方需在 FastAPI app 中注册：
        from src.gateway.approval import ApprovalGate
        app.state.approval_gate = ApprovalGate(timeout_seconds=300)

    若未注册，返回 None（路由层会返回 503）。
    """
    # 延迟导入，避免循环依赖
    try:
        from ..main import app as fastapi_app
        return getattr(fastapi_app.state, "approval_gate", None)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ApproveRequest(BaseModel):
    approver: str
    comment: str = ""


class RejectRequest(BaseModel):
    approver: str
    reason: str = ""


class ApprovalResponse(BaseModel):
    request_id: str
    status: str
    action: str
    risk_level: str
    requester: str
    approvers: list[str]
    comments: list[str]
    created_at: float

    @classmethod
    def from_request(cls, req) -> "ApprovalResponse":
        return cls(
            request_id=req.request_id,
            status=req.status.value,
            action=req.action,
            risk_level=req.risk_level,
            requester=req.requester,
            approvers=req.approvers,
            comments=req.comments,
            created_at=req.created_at,
        )


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@router.get("/pending", response_model=list[ApprovalResponse])
async def list_pending_approvals():
    """列出所有待审批的请求"""
    gate = get_approval_gate()
    if not gate:
        raise HTTPException(status_code=503, detail="ApprovalGate not configured")
    pending = gate.list_pending()
    return [ApprovalResponse.from_request(r) for r in pending]


@router.get("/{request_id}", response_model=ApprovalResponse)
async def get_approval_request(request_id: str):
    """查看指定审批请求的详情"""
    gate = get_approval_gate()
    if not gate:
        raise HTTPException(status_code=503, detail="ApprovalGate not configured")
    req = gate.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")
    return ApprovalResponse.from_request(req)


@router.post("/{request_id}/approve")
async def approve_request(request_id: str, body: ApproveRequest):
    """审批通过"""
    gate = get_approval_gate()
    if not gate:
        raise HTTPException(status_code=503, detail="ApprovalGate not configured")
    success = await gate.approve(request_id, body.approver, body.comment)
    if not success:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")
    req = gate.get_request(request_id)
    return {
        "request_id": request_id,
        "status": req.status.value if req else "unknown",
        "message": "approved" if req and req.status.value == "approved"
                   else f"approved ({req.approval_count}/{req.required_approvals} approvals)"
                   if req else "unknown",
    }


@router.post("/{request_id}/reject")
async def reject_request(request_id: str, body: RejectRequest):
    """审批拒绝"""
    gate = get_approval_gate()
    if not gate:
        raise HTTPException(status_code=503, detail="ApprovalGate not configured")
    success = await gate.reject(request_id, body.approver, body.reason)
    if not success:
        raise HTTPException(status_code=404, detail=f"Request not found: {request_id}")
    return {
        "request_id": request_id,
        "status": "rejected",
        "message": f"rejected by {body.approver}: {body.reason}",
    }
