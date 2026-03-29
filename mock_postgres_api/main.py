"""Mock PostgreSQL API - FastAPI服务
模拟PostgreSQL的系统视图和统计信息
端口: 18081
"""
import time
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from mock_postgres_api.routes import sessions, locks, replication, bloat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    print("[PG Mock API] Starting PostgreSQL Mock API on port 18081...")
    yield
    # 关闭时清理
    print("[PG Mock API] Shutting down...")


app = FastAPI(
    title="Mock PostgreSQL API",
    description="模拟PostgreSQL系统视图和统计信息API",
    version="1.0.0",
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
app.include_router(sessions.router, prefix="/api/pg", tags=["sessions"])
app.include_router(locks.router, prefix="/api/pg", tags=["locks"])
app.include_router(replication.router, prefix="/api/pg", tags=["replication"])
app.include_router(bloat.router, prefix="/api/pg", tags=["bloat"])


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "mock_postgres_api", "port": 18081}


@app.get("/api/pg/summary")
async def pg_summary():
    """PostgreSQL总览信息"""
    return {
        "version": "14.7",
        "role": "primary",
        "uptime_seconds": 1728000,
        "current_database": "orders_db",
        "current_schemas": ["public", "pg_catalog", "information_schema"],
        "max_connections": 300,
        "active_connections": random.randint(60, 120),
        "total_sessions": random.randint(80, 150),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18081)
