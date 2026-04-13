"""V3.3 P0 - retry_executor 单元测试

测试内容:
1. RetryExecutor 基本重试逻辑
2. 指数退避延迟计算
3. 熔断器状态转换 (closed→open→half_open→closed)
4. CircuitBreakerError / RetryExhaustedError 异常
5. execute_sync 同步执行
6. with_retry / with_retry_sync 装饰器
7. get_default_executor 单例
"""
import asyncio
import time
import pytest
import threading
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from gateway.retry_executor import (
    RetryExecutor,
    CircuitBreakerError,
    RetryExhaustedError,
    with_retry,
    with_retry_sync,
    get_default_executor,
)


class TestRetryExecutorBasics:
    """基本重试逻辑测试"""

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        """成功调用不触发重试"""
        executor = RetryExecutor(max_retries=3)
        call_count = 0

        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await executor.execute(succeed)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self):
        """瞬时失败触发重试，最终成功"""
        executor = RetryExecutor(max_retries=3, base_delay=0.01, jitter=False)
        call_count = 0

        async def fail_twice_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "recovered"

        result = await executor.execute(fail_twice_then_succeed)
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_retry_exhausted_error(self):
        """重试耗尽抛出 RetryExhaustedError"""
        executor = RetryExecutor(max_retries=2, base_delay=0.001, jitter=False)

        async def always_fail():
            raise ValueError("permanent")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await executor.execute(always_fail)
        assert exc_info.value.attempts == 3  # max_retries + 1
        assert isinstance(exc_info.value.last_error, ValueError)

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self):
        """非重试异常不触发重试，直接抛出"""
        executor = RetryExecutor(
            max_retries=3,
            retryable_exceptions=(ValueError,),
        )
        call_count = 0

        async def raise_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            await executor.execute(raise_type_error)
        assert call_count == 1  # 不重试


class TestExponentialBackoff:
    """指数退避延迟测试"""

    def test_delay_increases_exponentially(self):
        """延迟随尝试次数指数增长"""
        executor = RetryExecutor(
            max_retries=5,
            base_delay=1.0,
            exponential_base=2.0,
            jitter=False,
        )
        delays = [executor._get_delay(i) for i in range(5)]
        # 无抖动: 1*2^0=1, 1*2^1=2, 1*2^2=4, 1*2^3=8, 1*2^4=16
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_delay_capped_at_max_delay(self):
        """延迟上限为 max_delay"""
        executor = RetryExecutor(
            max_retries=10,
            base_delay=10.0,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=False,
        )
        # 10*2^3=80 > 30
        assert executor._get_delay(3) == 30.0
        assert executor._get_delay(4) == 30.0

    def test_jitter_adds_randomness(self):
        """启用抖动时，延迟有随机波动"""
        executor = RetryExecutor(
            max_retries=5,
            base_delay=10.0,
            jitter=True,
        )
        delays = [executor._get_delay(1) for _ in range(20)]
        # 基础延迟20，抖动±10% → 18~22范围
        assert all(18.0 <= d <= 22.0 for d in delays)
        # 有一定随机性
        assert len(set(round(d, 2) for d in delays)) > 1


