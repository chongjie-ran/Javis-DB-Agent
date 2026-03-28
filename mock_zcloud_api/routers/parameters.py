"""参数路由"""
from fastapi import APIRouter, Query
from mock_zcloud_api.models import gen_parameters

router = APIRouter()

@router.get("/parameters")
async def list_parameters(instance_id: str = Query(...)):
    """查询实例参数"""
    return {"code": 0, "data": gen_parameters()}

@router.get("/parameters/{param_name}")
async def get_parameter(instance_id: str, param_name: str):
    """查询单个参数"""
    params = gen_parameters()
    for p in params:
        if p.name == param_name:
            return {"code": 0, "data": p}
    return {"code": 404, "message": "Parameter not found"}
