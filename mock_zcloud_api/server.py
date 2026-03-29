"""
zCloud Mock API Server - FastAPI Application (增强版)
支持 QPS 限制和增强的数据格式
"""
import time
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mock_zcloud_api.routers import (
    instances, alerts, sessions, locks, sqls,
    replication, parameters, capacity, inspection, workorders
)
from src.mock_api.qps_limiter import (
    get_qps_limiter, RateLimitConfig, APIType, RateLimitError
)

app = FastAPI(
    title="zCloud Mock API",
    description="zCloud数据库运维智能体Mock API，用于本地开发和测试（增强版）",
    version="v1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# QPS 限制器
qps_limiter = get_qps_limiter(
    RateLimitConfig(
        query_qps=100.0,
        write_qps=20.0,
        batch_qps=5.0,
        enabled=True
    )
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """QPS 限制中间件"""
    # 只对 /api/v1/* 路径进行限流
    if request.url.path.startswith("/api/v1/"):
        # 根据请求方法判断 API 类型
        method = request.method
        if method in ["GET", "HEAD", "OPTIONS"]:
            api_type = APIType.QUERY
        elif method in ["POST", "PUT", "PATCH"]:
            # 写操作 API
            if "batch" in request.url.path or "bulk" in request.url.path:
                api_type = APIType.BATCH
            else:
                api_type = APIType.WRITE
        else:
            api_type = APIType.QUERY
        
        status = qps_limiter.check(api_type)
        if not status.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "code": 42901,
                    "message": "Rate limit exceeded",
                    "error": {
                        "code": 42901,
                        "message": f"Too many {api_type.value} requests",
                        "retry_after": round(status.retry_after, 2),
                        "limit": int(status.limit),
                        "remaining": status.remaining
                    },
                    "request_id": f"req_{int(time.time() * 1000)}",
                    "timestamp": time.time()
                },
                headers={
                    "X-RateLimit-Limit": str(int(status.limit)),
                    "X-RateLimit-Remaining": str(status.remaining),
                    "X-RateLimit-Reset": str(int(status.reset_at)),
                    "Retry-After": str(int(status.retry_after) + 1)
                }
            )
        
        # 获取许可
        qps_limiter.acquire_with_wait(api_type)
    
    response = await call_next(request)
    return response


# 注册路由
app.include_router(instances.router, prefix="/api/v1", tags=["实例"])
app.include_router(alerts.router, prefix="/api/v1", tags=["告警"])
app.include_router(sessions.router, prefix="/api/v1", tags=["会话"])
app.include_router(locks.router, prefix="/api/v1", tags=["锁"])
app.include_router(sqls.router, prefix="/api/v1", tags=["SQL"])
app.include_router(replication.router, prefix="/api/v1", tags=["复制"])
app.include_router(parameters.router, prefix="/api/v1", tags=["参数"])
app.include_router(capacity.router, prefix="/api/v1", tags=["容量"])
app.include_router(inspection.router, prefix="/api/v1", tags=["巡检"])
app.include_router(workorders.router, prefix="/api/v1", tags=["工单"])


@app.get("/")
async def root():
    return {
        "service": "zCloud Mock API",
        "version": "v1.1.0",
        "status": "running",
        "features": [
            "enhanced_data_format",
            "qps_limiting",
            "custom_fields",
            "annotations"
        ]
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/api/v1/slow")
async def slow_endpoint():
    """慢响应端点，模拟超时场景（延迟5秒）"""
    import asyncio
    await asyncio.sleep(5)
    return {"status": "ok", "message": "慢响应完成"}


@app.get("/api/v1/qps-status")
async def qps_status():
    """获取 QPS 限制状态"""
    query_status = qps_limiter.check(APIType.QUERY)
    write_status = qps_limiter.check(APIType.WRITE)
    batch_status = qps_limiter.check(APIType.BATCH)
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "query": {
                "limit": int(query_status.limit),
                "remaining": query_status.remaining,
                "reset_at": query_status.reset_at
            },
            "write": {
                "limit": int(write_status.limit),
                "remaining": write_status.remaining,
                "reset_at": write_status.reset_at
            },
            "batch": {
                "limit": int(batch_status.limit),
                "remaining": batch_status.remaining,
                "reset_at": batch_status.reset_at
            }
        },
        "timestamp": time.time()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18080)
