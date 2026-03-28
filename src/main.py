"""应用入口"""
import time
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.config import get_settings
from src.api.routes import router
from src.gateway.session import get_session_manager
from src.gateway.tool_registry import get_tool_registry
from src.gateway.policy_engine import get_policy_engine
from src.gateway.audit import get_audit_logger
from src.tools.query_tools import register_query_tools
from src.tools.analysis_tools import register_analysis_tools
from src.tools.action_tools import register_action_tools

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
    policy = get_policy_engine()
    audit = get_audit_logger()
    
    # 注册工具
    register_query_tools(registry)
    register_analysis_tools(registry)
    register_action_tools(registry)
    
    logger.info("app.started", 
                tools_count=len(registry.list_tools(enabled_only=True)),
                categories=["query", "analysis", "action"])
    
    yield
    
    # 关闭
    logger.info("app.shutdown")
    audit.export(time.time() - 86400, time.time(), "data/audit_export.jsonl")


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="zCloud数据库运维智能体系统",
        lifespan=lifespan,
    )
    
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
