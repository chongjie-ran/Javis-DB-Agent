"""
QPS 限制模拟器
用于模拟 zCloud API 的请求频率限制
"""
import time
import threading
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum


class APIType(Enum):
    """API 类型"""
    QUERY = "query"        # 查询类 API (100 QPS)
    WRITE = "write"        # 写操作 API (20 QPS)
    BATCH = "batch"        # 批量操作 API (5 QPS)


@dataclass
class RateLimitConfig:
    """速率限制配置"""
    query_qps: float = 100.0
    write_qps: float = 20.0
    batch_qps: float = 5.0
    
    # 时间窗口配置
    window_seconds: float = 1.0
    
    # 是否启用
    enabled: bool = True


@dataclass
class RateLimitStatus:
    """限流状态"""
    allowed: bool
    api_type: APIType
    limit: float
    remaining: int
    reset_at: float
    retry_after: float = 0.0
    error_type: Optional[str] = None


class QPSLimiter:
    """QPS 限制器（滑动窗口算法）"""
    
    def __init__(
        self,
        max_qps: float = 100.0,
        window_seconds: float = 1.0
    ):
        self.max_qps = max_qps
        self.window_seconds = window_seconds
        self._requests: list[float] = []
        self._lock = threading.Lock()
    
    def _cleanup_expired(self, now: float) -> None:
        """清理过期的请求记录"""
        cutoff = now - self.window_seconds
        self._requests = [r for r in self._requests if r > cutoff]
    
    def acquire(self) -> bool:
        """
        尝试获取一个请求许可
        
        Returns:
            True: 获取成功，可以继续
            False: 被限流
        """
        with self._lock:
            now = time.time()
            self._cleanup_expired(now)
            
            if len(self._requests) >= self.max_qps:
                return False
            
            self._requests.append(now)
            return True
    
    def acquire_with_wait(self) -> float:
        """
        获取许可，如果被限流则等待
        
        Returns:
            等待的秒数
        """
        wait_time = 0.0
        with self._lock:
            now = time.time()
            self._cleanup_expired(now)
            
            if len(self._requests) >= self.max_qps:
                oldest = min(self._requests)
                wait_time = oldest + self.window_seconds - now
                if wait_time > 0:
                    # 不在锁内sleep，计算等待时间后返回
                    pass
            
            if wait_time > 0:
                # 记录请求但不等待（等待在外面做）
                pass
            else:
                self._requests.append(now)
        
        if wait_time > 0:
            time.sleep(wait_time)
            with self._lock:
                self._requests.append(time.time())
        
        return wait_time
    
    def check(self) -> tuple[bool, int, float]:
        """
        检查是否会被限流（不占用配额）
        
        Returns:
            (是否允许, 剩余请求数, 重置时间)
        """
        with self._lock:
            now = time.time()
            self._cleanup_expired(now)
            
            remaining = max(0, int(self.max_qps - len(self._requests)))
            reset_at = min(self._requests) + self.window_seconds if self._requests else now
            allowed = len(self._requests) < self.max_qps
            
            return allowed, remaining, reset_at
    
    def get_remaining(self) -> int:
        """获取剩余请求次数"""
        _, remaining, _ = self.check()
        return remaining
    
    def reset(self) -> None:
        """重置限流器"""
        with self._lock:
            self._requests.clear()


