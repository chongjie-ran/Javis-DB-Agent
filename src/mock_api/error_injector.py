"""错误注入器 - Mock Javis-DB-Agent API 增强
模拟超时、限流、级联故障等真实场景
"""
import asyncio
import random
import time
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


class ErrorType(Enum):
    """错误类型"""
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    CLIENT_ERROR = "client_error"
    CASCADE_FAILURE = "cascade_failure"
    DATA_INCONSISTENCY = "data_inconsistency"


@dataclass
class ErrorConfig:
    """错误注入配置"""
    enabled: bool = True
    timeout_rate: float = 0.05       # 5% 超时概率
    timeout_delay_seconds: float = 30.0  # 超时延迟
    rate_limit_rate: float = 0.03    # 3% 限流概率
    rate_limit_count: int = 100      # 窗口内最大请求数
    rate_limit_window_seconds: int = 60  # 限流窗口
    cascade_failure_rate: float = 0.1  # 10% 级联故障概率
    server_error_rate: float = 0.02  # 2% 服务器错误概率
    client_error_rate: float = 0.05  # 5% 客户端错误概率
    
    # 特定API错误配置
    api_error_configs: dict[str, dict] = field(default_factory=dict)


@dataclass
class ErrorResult:
    """错误注入结果"""
    should_error: bool
    error_type: Optional[ErrorType]
    error_message: str
    status_code: int
    delay_seconds: float = 0.0


@dataclass
class CascadeFailure:
    """级联故障"""
    source_instance: str
    affected_services: list[str]
    triggered_at: float
    recovery_at: Optional[float] = None


class ErrorInjector:
    """错误注入器"""
    
    def __init__(self, config: Optional[ErrorConfig] = None):
        self.config = config or ErrorConfig()
        self._request_counts: dict[str, list[float]] = defaultdict(list)  # rate limiting
        self._cascade_failures: dict[str, CascadeFailure] = {}  # cascade failures
        self._error_state: dict[str, bool] = defaultdict(bool)  # api error state
    
    def update_config(self, config: ErrorConfig):
        """更新配置"""
        self.config = config
    
    def should_inject_error(self, api_name: str, instance_id: str = None) -> ErrorResult:
        """
        判断是否应该注入错误
        
        Args:
            api_name: API名称
            instance_id: 实例ID（可选）
        
        Returns:
            ErrorResult: 是否注入错误及类型
        """
        if not self.config.enabled:
            return ErrorResult(False, None, "", 200)
        
        # 检查特定API配置
        api_config = self.config.api_error_configs.get(api_name, {})
        
        # 检查级联故障
        if instance_id and self._is_in_cascade_failure(instance_id):
            return ErrorResult(
                should_error=True,
                error_type=ErrorType.CASCADE_FAILURE,
                error_message=f"Instance {instance_id} is in cascade failure",
                status_code=503,
            )
        
        # 检查API错误状态
        if self._error_state.get(api_name):
            return ErrorResult(
                should_error=True,
                error_type=ErrorType.SERVER_ERROR,
                error_message=f"API {api_name} is in error state",
                status_code=500,
            )
        
        # 检查限流
        if self._check_rate_limit(api_name):
            return ErrorResult(
                should_error=True,
                error_type=ErrorType.RATE_LIMIT,
                error_message="Rate limit exceeded",
                status_code=429,
            )
        
        # 随机错误注入（按配置的rate）
        if random.random() < self.config.server_error_rate:
            return ErrorResult(
                should_error=True,
                error_type=ErrorType.SERVER_ERROR,
                error_message="Internal server error",
                status_code=500,
            )
        
        if random.random() < self.config.client_error_rate:
            return ErrorResult(
                should_error=True,
                error_type=ErrorType.CLIENT_ERROR,
                error_message="Bad request",
                status_code=400,
            )
        
        # 超时模拟（对特定API）
        if api_config.get("support_timeout", True) and random.random() < self.config.timeout_rate:
            return ErrorResult(
                should_error=True,
                error_type=ErrorType.TIMEOUT,
                error_message="Request timeout",
                status_code=408,
                delay_seconds=self.config.timeout_delay_seconds,
            )
        
        return ErrorResult(False, None, "", 200)
    
    async def inject_error_delay(self, result: ErrorResult):
        """注入错误延迟"""
        if result.should_error and result.delay_seconds > 0:
            await asyncio.sleep(result.delay_seconds)
    
    def _check_rate_limit(self, api_name: str) -> bool:
        """检查是否限流"""
        now = time.time()
        window = self.config.rate_limit_window_seconds
        
        # 清理过期记录
        self._request_counts[api_name] = [
            t for t in self._request_counts[api_name]
            if now - t < window
        ]
        
        # 检查限流
        if len(self._request_counts[api_name]) >= self.config.rate_limit_count:
            return True
        
        # 记录请求
        self._request_counts[api_name].append(now)
        return False
    
    def _is_in_cascade_failure(self, instance_id: str) -> bool:
        """检查是否处于级联故障"""
        failure = self._cascade_failures.get(instance_id)
        if not failure:
            return False
        if failure.recovery_at and time.time() > failure.recovery_at:
            # 故障已恢复
            del self._cascade_failures[instance_id]
            return False
        return True
    
    def trigger_cascade_failure(
        self,
        source_instance: str,
        affected_services: list[str],
        duration_seconds: int = 300,
    ):
        """
        触发级联故障
        
        Args:
            source_instance: 源实例ID
            affected_services: 受影响的服务列表
            duration_seconds: 持续时间
        """
        self._cascade_failures[source_instance] = CascadeFailure(
            source_instance=source_instance,
            affected_services=affected_services,
            triggered_at=time.time(),
            recovery_at=time.time() + duration_seconds if duration_seconds > 0 else None,
        )
        
        # 随机触发关联服务的故障
        if random.random() < self.config.cascade_failure_rate:
            for service in affected_services:
                self._error_state[service] = True
    
    def set_api_error(self, api_name: str, in_error: bool = True):
        """设置API错误状态"""
        self._error_state[api_name] = in_error
    
    def clear_all_errors(self):
        """清除所有错误状态"""
        self._cascade_failures.clear()
        self._error_state.clear()
        self._request_counts.clear()


