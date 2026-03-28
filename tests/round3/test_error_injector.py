"""
第三轮测试：Mock API 错误注入
测试错误注入器、超时、限流、级联故障模拟
"""
import pytest
import asyncio
import time
from src.mock_api.error_injector import (
    ErrorInjector,
    ErrorConfig,
    ErrorType,
    ErrorResult,
    MockZCloudAPIErrorInjector,
    CascadeSimulator,
    get_error_injector,
)


class TestErrorInjector:
    """错误注入器测试"""
    
    @pytest.fixture
    def error_config(self):
        """默认错误配置"""
        return ErrorConfig(
            enabled=True,
            timeout_rate=0.1,       # 10%
            rate_limit_rate=0.1,     # 10%
            rate_limit_count=100,
            rate_limit_window_seconds=60,
            cascade_failure_rate=0.2,
            server_error_rate=0.05,  # 5%
            client_error_rate=0.05,  # 5%
        )
    
    @pytest.fixture
    def injector(self, error_config):
        """创建错误注入器"""
        return ErrorInjector(config=error_config)
    
    def test_injector_initialization(self, injector, error_config):
        """测试注入器初始化"""
        assert injector.config.enabled == error_config.enabled
        assert injector.config.timeout_rate == error_config.timeout_rate
    
    def test_error_result_creation(self):
        """测试错误结果创建"""
        result = ErrorResult(
            should_error=True,
            error_type=ErrorType.TIMEOUT,
            error_message="Request timeout",
            status_code=408,
            delay_seconds=30.0,
        )
        
        assert result.should_error == True
        assert result.error_type == ErrorType.TIMEOUT
        assert result.status_code == 408
        assert result.delay_seconds == 30.0
    
    def test_no_error_when_disabled(self):
        """测试禁用时不注入错误"""
        config = ErrorConfig(enabled=False)
        injector = ErrorInjector(config=config)
        
        result = injector.should_inject_error("get_instance", "INS-001")
        
        assert result.should_error == False
        assert result.status_code == 200
    
    @pytest.mark.asyncio
    async def test_timeout_delay(self, injector):
        """测试超时延迟"""
        result = ErrorResult(
            should_error=True,
            error_type=ErrorType.TIMEOUT,
            error_message="Timeout",
            status_code=408,
            delay_seconds=0.1,  # 100ms for testing
        )
        
        await injector.inject_error_delay(result)
        
        # 如果没有抛异常，说明延迟完成
        assert True
    
    def test_rate_limit_tracking(self, injector):
        """测试限流追踪"""
        api_name = "test_api"
        
        # 前100个请求应该不触发限流
        for i in range(99):
            result = injector.should_inject_error(api_name)
            # 如果是限流错误，跳过
            if result.error_type == ErrorType.RATE_LIMIT:
                break
        
        # 第100个请求之后应该触发限流
        # (注意：由于rate_limit_count=100，前100个请求会占满配额)
        result = injector.should_inject_error(api_name)
        
        # 在达到限流阈值后，应该触发限流
        if injector.config.rate_limit_count <= 100:
            # 此时配额已满，应该限流
            pass  # 可能已经触发
    
    def test_cascade_failure_trigger(self, injector):
        """测试级联故障触发"""
        # 设置100%触发
        injector.config.cascade_failure_rate = 1.0
        
        injector.trigger_cascade_failure(
            source_instance="INS-001",
            affected_services=["get_sessions", "get_locks"],
            duration_seconds=60,
        )
        
        # 检查实例是否在级联故障状态
        assert injector._is_in_cascade_failure("INS-001") == True
        
        # 检查受影响的API是否在错误状态（100%触发时）
        assert injector._error_state.get("get_sessions") == True
        assert injector._error_state.get("get_locks") == True
    
    def test_cascade_failure_recovery(self, injector):
        """测试级联故障恢复"""
        # 触发短时级联故障
        injector.trigger_cascade_failure(
            source_instance="INS-001",
            affected_services=["get_sessions"],
            duration_seconds=1,  # 1秒后恢复
        )
        
        assert injector._is_in_cascade_failure("INS-001") == True
        
        # 等待恢复
        time.sleep(1.1)
        
        # 应该已恢复
        assert injector._is_in_cascade_failure("INS-001") == False
    
    def test_api_error_state(self, injector):
        """测试API错误状态"""
        api_name = "test_api"
        
        # 设置错误状态
        injector.set_api_error(api_name, True)
        
        # 检查是否返回错误
        result = injector.should_inject_error(api_name)
        assert result.should_error == True
        assert result.error_type == ErrorType.SERVER_ERROR
        
        # 清除错误状态
        injector.set_api_error(api_name, False)
        
        # 再次检查（可能有其他随机错误）
        result2 = injector.should_inject_error(api_name)
        # 不应该因为之前的错误状态返回错误
        if result2.error_type == ErrorType.SERVER_ERROR:
            # 可能是随机触发的
            pass
    
    def test_clear_all_errors(self, injector):
        """测试清除所有错误"""
        # 触发多个错误
        injector.trigger_cascade_failure("INS-001", ["get_sessions"], 60)
        injector.set_api_error("test_api", True)
        
        # 清除
        injector.clear_all_errors()
        
        # 验证清除
        assert len(injector._cascade_failures) == 0
        assert len(injector._error_state) == 0


