"""复制路由"""
from fastapi import APIRouter, Query
from mock_zcloud_api.models import gen_replication

router = APIRouter()

@router.get("/replication")
async def get_replication(instance_id: str = Query(...)):
    """获取主从复制状态"""
    return {"code": 0, "data": gen_replication()}