class MockJavisAPIErrorInjector:
    """
    包装Mock Javis-DB-Agent API Client，注入错误
    """
    
    def __init__(self, base_client, injector: Optional[ErrorInjector] = None):
        self.base_client = base_client
        self.injector = injector or ErrorInjector()
    
    def _wrap_result(self, result: Any, error_result: ErrorResult) -> Any:
        """包装结果以注入错误"""
        if not error_result.should_error:
            return result
        
        # 返回错误结果（模拟API错误响应）
        return {
            "error": True,
            "error_type": error_result.error_type.value if error_result.error_type else None,
            "message": error_result.error_message,
            "status_code": error_result.status_code,
        }
    
    async def get_instance(self, instance_id: str) -> Optional[dict]:
        """获取实例 - 带错误注入"""
        error_result = self.injector.should_inject_error("get_instance", instance_id)
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result(None, error_result)
        
        return await self.base_client.get_instance(instance_id)
    
    async def list_instances(self, status: Optional[str] = None) -> list[dict]:
        """列出实例 - 带错误注入"""
        error_result = self.injector.should_inject_error("list_instances")
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result([], error_result)
        
        return await self.base_client.list_instances(status)
    
    async def get_sessions(
        self,
        instance_id: str,
        limit: int = 20,
        filter_expr: Optional[str] = None,
    ) -> dict:
        """获取会话 - 带错误注入"""
        error_result = self.injector.should_inject_error("get_sessions", instance_id)
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result({}, error_result)
        
        return await self.base_client.get_sessions(instance_id, limit, filter_expr)
    
    async def get_locks(self, instance_id: str, include_blocker: bool = True) -> dict:
        """获取锁 - 带错误注入"""
        error_result = self.injector.should_inject_error("get_locks", instance_id)
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result({}, error_result)
        
        return await self.base_client.get_locks(instance_id, include_blocker)
    
    async def get_alerts(
        self,
        instance_id: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """获取告警 - 带错误注入"""
        error_result = self.injector.should_inject_error("get_alerts", instance_id)
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result([], error_result)
        
        return await self.base_client.get_alerts(instance_id, severity, status, limit)
    
    async def get_alert_detail(self, alert_id: str) -> Optional[dict]:
        """获取告警详情 - 带错误注入"""
        error_result = self.injector.should_inject_error("get_alert_detail")
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result(None, error_result)
        
        return await self.base_client.get_alert_detail(alert_id)
    
    async def get_slow_sql(
        self,
        instance_id: str,
        limit: int = 10,
        order_by: str = "elapsed_time",
    ) -> dict:
        """获取慢SQL - 带错误注入"""
        error_result = self.injector.should_inject_error("get_slow_sql", instance_id)
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result({}, error_result)
        
        return await self.base_client.get_slow_sql(instance_id, limit, order_by)
    
    async def get_replication_status(self, instance_id: str) -> dict:
        """获取复制状态 - 带错误注入"""
        error_result = self.injector.should_inject_error("get_replication_status", instance_id)
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result({}, error_result)
        
        return await self.base_client.get_replication_status(instance_id)
    
    async def get_tablespaces(self, instance_id: str, tablespace_name: Optional[str] = None) -> dict:
        """获取表空间 - 带错误注入"""
        error_result = self.injector.should_inject_error("get_tablespaces", instance_id)
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result({}, error_result)
        
        return await self.base_client.get_tablespaces(instance_id, tablespace_name)
    
    async def get_instance_metrics(
        self,
        instance_id: str,
        metrics: Optional[list[str]] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> dict:
        """获取实例指标 - 带错误注入"""
        error_result = self.injector.should_inject_error("get_instance_metrics", instance_id)
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result({}, error_result)
        
        return await self.base_client.get_instance_metrics(
            instance_id, metrics, start_time, end_time
        )
    
    async def get_backup_status(
        self,
        instance_id: str,
        backup_type: Optional[str] = None,
    ) -> dict:
        """获取备份状态 - 带错误注入"""
        error_result = self.injector.should_inject_error("get_backup_status", instance_id)
        
        if error_result.should_error:
            await self.injector.inject_error_delay(error_result)
            return self._wrap_result({}, error_result)
        
        return await self.base_client.get_backup_status(instance_id, backup_type)


# ==================== 级联故障模拟器 ====================

class CascadeSimulator:
    """
    级联故障模拟器
    当某个实例发生故障时，自动触发关联服务的故障
    """
    
    # 级联规则：实例ID -> [受影响的API/服务]
    CASCADE_RULES = {
        "INS-001": {
            "affects": ["get_sessions", "get_locks", "get_slow_sql"],
            "delay_seconds": 3,
            "probability": 0.8,
        },
        "INS-002": {
            "affects": ["get_replication_status", "get_sessions"],
            "delay_seconds": 5,
            "probability": 0.6,
        },
        "INS-003": {
            "affects": ["get_instance_metrics", "get_tablespaces"],
            "delay_seconds": 2,
            "probability": 0.9,
        },
    }
    
    def __init__(self, error_injector: ErrorInjector):
        self.error_injector = error_injector
        self._active_cascades: dict[str, dict] = {}
    
    def check_and_trigger_cascade(
        self,
        instance_id: str,
        failure_type: str,
        duration_seconds: int = 300,
    ):
        """
        检查并触发级联故障
        
        Args:
            instance_id: 发生故障的实例ID
            failure_type: 故障类型
            duration_seconds: 持续时间
        """
        if instance_id not in self.CASCADE_RULES:
            return
        
        rule = self.CASCADE_RULES[instance_id]
        
        # 按概率决定是否触发
        if random.random() > rule["probability"]:
            return
        
        # 延迟触发
        affected = rule["affects"]
        delay = rule["delay_seconds"]
        
        cascade_info = {
            "instance_id": instance_id,
            "failure_type": failure_type,
            "affected_services": affected,
            "triggered_at": time.time(),
        }
        self._active_cascades[instance_id] = cascade_info
        
        # 异步触发（简单起见，这里直接触发）
        # 在真实场景中可以用 asyncio.create_task 延迟触发
        self.error_injector.trigger_cascade_failure(
            source_instance=instance_id,
            affected_services=affected,
            duration_seconds=duration_seconds,
        )
    
    def get_active_cascades(self) -> dict[str, dict]:
        """获取活跃的级联故障"""
        return self._active_cascades.copy()
    
    def clear_cascade(self, instance_id: str):
        """清除级联故障"""
        if instance_id in self._active_cascades:
            del self._active_cascades[instance_id]


# ==================== 单例 ====================

_error_injector: Optional[ErrorInjector] = None


def get_error_injector() -> ErrorInjector:
    """获取错误注入器单例"""
    global _error_injector
    if _error_injector is None:
        _error_injector = ErrorInjector()
    return _error_injector


def create_error_injected_client(base_client) -> MockJavisAPIErrorInjector:
    """创建带错误注入的客户端"""
    return MockJavisAPIErrorInjector(base_client, get_error_injector())
