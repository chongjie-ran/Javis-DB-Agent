"""应用入口"""
import time
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.config import get_settings
from src.security.tls import TLSConfig, TLSMiddleware
from src.security.rate_limit import RateLimitMiddleware, configure_rate_limits
from src.api.routes import router
from src.api.dashboard import router as dashboard_router
from src.api.auth_routes import router as auth_router
from src.api.monitoring_routes import router as monitoring_router
from src.api.audit_routes import router as audit_router
from src.api.chat_stream import router as chat_stream_router
from src.api.wecom_routes import router as wecom_router
from src.real_api.routers.knowledge import router as knowledge_router
from src.api.dependency_routes import router as dependency_router, init_dependency_routes
from src.api.knowledge_routes.evolution_routes import router as evolution_router
from src.api.approval_routes import router as approval_router
from src.api.spawn_routes import router as spawn_router
from src.api.discovery_api import router as discovery_router
from src.api.metrics import setup_metrics_middleware, get_metrics
from src.gateway.session import get_session_manager
from src.gateway.tool_registry import get_tool_registry
from src.gateway.policy_engine import get_policy_engine
from src.gateway.audit import get_audit_logger
from src.gateway.approval import ApprovalGate
from src.tools.query_tools import register_query_tools
from src.tools.analysis_tools import register_analysis_tools
from src.tools.action_tools import register_action_tools
from src.tools.backup_tools import register_backup_tools
from src.tools.performance_tools import register_performance_tools
from src.tools.subagent_tool import SubagentTool
from src.mcp import get_mcp_server
from src.hooks import get_composite_hook, AgentHook
from src.hooks.auto_verification_hook import AutoVerificationHook
from src.hooks.auto_memory_hook import AutoMemoryHook
from src.hooks.self_justification_guard import SelfJustificationGuard


# 配置日志
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    settings = get_settings()
    logger.info("app.starting", app_name=settings.app_name, version=settings.app_version)

    # 初始化组件
    session_mgr = get_session_manager()
    registry = get_tool_registry()
    # 初始化Hook注册表 (V3.2 P0)
    hook_registry = get_composite_hook()
    hook_registry.register(AutoVerificationHook())    # priority=50
    hook_registry.register(AutoMemoryHook())          # priority=50
    hook_registry.register(SelfJustificationGuard()) # priority=50
    logger.info("hooks.registered", count=len(hook_registry.list_hooks()))
    policy = get_policy_engine()
    audit = get_audit_logger()

    # 注册工具
    register_query_tools(registry)
    register_analysis_tools(registry)
    register_action_tools(registry)
    register_backup_tools(registry)
    register_performance_tools(registry)
    registry.register(SubagentTool())
    logger.info("subagent_tool.registered")
    # MCP Server初始化 (V3.2 P1)
    mcp_server = get_mcp_server()
    mcp_server.sync_from_registry(registry)
    logger.info("mcp_server.initialized", tools=len(mcp_server.get_tool_schemas()))

    # 更新指标初始状态
    metrics = get_metrics()
    stats = session_mgr.get_stats()
    metrics.set_session_count(stats["total_sessions"])

    try:
        pending = approval_gate.list_pending()
        metrics.set_approvals_pending(len(pending))
    except Exception:
        pass

    logger.info("app.started",
                tools_count=len(registry.list_tools(enabled_only=True)),
                categories=["query", "analysis", "action"])

    # 初始化依赖传播引擎 (Round 19)
    try:
        await init_dependency_routes()
        logger.info("dependency_routes.initialized")
    except Exception as e:
        logger.warning("dependency_routes.init_failed", error=str(e))

    yield

    # 关闭
    logger.info("app.shutdown")
    audit.export(time.time() - 86400, time.time(), "data/audit_export.jsonl")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    settings = get_settings()

    # 配置限速规则
    configure_rate_limits({})

    # 创建V2.1 ApprovalGate（lifespan中会用到，需提前创建）
    approval_gate = ApprovalGate(timeout_seconds=300)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Javis-DB-Agent数据库运维智能体系统",
        lifespan=lifespan,
    )

    # 安全中间件 - TLS/HTTPS
    tls_config = TLSConfig.from_env()
    if tls_config.enabled:
        app.add_middleware(TLSMiddleware, config=tls_config)

    # 全局限速中间件（IP维度，防止DDoS）
    app.add_middleware(RateLimitMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(router)
    app.include_router(dashboard_router)
    app.include_router(auth_router)
    app.include_router(monitoring_router)
    app.include_router(audit_router)
    app.include_router(chat_stream_router)
    app.include_router(wecom_router)
    app.include_router(knowledge_router)
    app.include_router(dependency_router)
    app.include_router(evolution_router)
    app.include_router(approval_router)
    app.include_router(discovery_router)
    app.include_router(spawn_router)
    app.state.approval_gate = approval_gate

    # 设置指标中间件
    setup_metrics_middleware(app)

    return app


# 创建应用实例
app = create_app()


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
