"""SQL 监控路由 - 增强版"""
import time
import random
from typing import Optional

from fastapi import APIRouter, Path, Query
from mock_javis_api.models_enhanced import (
    gen_enhanced_slow_sqls,
    gen_sql_plan
)

router = APIRouter()


@router.get("/sqls/slow")
async def get_slow_sqls(
    instance_id: str = Query(..., description="实例ID"),
    limit: int = Query(10, ge=1, le=50),
    order_by: str = Query("elapsed_time", description="排序字段")
):
    """获取慢SQL列表"""
    slow_sqls = gen_enhanced_slow_sqls(limit=limit)
    
    # 排序
    if order_by == "elapsed_time":
        slow_sqls.sort(key=lambda x: x.elapsed_time_sec, reverse=True)
    elif order_by == "executions":
        slow_sqls.sort(key=lambda x: x.executions, reverse=True)
    elif order_by == "disk_reads":
        slow_sqls.sort(key=lambda x: x.disk_reads, reverse=True)
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "instance_id": instance_id,
            "slow_sqls": [sql.model_dump() for sql in slow_sqls],
            "count": len(slow_sqls),
            "order_by": order_by
        },
        "timestamp": time.time()
    }


@router.get("/sqls/{sql_id}/plan")
async def get_sql_plan(
    sql_id: str = Path(..., description="SQL ID"),
    instance_id: Optional[str] = Query(None, description="实例ID")
):
    """获取SQL执行计划"""
    plan = gen_sql_plan(sql_id)
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "sql_id": sql_id,
            "instance_id": instance_id,
            "plan": [step.model_dump() for step in plan],
            "estimated_cost": sum(step.cost for step in plan),
            "estimated_rows": sum(step.cardinality for step in plan)
        },
        "timestamp": time.time()
    }


@router.get("/sqls/top")
async def get_top_sqls(
    instance_id: str = Query(..., description="实例ID"),
    sort_type: str = Query("cpu", description="排序类型: cpu/buffer_gets/disk_reads"),
    limit: int = Query(10, ge=1, le=50)
):
    """获取TOP SQL"""
    sqls = gen_enhanced_slow_sqls(limit=limit)
    
    # 按指定类型排序
    if sort_type == "cpu":
        sqls.sort(key=lambda x: x.elapsed_time_sec * x.executions, reverse=True)
    elif sort_type == "buffer_gets":
        sqls.sort(key=lambda x: x.buffer_gets, reverse=True)
    elif sort_type == "disk_reads":
        sqls.sort(key=lambda x: x.disk_reads, reverse=True)
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "instance_id": instance_id,
            "sqls": [sql.model_dump() for sql in sqls],
            "count": len(sqls),
            "sort_type": sort_type
        },
        "timestamp": time.time()
    }


@router.get("/sqls/{sql_id}/history")
async def get_sql_history(
    sql_id: str = Path(..., description="SQL ID"),
    instance_id: Optional[str] = Query(None, description="实例ID"),
    start_time: Optional[float] = Query(None, description="开始时间"),
    end_time: Optional[float] = Query(None, description="结束时间"),
    limit: int = Query(20, ge=1, le=100)
):
    """获取SQL历史执行记录"""
    now = time.time()
    if not end_time:
        end_time = now
    if not start_time:
        start_time = now - 86400  # 默认1天
    
    # 生成历史记录
    history = []
    for i in range(min(limit, 20)):
        exec_time = random.uniform(0.1, 30.0)
        history.append({
            "execution_time": end_time - (i * (end_time - start_time) / limit),
            "elapsed_sec": round(exec_time, 3),
            "buffer_gets": random.randint(100, 100000),
            "disk_reads": random.randint(10, 50000),
            "rows_processed": random.randint(1, 10000),
            "status": "completed",
            "error": None
        })
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "sql_id": sql_id,
            "instance_id": instance_id,
            "history": history,
            "count": len(history),
            "start_time": start_time,
            "end_time": end_time
        },
        "timestamp": now
    }