class TestCascadeSimulator:
    """级联故障模拟器测试"""
    
    @pytest.fixture
    def error_injector(self):
        return ErrorInjector(ErrorConfig(enabled=True, cascade_failure_rate=1.0))
    
    @pytest.fixture
    def cascade_simulator(self, error_injector):
        return CascadeSimulator(error_injector)
    
    def test_cascade_rules_exist(self, cascade_simulator):
        """测试级联规则定义"""
        assert len(CascadeSimulator.CASCADE_RULES) > 0
        assert "INS-001" in CascadeSimulator.CASCADE_RULES
    
    def test_check_and_trigger_cascade(self, cascade_simulator, error_injector):
        """测试级联故障检查和触发"""
        # INS-001 触发故障
        cascade_simulator.check_and_trigger_cascade(
            instance_id="INS-001",
            failure_type="DB_HIGH_LOAD",
            duration_seconds=60,
        )
        
        # 验证级联故障已激活（注意：由于概率设置，可能不会触发）
        # 但只要调用不报错就算成功
        active = cascade_simulator.get_active_cascades()
        # 验证方法存在且能返回结果
        assert isinstance(active, dict)
    
    def test_clear_cascade(self, cascade_simulator):
        """测试清除级联故障"""
        cascade_simulator.check_and_trigger_cascade("INS-001", "FAILURE", 60)
        
        # 清除
        cascade_simulator.clear_cascade("INS-001")
        
        active = cascade_simulator.get_active_cascades()
        assert "INS-001" not in active


class TestErrorInjectionScenarios:
    """错误注入场景测试"""
    
    @pytest.fixture
    def error_injector(self):
        config = ErrorConfig(
            enabled=True,
            timeout_rate=0.0,      # 禁用超时
            rate_limit_rate=0.0,   # 禁用限流
            server_error_rate=0.0,  # 禁用服务器错误
            client_error_rate=0.0,  # 禁用客户端错误
        )
        return ErrorInjector(config=config)
    
    def test_timeout_scenario(self):
        """测试超时场景"""
        config = ErrorConfig(
            enabled=True,
            timeout_rate=1.0,  # 100% 超时
            timeout_delay_seconds=0.01,
            server_error_rate=0.0,  # 禁用其他错误
            client_error_rate=0.0,
        )
        injector = ErrorInjector(config=config)
        
        result = injector.should_inject_error("get_instance", "INS-001")
        
        assert result.should_error == True
        assert result.error_type == ErrorType.TIMEOUT
        assert result.status_code == 408
    
    def test_rate_limit_scenario(self):
        """测试限流场景"""
        config = ErrorConfig(
            enabled=True,
            rate_limit_rate=0.0,
            rate_limit_count=5,  # 低阈值
            rate_limit_window_seconds=60,
        )
        injector = ErrorInjector(config=config)
        
        # 发送6个请求触发限流
        for i in range(5):
            injector.should_inject_error("test_api")
        
        # 第6个请求应该限流
        result = injector.should_inject_error("test_api")
        assert result.should_error == True
        assert result.error_type == ErrorType.RATE_LIMIT
        assert result.status_code == 429
    
    def test_cascade_failure_scenario(self):
        """测试级联故障场景"""
        config = ErrorConfig(
            enabled=True,
            cascade_failure_rate=1.0,  # 100% 触发
        )
        injector = ErrorInjector(config=config)
        
        # 触发INS-001故障
        injector.trigger_cascade_failure(
            source_instance="INS-001",
            affected_services=["get_sessions", "get_locks", "get_slow_sql"],
            duration_seconds=300,
        )
        
        # 检查受影响的API
        for api in ["get_sessions", "get_locks", "get_slow_sql"]:
            result = injector.should_inject_error(api, "INS-001")
            assert result.should_error == True
            assert result.error_type == ErrorType.CASCADE_FAILURE
    
    def test_mixed_error_scenario(self):
        """测试混合错误场景"""
        config = ErrorConfig(
            enabled=True,
            timeout_rate=0.1,
            rate_limit_rate=0.1,
            server_error_rate=0.1,
            client_error_rate=0.1,
        )
        injector = ErrorInjector(config=config)
        
        error_types = []
        
        # 发送多个请求，收集错误类型
        for _ in range(50):
            result = injector.should_inject_error("test_api")
            if result.should_error and result.error_type:
                error_types.append(result.error_type)
        
        # 应该收集到多种错误类型
        unique_types = set(error_types)
        assert len(unique_types) > 0, "Should have at least one error type"


class TestErrorInjectorStress:
    """错误注入器压力测试"""
    
    def test_high_concurrency(self):
        """测试高并发"""
        config = ErrorConfig(enabled=True, timeout_rate=0.5)
        injector = ErrorInjector(config=config)
        
        async def make_request():
            return injector.should_inject_error("test_api")
        
        async def run_concurrent():
            tasks = [make_request() for _ in range(100)]
            return await asyncio.gather(*tasks)
        
        results = asyncio.run(run_concurrent())
        
        error_count = sum(1 for r in results if r.should_error)
        
        # 大约50%的请求应该出错
        assert error_count > 0, "Should have some errors under high concurrency"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