class MultiTierQPSLimiter:
    """多层级 QPS 限制器"""
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        if config is None:
            config = RateLimitConfig()
        
        self.config = config
        self.query_limiter = QPSLimiter(
            max_qps=config.query_qps,
            window_seconds=config.window_seconds
        )
        self.write_limiter = QPSLimiter(
            max_qps=config.write_qps,
            window_seconds=config.window_seconds
        )
        self.batch_limiter = QPSLimiter(
            max_qps=config.batch_qps,
            window_seconds=config.window_seconds
        )
        self._lock = threading.Lock()
    
    def _get_limiter(self, api_type: APIType) -> QPSLimiter:
        """获取对应 API 类型的限流器"""
        if api_type == APIType.QUERY:
            return self.query_limiter
        elif api_type == APIType.WRITE:
            return self.write_limiter
        else:
            return self.batch_limiter
    
    def acquire(self, api_type: APIType) -> bool:
        """尝试获取请求许可"""
        if not self.config.enabled:
            return True
        
        limiter = self._get_limiter(api_type)
        return limiter.acquire()
    
    def acquire_with_wait(self, api_type: APIType) -> RateLimitStatus:
        """获取请求许可（等待模式）"""
        if not self.config.enabled:
            return RateLimitStatus(
                allowed=True,
                api_type=api_type,
                limit=self.config.query_qps,
                remaining=999,
                reset_at=0
            )
        
        limiter = self._get_limiter(api_type)
        allowed, remaining, reset_at = limiter.check()
        
        if allowed:
            wait_time = limiter.acquire_with_wait()
            _, new_remaining, _ = limiter.check()
            return RateLimitStatus(
                allowed=True,
                api_type=api_type,
                limit=limiter.max_qps,
                remaining=new_remaining,
                reset_at=reset_at
            )
        else:
            oldest_requests = limiter._requests[:1] if limiter._requests else []
            reset_at = min(oldest_requests) + limiter.window_seconds if oldest_requests else time.time()
            retry_after = max(0, reset_at - time.time())
            
            return RateLimitStatus(
                allowed=False,
                api_type=api_type,
                limit=limiter.max_qps,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after,
                error_type=f"{api_type.value}_limit"
            )
    
    def check(self, api_type: APIType) -> RateLimitStatus:
        """检查限流状态（不占用配额）"""
        if not self.config.enabled:
            return RateLimitStatus(
                allowed=True,
                api_type=api_type,
                limit=self.config.query_qps,
                remaining=999,
                reset_at=0
            )
        
        limiter = self._get_limiter(api_type)
        allowed, remaining, reset_at = limiter.check()
        
        return RateLimitStatus(
            allowed=allowed,
            api_type=api_type,
            limit=limiter.max_qps,
            remaining=remaining,
            reset_at=reset_at
        )
    
    def reset(self) -> None:
        """重置所有限流器"""
        self.query_limiter.reset()
        self.write_limiter.reset()
        self.batch_limiter.reset()


class RateLimitError(Exception):
    """限流异常"""
    
    def __init__(
        self,
        status: RateLimitStatus,
        response_data: Optional[dict] = None
    ):
        self.status = status
        self.response_data = response_data or {}
        super().__init__(
            f"Rate limit exceeded for {status.api_type.value} API. "
            f"Retry after {status.retry_after:.2f}s"
        )


class RateLimitedClientMixin:
    """带限流功能的客户端 Mixin"""
    
    def __init__(self, qps_limiter: Optional[MultiTierQPSLimiter] = None):
        self._qps_limiter = qps_limiter or MultiTierQPSLimiter()
    
    def _check_rate_limit(self, api_type: APIType) -> None:
        """检查限流，超限则抛出异常"""
        status = self._qps_limiter.check(api_type)
        if not status.allowed:
            raise RateLimitError(status)
    
    def _acquire_rate_limit(self, api_type: APIType) -> None:
        """获取限流许可，超限则等待"""
        status = self._qps_limiter.acquire_with_wait(api_type)
        if not status.allowed:
            raise RateLimitError(status)
    
    @property
    def qps_limiter(self) -> MultiTierQPSLimiter:
        return self._qps_limiter


# 全局限流器单例
_limiter_instance: Optional[MultiTierQPSLimiter] = None
_limiter_lock = threading.Lock()


def get_qps_limiter(config: Optional[RateLimitConfig] = None) -> MultiTierQPSLimiter:
    """获取全局 QPS 限制器单例"""
    global _limiter_instance
    with _limiter_lock:
        if _limiter_instance is None:
            _limiter_instance = MultiTierQPSLimiter(config)
        return _limiter_instance


def reset_qps_limiter() -> None:
    """重置全局 QPS 限制器"""
    global _limiter_instance
    with _limiter_lock:
        if _limiter_instance:
            _limiter_instance.reset()
        _limiter_instance = None
