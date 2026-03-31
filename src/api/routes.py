"""API路由"""
from fastapi import APIRouter, HTTPException, Response, Depends, Request
from src.security.rate_limit import rate_limit
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
from src.api.metrics import get_metrics
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

@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit("chat"))])
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
    """
    详细健康检查
    
    检查项:
    - Ollama LLM连接状态
    - 会话数据库状态
    - 审计数据库状态
    - 工具注册状态
    - 磁盘空间
    - 内存使用
    """
    from src.config import get_settings
    settings = get_settings()
    
    ollama = get_ollama_client()
    ollama_ok = await ollama.health_check()
    
    # 检查会话数据库
    session_ok = True
    session_msg = "ok"
    try:
        session_mgr = get_session_manager()
        stats = session_mgr.get_stats()
        session_msg = f"sessions={stats['total_sessions']}"
    except Exception as e:
        session_ok = False
        session_msg = f"error: {e}"
    
    # 检查审计数据库
    audit_ok = True
    audit_msg = "ok"
    try:
        audit = get_audit_logger()
        audit_stats = audit.get_stats()
        audit_msg = f"records={audit_stats['total_records']}, chain_valid={audit_stats['chain_valid']}"
    except Exception as e:
        audit_ok = False
        audit_msg = f"error: {e}"
    
    # 检查工具注册
    registry = get_tool_registry()
    tools_count = len(registry.list_tools(enabled_only=True))
    
    # 检查磁盘空间
    disk_ok = True
    disk_usage = 0
    try:
        import psutil as _psutil
        usage = _psutil.disk_usage("/")
        disk_usage = usage.percent
        disk_ok = disk_usage < 90
    except Exception:
        disk_usage = 0
    
    # 检查内存
    mem_ok = True
    mem_percent = 0
    try:
        import psutil as _psutil
        mem = _psutil.virtual_memory()
        mem_percent = mem.percent
        mem_ok = mem_percent < 90
    except Exception:
        mem_percent = 0
    
    # 综合状态
    all_ok = ollama_ok and session_ok and audit_ok and disk_ok and mem_ok
    status = "healthy" if all_ok else ("degraded" if (ollama_ok and session_ok) else "unhealthy")
    
    return HealthResponse(
        status=status,
        version=settings.app_version,
        ollama_status="connected" if ollama_ok else "disconnected",
        timestamp=time.time(),
        metadata={
            "session_db": session_msg,
            "audit_db": audit_msg,
            "tools_registered": tools_count,
            "disk_usage_percent": disk_usage,
            "memory_usage_percent": mem_percent,
            "checks": {
                "ollama": ollama_ok,
                "session_db": session_ok,
                "audit_db": audit_ok,
                "disk": disk_ok,
                "memory": mem_ok,
            }
        },
    )


# ============ Prometheus指标 ============

@router.get("/metrics")
async def metrics(request: Request):
    """
    Prometheus格式指标端点
    
    返回:
    - http_requests_total: HTTP请求总量
    - http_requests_total_by_status: 按状态分类的请求数
    - http_requests_error_rate_percent: 错误率
    - http_request_duration_seconds: 请求延迟分布
    - http_requests_active: 当前活跃请求数
    - sessions_active: 活跃会话数
    - ollama_connected: Ollama连接状态
    - audit_records_total: 审计记录总数
    - policy_version: 策略版本
    - policy_changes_total: 策略变更次数
    - approvals_pending: 待审批数量
    """
    m = get_metrics()
    # 定期同步会话数
    try:
        session_mgr = get_session_manager()
        m.set_session_count(session_mgr.get_stats()["total_sessions"])
    except Exception:
        pass
    # 同步待审批数
    try:
        gate = request.app.state.approval_gate
        pending = gate.list_pending()
        m.set_approvals_pending(len(pending))
    except Exception:
        pass
    # 同步策略版本
    try:
        from src.gateway.policy_engine import get_policy_engine
        pe = get_policy_engine()
        m.set_policy_version(pe.get_version())
    except Exception:
        pass
    
    return Response(
        content=m.render_prometheus(),
        media_type="text/plain; charset=utf-8",
    )


@router.get("/metrics/summary")
async def metrics_summary(request: Request):
    """指标摘要（JSON格式）"""
    m = get_metrics()
    try:
        session_mgr = get_session_manager()
        m.set_session_count(session_mgr.get_stats()["total_sessions"])
    except Exception:
        pass
    try:
        gate = request.app.state.approval_gate
        pending = gate.list_pending()
        m.set_approvals_pending(len(pending))
    except Exception:
        pass
    try:
        from src.gateway.policy_engine import get_policy_engine
        pe = get_policy_engine()
        m.set_policy_version(pe.get_version())
    except Exception:
        pass

    return APIResponse(data=m.get_summary())


# ============ 策略版本管理 ============

@router.get("/policies/version")
async def get_policy_version():
    """获取当前策略版本"""
    from src.gateway.policy_engine import get_policy_engine
    pe = get_policy_engine()
    return APIResponse(data={
        "version": pe.get_version(),
        "history": pe.get_version_history(),
    })


@router.post("/policies/config")
async def update_policy_config(l4_required: bool = True, l5_dual_required: bool = True):
    """
    更新策略配置
    
    配置变更会自动记录到审计日志并增加版本号
    """
    from src.gateway.policy_engine import get_policy_engine
    from src.gateway.audit import get_audit_logger, AuditAction
    pe = get_policy_engine()
    
    old_l4 = pe._require_approval_l4
    old_l5 = pe._require_dual_approval_l5
    
    pe.set_approval_config(l4=l4_required, l5=l5_dual_required)
    
    # 记录到审计日志
    audit = get_audit_logger()
    audit.log_action(
        action=AuditAction.POLICY_CHANGE,
        user_id="system",
        metadata={
            "l4_required": {"old": old_l4, "new": l4_required},
            "l5_dual_required": {"old": old_l5, "new": l5_dual_required},
            "new_version": pe.get_version(),
        }
    )
    
    return APIResponse(data={
        "version": pe.get_version(),
        "l4_required": l4_required,
        "l5_dual_required": l5_dual_required,
        "message": "策略配置已更新",
    })


# ============ 多节点部署验证 ============

@router.get("/cluster/health")
async def cluster_health():
    """
    多节点集群健康检查
    
    检查Redis连接、会话同步、审批状态同步、审计链完整性
    """
    from src.gateway.distributed import check_multi_node_health
    return APIResponse(data=check_multi_node_health())


@router.get("/cluster/sessions/verify")
async def verify_sessions():
    """
    验证会话在多实例间的一致性
    
    Returns:
        - redis_available: Redis是否可用
        - session_count_local: 本地会话数
        - session_count_redis: Redis会话数
        - missing_in_redis: 本地有但Redis没有的会话
        - missing_in_local: Redis有但本地没有的会话
        - consistent: 是否一致
    """
    from src.gateway.distributed import DistributedSessionManager
    mgr = DistributedSessionManager()
    return APIResponse(data=mgr.verify_consistency())


@router.get("/cluster/approvals/verify")
async def verify_approvals():
    """
    验证审批状态在多实例间的一致性
    """
    from src.gateway.distributed import DistributedApprovalManager
    mgr = DistributedApprovalManager()
    return APIResponse(data=mgr.verify_consistency())
