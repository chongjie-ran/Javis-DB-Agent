"""容量路由"""
from fastapi import APIRouter, Query
from mock_zcloud_api.models import gen_disk_usage, gen_config_deviation

router = APIRouter()

@router.get("/capacity/disk")
async def get_disk_usage(instance_id: str = Query(...)):
    """查询磁盘/表空间使用率"""
    disks = gen_disk_usage()
    total = sum(d.total_mb for d in disks)
    used = sum(d.used_mb for d in disks)
    return {
        "code": 0,
        "data": {
            "instance_id": instance_id,
            "disk_total_gb": round(total/1024, 2),
            "disk_used_gb": round(used/1024, 2),
            "disk_free_gb": round((total-used)/1024, 2),
            "disk_used_percent": round(used/total*100, 2) if total else 0,
            "tablespaces": disks
        }
    }

@router.get("/capacity/deviation")
async def get_config_deviation(instance_id: str = Query(...)):
    """查询配置偏差"""
    return {"code": 0, "data": gen_config_deviation()}
