"""巡检路由"""
from fastapi import APIRouter, Path, Query
from mock_zcloud_api.models import gen_inspection_result
import time

router = APIRouter()

# 存储巡检任务状态（内存）
_inspection_tasks = {}

@router.post("/inspection")
async def trigger_inspection(
    instance_id: str = Query(...),
    inspection_type: str = Query("quick")
):
    """触发巡检"""
    task_id = f"INS-{int(time.time())}"
    _inspection_tasks[task_id] = {
        "task_id": task_id,
        "instance_id": instance_id,
        "inspection_type": inspection_type,
        "status": "pending",
        "started_at": time.time()
    }
    return {"code": 0, "data": _inspection_tasks[task_id]}

@router.get("/inspection/{task_id}")
async def get_inspection_result(task_id: str = Path(...)):
    """获取巡检结果"""
    if task_id in _inspection_tasks:
        result = gen_inspection_result(task_id)
        result.status = "completed"
        _inspection_tasks[task_id]["status"] = "completed"
        return {"code": 0, "data": result}
    raise {"code": 404, "message": "Task not found"}
