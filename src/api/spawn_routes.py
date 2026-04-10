"""Subagent Spawn Routes - /spawn端点 (V3.2 P0)"""
import asyncio
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.subagent import (
    SubagentFactory, SubagentMode,
    ExploreSpec, ExecuteSpec, PlanSpec,
    quick_explore, quick_execute,
)
from src.subagent.hooks import SubagentModeHook
from src.api.schemas import APIResponse

router = APIRouter(prefix="/api/v1", tags=["subagent"])


class SpawnRequest(BaseModel):
    """Spawn请求"""
    task: str
    mode: str = "explore"  # explore/plan/execute
    timeout: int = 300
    session_id: str | None = None
    user_id: str | None = None


class SpawnResponse(BaseModel):
    """Spawn响应"""
    session_id: str
    config: dict
    status: str


@router.post("/spawn", response_model=SpawnResponse)
async def spawn_subagent(request: SpawnRequest):
    """
    创建Subagent任务
    
    使用示例：
    POST /api/v1/spawn
    {
        "task": "帮我查看这个项目的结构",
        "mode": "explore",
        "timeout": 300
    }
    """
    # 创建对应的Spec
    spec: SubagentSpec
    if request.mode == "explore":
        spec = quick_explore(request.task)
        spec.timeout = request.timeout
    elif request.mode == "plan":
        spec = PlanSpec(task=request.task)
        spec.timeout = request.timeout
    elif request.mode == "execute":
        spec = quick_execute(request.task)
        spec.timeout = request.timeout
    else:
        raise HTTPException(status_code=400, detail=f"无效模式: {request.mode}")
    
    # 使用SubagentFactory创建配置
    config = SubagentFactory.create(spec)
    
    # 生成session_id
    session_id = request.session_id or f"subagent-{uuid.uuid4().hex[:8]}"
    
    return SpawnResponse(
        session_id=session_id,
        config=config,
        status="created",
    )


@router.get("/subagent/modes")
async def list_subagent_modes():
    """列出所有Subagent模式"""
    return APIResponse(data={
        "modes": [
            {"name": "explore", "description": "只读探索模式", "readonly": True},
            {"name": "plan", "description": "纯规划模式（最严格只读）", "readonly": True},
            {"name": "execute", "description": "执行模式（允许写操作）", "readonly": False},
        ],
        "default_mode": "explore",
    })
