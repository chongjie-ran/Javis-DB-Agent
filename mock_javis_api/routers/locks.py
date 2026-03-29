"""锁路由"""
from fastapi import APIRouter, Query
from mock_javis_api.models import gen_locks

router = APIRouter()

@router.get("/locks")
async def list_locks(instance_id: str = Query(...)):
    """查询锁等待"""
    locks = gen_locks()
    return {"code": 0, "data": locks, "total": len(locks)}
