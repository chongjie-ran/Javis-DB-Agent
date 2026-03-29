"""
API限速 - 基于IP/用户维度的限流
防止暴力破解和DDoS攻击

使用滑动窗口算法，支持:
- IP维度限速（所有请求）
- 用户维度限速（登录后）
- 敏感端点强化限速（登录/注册/refresh）
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings


# ============ 配置 ============

@dataclass
class RateLimitConfig:
    """单个限流规则的配置"""
    requests: int          # 时间窗口内最大请求数
    window_seconds: int    # 时间窗口（秒）
    block_seconds: int     # 超限后封禁时长（秒），0表示只限速不封禁


# 默认限流配置
DEFAULT_LIMITS: dict[str, RateLimitConfig] = {
    # 敏感操作 - 严格限制
    "login":      RateLimitConfig(requests=5,  window_seconds=300,  block_seconds=600),   # 5次/5分钟，封禁10分钟
    "refresh":    RateLimitConfig(requests=10, window_seconds=300,  block_seconds=300),   # 10次/5分钟
    "register":   RateLimitConfig(requests=3,  window_seconds=3600, block_seconds=3600),  # 3次/小时
    # 普通API
    "api":        RateLimitConfig(requests=60, window_seconds=60,  block_seconds=60),    # 60次/分钟
    # 聊天（高频）
    "chat":       RateLimitConfig(requests=30, window_seconds=60,  block_seconds=60),    # 30次/分钟
    # 全局限流（所有请求）
    "global_ip":  RateLimitConfig(requests=200, window_seconds=60, block_seconds=120),   # 200次/分钟
}


# ============ 异常 ============

class RateLimitExceeded(HTTPException):
    """限速超限"""
    def __init__(self, retry_after: int, message: str = "请求过于频繁，请稍后重试"):
        super().__init__(
            status_code=429,
            detail=message,
            headers={"Retry-After": str(retry_after)}
        )


# ============ 滑动窗口计数器 ============

@dataclass
class RateWindow:
    """滑动时间窗口"""
    count: int = 0
    window_start: float = field(default_factory=time.time)


class RateLimitStore:
    """
    内存存储的限流计数器
    
    使用滑动窗口算法：
    - 当请求到达时，计算当前时间窗口的起始点
    - 如果起始点变化，重置计数器
    - 如果计数器超过限制，返回超限
    """

    def __init__(self):
        # key: "limiter_type:identifier" -> RateWindow
        self._windows: dict[str, RateWindow] = defaultdict(RateWindow)
        # key: "block:identifier" -> unblock_timestamp
        self._blocks: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def _make_key(self, limiter_type: str, identifier: str) -> str:
        return f"{limiter_type}:{identifier}"

    def _is_blocked(self, key: str) -> tuple[bool, int]:
        """检查是否被封禁，返回 (是否封禁, 剩余秒数)"""
        if key not in self._blocks:
            return False, 0
        unblock_at = self._blocks[key]
        remaining = int(unblock_at - time.time())
        if remaining <= 0:
            del self._blocks[key]
            return False, 0
        return True, remaining

    def check_and_increment(
        self,
        limiter_type: str,
        identifier: str,
        config: RateLimitConfig,
    ) -> tuple[bool, int]:
        """
        检查并增加计数
        
        Returns:
            (是否允许, retry_after秒数) - 如果被限速，retry_after > 0
        """
        with self._lock:
            key = self._make_key(limiter_type, identifier)

            # 检查封禁
            blocked, remaining = self._is_blocked(key)
            if blocked:
                return False, remaining

            now = time.time()
            window = self._windows[key]

            # 判断是否在同一个时间窗口内
            if now - window.window_start >= config.window_seconds:
                # 新窗口
                window.count = 1
                window.window_start = now
            else:
                window.count += 1

            if window.count > config.requests:
                # 超限！计算重试时间
                elapsed_in_window = now - window.window_start
                retry_after = int(config.window_seconds - elapsed_in_window) + 1
                retry_after = max(retry_after, 1)

                if config.block_seconds > 0:
                    # 触发封禁
                    self._blocks[key] = now + config.block_seconds

                return False, retry_after

            return True, 0

    def clear_expired(self):
        """清理过期数据（防止内存泄漏）"""
        now = time.time()
        expired_keys = [
            k for k, w in self._windows.items()
            if now - w.window_start > w.window_seconds + 60
            for _ in [self._windows[k]]  # just to reference
        ]
        for k in list(self._windows.keys()):
            if now - self._windows[k].window_start > 3600:
                del self._windows[k]
        for k in list(self._blocks.keys()):
            if self._blocks[k] < now:
                del self._blocks[k]


# 全局存储实例
_rate_store: Optional[RateLimitStore] = None


def get_rate_store() -> RateLimitStore:
    global _rate_store
    if _rate_store is None:
        _rate_store = RateLimitStore()
    return _rate_store


# ============ IP提取工具 ============

def extract_client_ip(request: Request) -> str:
    """
    从请求中提取真实客户端IP
    
    优先从 X-Forwarded-For（反向代理场景）获取，
    其次从 X-Real-IP，最后从 request.client.host
    """
    # 优先 X-Forwarded-For（第一个IP是原始客户端）
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # "client_ip, proxy1, proxy2, ..."
        first_ip = forwarded.split(",")[0].strip()
        if first_ip:
            return first_ip

    # X-Real-IP（nginx）
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()

    # 直接连接
    if request.client:
        return request.client.host

    return "unknown"


# ============ FastAPI 依赖 ============

_rate_limits_config: dict[str, RateLimitConfig] = {}


def configure_rate_limits(limits: dict[str, RateLimitConfig]):
    """配置限流规则（在应用启动时调用）"""
    global _rate_limits_config
    _rate_limits_config = {**DEFAULT_LIMITS, **limits}


def get_rate_limit_config(action: str) -> RateLimitConfig:
    return _rate_limits_config.get(action, DEFAULT_LIMITS.get("api", RateLimitConfig(requests=60, window_seconds=60, block_seconds=60)))


class RateLimitDependency:
    """
    FastAPI 依赖：限流检查
    
    用法:
        @router.post("/login")
        async def login(request: LoginRequest, _: None = Depends(RateLimitDependency("login"))):
            ...
    """

    def __init__(self, action: str, use_user_id: bool = False):
        self.action = action
        self.use_user_id = use_user_id

    def __call__(self, request: Request) -> None:
        store = get_rate_store()
        config = get_rate_limit_config(self.action)

        # 确定限流标识符
        ip = extract_client_ip(request)
        identifier = ip

        # 尝试从已验证的token中提取user_id（更精确的限流）
        if self.use_user_id:
            user_id = self._extract_user_id(request)
            if user_id:
                identifier = f"user:{user_id}"
            else:
                identifier = f"ip:{ip}"

        allowed, retry_after = store.check_and_increment(
            limiter_type=self.action,
            identifier=identifier,
            config=config,
        )

        if not allowed:
            raise RateLimitExceeded(
                retry_after=retry_after,
                message=f"{self.action} 请求过于频繁，请 {retry_after} 秒后重试"
            )

    def _extract_user_id(self, request: Request) -> Optional[str]:
        """从Authorization header尝试提取已验证的user_id（不验证签名，只提取）"""
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
            # 简单JWT解码（不验证签名，仅提取sub）
            try:
                import base64
                import json
                parts = token.split(".")
                if len(parts) == 3:
                    payload_b64 = parts[1]
                    # 补全 padding
                    padding = 4 - len(payload_b64) % 4
                    if padding != 4:
                        payload_b64 += "=" * padding
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                    return payload.get("sub")
            except Exception:
                pass
        return None


# 便捷依赖实例
def rate_limit(action: str, use_user_id: bool = False) -> RateLimitDependency:
    return RateLimitDependency(action, use_user_id)


# ============ 全局中间件 ============

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    全局IP限速中间件
    
    对所有请求进行IP级别的限速，防止DDoS
    """

    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查和指标端点
        path = request.url.path
        if path in ("/api/v1/health", "/api/v1/metrics", "/api/v1/metrics/summary",
                    "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        store = get_rate_store()
        config = get_rate_limit_config("global_ip")
        ip = extract_client_ip(request)

        allowed, retry_after = store.check_and_increment(
            limiter_type="global",
            identifier=f"ip:{ip}",
            config=config,
        )

        if not allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"detail": f"请求过于频繁，请 {retry_after} 秒后重试", "code": 429},
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        return response


# ============ 工具函数 ============

def get_rate_limit_status(action: str, identifier: str) -> dict:
    """查询当前限流状态（用于调试/监控）"""
    store = get_rate_store()
    config = get_rate_limit_config(action)
    key = store._make_key(action, identifier)

    blocked, remaining = store._is_blocked(f"block:{action}:{identifier}")
    window = store._windows.get(key)

    return {
        "action": action,
        "identifier": identifier,
        "blocked": blocked,
        "block_remaining_seconds": remaining if blocked else 0,
        "current_count": window.count if window else 0,
        "limit": config.requests,
        "window_seconds": config.window_seconds,
    }
