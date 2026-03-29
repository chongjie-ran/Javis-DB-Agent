"""会话路由"""
from fastapi import APIRouter, Query
from mock_javis_api.models import gen_sessions

router = APIRouter()

@router.get("/sessions")
async def list_sessions(
    instance_id: str = Query(...),
    status: str = Query(None),
    limit: int = Query(20)
):
    """查询会话列表"""
    sessions = gen_sessions(limit)
    if status:
        sessions = [s for s in sessions if s.status == status]
    return {"code": 0, "data": sessions, "total": len(sessions)}

@router.get("/sessions/{sid}")
async def get_session(sid: int):
    """获取单个会话"""
    sessions = gen_sessions(20)
    for s in sessions:
        if s.sid == sid:
            return {"code": 0, "data": s}
    return {"code": 404, "message": "Session not found"}
