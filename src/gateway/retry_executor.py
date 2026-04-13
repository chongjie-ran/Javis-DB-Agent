"""应用层重试执行器，支持指数退避和熔断器

V3.3 P0 - 错误恢复机制核心组件
参考: openclaw/docs/concepts/retry.md
"""
import asyncio
import random
import time
import threading
import functools
from typing import Callable, Any, TypeVar, Coroutine, Type, Tuple, Optional

T = TypeVar("T")


class CircuitBreakerError(Exception):
    """熔断器打开时抛出的异常"""
    pass


class RetryExhaustedError(Exception):
    """重试次数耗尽时抛出的异常"""
    def __init__(self, attempts: int, last_error: Exception):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"Retry exhausted after {attempts} attempts: {last_error}")


class RetryExecutor:
    """应用层重试执行器，支持指数退避和熔断器"""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: float = 60.0,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_timeout = circuit_breaker_timeout
        self.retryable_exceptions = retryable_exceptions
        
        # 熔断器状态
        self._circuit_state = "closed"  # closed | open | half_open
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._circuit_lock = threading.Lock()
    
    def _get_delay(self, attempt: int) -> float:
        """计算指数退避延迟"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            # ±10% 随机抖动
            jitter_range = delay * 0.1
            delay = delay + random.uniform(-jitter_range, jitter_range)
        return max(0, delay)
    
    def _check_circuit(self) -> None:
        """检查熔断器状态"""
        with self._circuit_lock:
            if self._circuit_state == "open":
                if self._last_failure_time is not None:
                    elapsed = time.monotonic() - self._last_failure_time
                    if elapsed >= self.circuit_breaker_timeout:
                        self._circuit_state = "half_open"
                        self._failure_count = 0
                        return
                raise CircuitBreakerError("Circuit breaker is OPEN, request blocked")
            elif self._circuit_state == "half_open":
                # half_open状态下只允许一个请求探测
                if self._failure_count > 0:
                    raise CircuitBreakerError("Circuit breaker is HALF_OPEN, probing...")
    
    def _record_success(self) -> None:
        """记录成功，关闭熔断器"""
        with self._circuit_lock:
            self._failure_count = 0
            self._circuit_state = "closed"
    
    def _record_failure(self) -> None:
        """记录失败，可能打开熔断器"""
        with self._circuit_lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._circuit_state == "half_open":
                self._circuit_state = "open"
            elif self._failure_count >= self.circuit_breaker_threshold:
                self._circuit_state = "open"
    
    def get_circuit_state(self) -> str:
        """返回熔断器状态: 'closed' | 'open' | 'half_open'"""
        with self._circuit_lock:
            # 检查超时后自动转换
            if self._circuit_state == "open" and self._last_failure_time is not None:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.circuit_breaker_timeout:
                    return "half_open"
            return self._circuit_state
    
    async def execute(self, func: Callable[..., Coroutine[Any, Any, T]], *args, **kwargs) -> T:
        """异步执行函数，自动重试+熔断保护"""
        self._check_circuit()
        
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                self._record_success()
                return result
            except self.retryable_exceptions as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._get_delay(attempt)
                    await asyncio.sleep(delay)
                else:
                    self._record_failure()
                    raise RetryExhaustedError(self.max_retries + 1, last_error) from last_error
        
        # 不应该到达这里
        raise RetryExhaustedError(self.max_retries + 1, last_error or Exception("Unknown error"))
    
    def execute_sync(self, func: Callable[..., T], *args, **kwargs) -> T:
        """同步执行函数，自动重试+熔断保护"""
        self._check_circuit()
        
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                self._record_success()
                return result
            except self.retryable_exceptions as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._get_delay(attempt)
                    time.sleep(delay)
                else:
                    self._record_failure()
                    raise RetryExhaustedError(self.max_retries + 1, last_error) from last_error
        
        raise RetryExhaustedError(self.max_retries + 1, last_error or Exception("Unknown error"))


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """装饰器：为异步函数添加重试逻辑"""
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            executor = RetryExecutor(
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                retryable_exceptions=retryable_exceptions,
            )
            return await executor.execute(func, *args, **kwargs)
        return wrapper
    return decorator


def with_retry_sync(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """装饰器：为同步函数添加重试逻辑"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            executor = RetryExecutor(
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=jitter,
                retryable_exceptions=retryable_exceptions,
            )
            return executor.execute_sync(func, *args, **kwargs)
        return wrapper
    return decorator


# 默认全局实例
_default_executor: Optional[RetryExecutor] = None
_default_lock = threading.Lock()


def get_default_executor() -> RetryExecutor:
    """获取默认全局重试执行器（线程安全单例）"""
    global _default_executor
    if _default_executor is None:
        with _default_lock:
            if _default_executor is None:
                _default_executor = RetryExecutor()
    return _default_executor
