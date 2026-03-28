"""API路由"""
from fastapi import APIRouter, HTTPException, Depends
from src.api.schemas import (
    ChatRequest, ChatResponse,
    DiagnoseRequest, DiagnoseResponse,
    SQLAnalyzeRequest, APIResponse,
    InspectRequest,
    ReportRequest,
    HealthResponse,
)
from src.agents.orchestrator import OrchestratorAgent
from src.gateway.session import get_session_manager
from src.gateway.tool_registry import get_tool_registry
from src.llm.ollama_client import get_ollama_client
import time

router = APIRouter(prefix="/api/v1")

# 全局Agent实例
_orchestrator: OrchestratorAgent = None


def get_orchestrator() -> OrchestratorAgent:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = OrchestratorAgent()
    return _orchestrator


# ============ 对话接口 ============

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """对话交互"""
    orch = get_orchestrator()
    session_mgr = get_session_manager()
    
    # 获取或创建会话
    if request.session_id:
        session = session_mgr.get_session(request.session_id)
    else:
        session = session_mgr.create_session(request.user_id)
    
    if not session:
        session = session_mgr.create_session(request.user_id)
    
    # 构建上下文
    context = {
        "session_id": session.session_id,
        "user_id": request.user_id,
        "extra_info": str(request.context),
    }
    
    # 处理对话
    response = await orch.handle_chat(request.message, context)
    
    # 记录到会话
    session.add_message("user", request.message)
    session.add_message("assistant", response.content)
    
    return ChatResponse(
        session_id=session.session_id,
        reply=response.content,
        agent=response.metadata.get("agent", "orchestrator"),
        metadata=response.metadata,
    )


# ============ 诊断接口 ============

@router.post("/diagnose", response_model=DiagnoseResponse)
async def diagnose(request: DiagnoseRequest):
    """告警诊断"""
    orch = get_orchestrator()
    
    context = {
        "user_id": "system",
        "extra_info": str(request.context),
        "instance_id": request.instance_id or "",
    }
    
    response = await orch.handle_diagnose(request.alert_id, context)
    
    return DiagnoseResponse(
        data={
            "diagnosis": response.content,
            "metadata": response.metadata,
        }
    )


# ============ SQL分析接口 ============

@router.post("/analyze/sql", response_model=APIResponse)
async def analyze_sql(request: SQLAnalyzeRequest):
    """SQL分析"""
    from src.agents.sql_analyzer import SQLAnalyzerAgent
    
    agent = SQLAnalyzerAgent()
    context = {
        "user_id": "system",
        "instance_id": request.instance_id or "",
        "sql": request.sql or "",
    }
    
    if request.sql:
        response = await agent.analyze_sql(request.sql, context)
    elif request.session_id:
        response = await agent.analyze_session(request.session_id, context)
    else:
        raise HTTPException(status_code=400, detail="需要提供sql或session_id")
    
    return APIResponse(data={"analysis": response.content, "metadata": response.metadata})


# ============ 巡检接口 ============

@router.post("/inspect", response_model=APIResponse)
async def inspect(request: InspectRequest):
    """执行巡检"""
    from src.agents.inspector import InspectorAgent
    
    agent = InspectorAgent()
    results = []
    
    for instance_id in request.instance_ids:
        context = {"user_id": "system", "instance_id": instance_id}
        response = await agent.inspect_instance(instance_id, context)
        results.append({
            "instance_id": instance_id,
            "result": response.content,
        })
    
    return APIResponse(data={"results": results})


# ============ 报告生成接口 ============

@router.post("/report", response_model=APIResponse)
async def generate_report(request: ReportRequest):
    """生成报告"""
    from src.agents.reporter import ReporterAgent
    
    agent = ReporterAgent()
    context = {
        "user_id": "system",
        "report_type": request.report_type,
        "report_data": request.data,
        "instance_id": request.instance_id or "",
    }
    
    if request.report_type == "rca" and request.incident_id:
        response = await agent.generate_rca(request.incident_id, context)
    elif request.report_type == "inspection" and request.instance_id:
        response = await agent.generate_inspection_report(request.instance_id, context)
    else:
        response = await agent.generate_summary(request.data, context)
    
    return APIResponse(data={"report": response.content, "metadata": response.metadata})


# ============ 工具管理接口 ============

@router.get("/tools", response_model=APIResponse)
async def list_tools(category: str = None):
    """列出可用工具"""
    registry = get_tool_registry()
    tools = registry.list_tools(enabled_only=True, category=category)
    return APIResponse(data={"tools": tools, "stats": registry.get_stats()})


@router.get("/tools/{tool_name}")
async def get_tool(tool_name: str):
    """获取工具详情"""
    registry = get_tool_registry()
    tool = registry.get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")
    return APIResponse(data=tool.definition_dict)


# ============ 健康检查 ============

@router.get("/health", response_model=HealthResponse)
async def health():
    """健康检查"""
    from src.config import get_settings
    settings = get_settings()
    
    ollama = get_ollama_client()
    ollama_ok = await ollama.health_check()
    
    return HealthResponse(
        status="healthy" if ollama_ok else "degraded",
        version=settings.app_version,
        ollama_status="connected" if ollama_ok else "disconnected",
        timestamp=time.time(),
    )
