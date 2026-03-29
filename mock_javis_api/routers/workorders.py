"""工单路由"""
from fastapi import APIRouter
from mock_javis_api.models import WorkOrderCreate, gen_workorder

router = APIRouter()

# 存储工单（内存）
_workorders = {}

@router.post("/workorders")
async def create_workorder(wo: WorkOrderCreate):
    """创建工单"""
    workorder = gen_workorder(wo)
    _workorders[workorder.work_order_id] = workorder
    return {"code": 0, "data": workorder}

@router.get("/workorders/{work_order_id}")
async def get_workorder(work_order_id: str):
    """获取工单详情"""
    if work_order_id in _workorders:
        return {"code": 0, "data": _workorders[work_order_id]}
    return {"code": 404, "message": "Work order not found"}