class TestCircuitBreaker:
    """熔断器状态转换测试"""

    @pytest.mark.asyncio
    async def test_circuit_starts_closed(self):
        """熔断器初始为 closed"""
        executor = RetryExecutor(circuit_breaker_threshold=3)
        assert executor.get_circuit_state() == "closed"

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self):
        """连续失败达到阈值后熔断器打开"""
        executor = RetryExecutor(
            max_retries=0,  # 不重试
            circuit_breaker_threshold=3,
            circuit_breaker_timeout=0.1,
        )

        async def always_fail():
            raise ValueError("fail")

        # 3次失败后熔断器打开
        for _ in range(3):
            try:
                await executor.execute(always_fail)
            except RetryExhaustedError:
                pass

        assert executor.get_circuit_state() == "open"

        # 熔断打开时直接拒绝
        with pytest.raises(CircuitBreakerError):
            await executor.execute(always_fail)

    @pytest.mark.asyncio
    async def test_circuit_half_open_after_timeout(self):
        """熔断超时后进入 half_open 状态"""
        executor = RetryExecutor(
            max_retries=0,
            circuit_breaker_threshold=1,
            circuit_breaker_timeout=0.05,
        )

        async def always_fail():
            raise ValueError("fail")

        # 触发熔断
        try:
            await executor.execute(always_fail)
        except RetryExhaustedError:
            pass

        assert executor.get_circuit_state() == "open"

        # 等待超时
        await asyncio.sleep(0.1)
        assert executor.get_circuit_state() == "half_open"

    @pytest.mark.asyncio
    async def test_circuit_closes_on_success(self):
        """half_open 状态下成功调用关闭熔断器"""
        executor = RetryExecutor(
            max_retries=0,
            circuit_breaker_threshold=1,
            circuit_breaker_timeout=0.05,
        )

        async def fail_once_then_succeed():
            if not hasattr(fail_once_then_succeed, "_called"):
                fail_once_then_succeed._called = True
                raise ValueError("fail")
            return "ok"

        # 触发熔断
        try:
            await executor.execute(fail_once_then_succeed)
        except RetryExhaustedError:
            pass

        # 等待超时进入 half_open
        await asyncio.sleep(0.1)
        assert executor.get_circuit_state() == "half_open"

        # 成功调用，熔断器关闭
        result = await executor.execute(fail_once_then_succeed)
        assert result == "ok"
        assert executor.get_circuit_state() == "closed"

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_circuit(self):
        """half_open 状态下失败，重新打开熔断器"""
        executor = RetryExecutor(
            max_retries=0,
            circuit_breaker_threshold=1,
            circuit_breaker_timeout=0.05,
        )

        async def always_fail():
            raise ValueError("fail")

        # 触发熔断
        try:
            await executor.execute(always_fail)
        except RetryExhaustedError:
            pass

        await asyncio.sleep(0.1)  # 进入 half_open
        assert executor.get_circuit_state() == "half_open"

        # half_open 状态下第一个探测失败，熔断器重新打开（RetryExhaustedError）
        try:
            await executor.execute(always_fail)
        except (CircuitBreakerError, RetryExhaustedError):
            pass

        assert executor.get_circuit_state() == "open"

        # 再次调用被直接拒绝（不进入重试）
        with pytest.raises(CircuitBreakerError):
            await executor.execute(always_fail)
        assert executor.get_circuit_state() == "open"


class TestExecuteSync:
    """同步执行测试"""

    def test_execute_sync_success(self):
        """同步成功调用"""
        executor = RetryExecutor(max_retries=3)
        result = executor.execute_sync(lambda: 42)
        assert result == 42

    def test_execute_sync_retries_on_failure(self):
        """同步执行失败时重试"""
        executor = RetryExecutor(max_retries=2, base_delay=0.001, jitter=False)
        counter = [0]

        def fail_twice():
            counter[0] += 1
            if counter[0] < 3:
                raise ValueError("transient")
            return "ok"

        result = executor.execute_sync(fail_twice)
        assert result == "ok"
        assert counter[0] == 3


class TestDecorators:
    """装饰器测试"""

    @pytest.mark.asyncio
    async def test_with_retry_decorator(self):
        """with_retry 装饰器为异步函数添加重试"""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.001, jitter=False)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("flaky")
            return "done"

        result = await flaky()
        assert result == "done"
        assert call_count == 3

    def test_with_retry_sync_decorator(self):
        """with_retry_sync 装饰器为同步函数添加重试"""
        call_count = 0

        @with_retry_sync(max_retries=2, base_delay=0.001, jitter=False)
        def flaky_sync():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("flaky")
            return "done"

        result = flaky_sync()
        assert result == "done"
        assert call_count == 3


class TestDefaultExecutor:
    """全局单例测试"""

    def test_default_executor_singleton(self):
        """get_default_executor 返回单例"""
        e1 = get_default_executor()
        e2 = get_default_executor()
        assert e1 is e2

    @pytest.mark.asyncio
    async def test_default_executor_works(self):
        """默认执行器功能正常"""
        executor = get_default_executor()
        async def quick():
            return "quick"
        result = await executor.execute(quick)
        assert result == "quick"


class TestEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_zero_max_retries(self):
        """max_retries=0 时不重试"""
        executor = RetryExecutor(max_retries=0, base_delay=0.001, jitter=False)
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(RetryExhaustedError):
            await executor.execute(always_fail)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_kwargs_passed_to_func(self):
        """kwargs 正确传递给目标函数"""
        executor = RetryExecutor(max_retries=0)

        async def func(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = await executor.execute(func, "x", "y", c="z")
        assert result == "x-y-z"

    def test_execute_sync_with_args(self):
        """同步执行传递参数"""
        executor = RetryExecutor(max_retries=0)

        def add(a, b):
            return a + b

        result = executor.execute_sync(add, 3, 4)
        assert result == 7
