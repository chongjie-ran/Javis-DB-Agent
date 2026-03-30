"""Pre/Post Check Hooks"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class CheckType(Enum):
    """检查类型"""
    PRE_CHECK = "pre_check"
    POST_CHECK = "post_check"


@dataclass
class CheckResult:
    """检查结果"""
    passed: bool
    message: str
    metrics: Optional[Dict[str, Any]] = None
    check_name: str = ""


class CheckHook(ABC):
    """检查钩子基类"""

    def __init__(self, name: str = ""):
        self.name = name or self.__class__.__name__

    @abstractmethod
    async def run(self, context: Dict[str, Any], check_type: CheckType) -> CheckResult:
        """执行检查"""
        pass


class InstanceHealthCheck(CheckHook):
    """实例健康检查"""

    def __init__(self):
        super().__init__("InstanceHealthCheck")

    async def run(self, context: Dict[str, Any], check_type: CheckType) -> CheckResult:
        instance_id = context.get("instance_id")
        if not instance_id:
            return CheckResult(passed=False, message="缺少instance_id", check_name=self.name)

        # 模拟检查（实际应调用真实API）
        # 验证实例状态是否为running
        instance_state = context.get("instance_state", "running")

        if instance_state != "running":
            return CheckResult(
                passed=False,
                message=f"实例状态异常: {instance_state}",
                check_name=self.name,
            )

        return CheckResult(
            passed=True,
            message="实例健康",
            metrics={"instance_id": instance_id, "state": instance_state},
            check_name=self.name,
        )


class ReplicationLagCheck(CheckHook):
    """主从复制延迟检查"""

    def __init__(self, max_lag_seconds: float = 30.0):
        super().__init__("ReplicationLagCheck")
        self.max_lag_seconds = max_lag_seconds

    async def run(self, context: Dict[str, Any], check_type: CheckType) -> CheckResult:
        instance_id = context.get("instance_id")
        replication_lag = context.get("replication_lag_seconds", 0.0)

        if replication_lag > self.max_lag_seconds:
            return CheckResult(
                passed=False,
                message=f"复制延迟过高: {replication_lag}s > {self.max_lag_seconds}s",
                metrics={"lag_seconds": replication_lag, "threshold": self.max_lag_seconds},
                check_name=self.name,
            )

        return CheckResult(
            passed=True,
            message="复制延迟正常",
            metrics={"lag_seconds": replication_lag},
            check_name=self.name,
        )


class SessionCountCheck(CheckHook):
    """会话数检查"""

    def __init__(self, max_sessions: int = 1000):
        super().__init__("SessionCountCheck")
        self.max_sessions = max_sessions

    async def run(self, context: Dict[str, Any], check_type: CheckType) -> CheckResult:
        session_count = context.get("session_count", 0)

        if session_count > self.max_sessions:
            return CheckResult(
                passed=False,
                message=f"会话数过高: {session_count} > {self.max_sessions}",
                metrics={"session_count": session_count, "max": self.max_sessions},
                check_name=self.name,
            )

        return CheckResult(
            passed=True,
            message="会话数正常",
            metrics={"session_count": session_count},
            check_name=self.name,
        )


class LockWaitCheck(CheckHook):
    """锁等待检查"""

    def __init__(self, max_wait_seconds: float = 30.0):
        super().__init__("LockWaitCheck")
        self.max_wait_seconds = max_wait_seconds

    async def run(self, context: Dict[str, Any], check_type: CheckType) -> CheckResult:
        lock_wait_time = context.get("lock_wait_seconds", 0.0)

        if lock_wait_time > self.max_wait_seconds:
            return CheckResult(
                passed=False,
                message=f"锁等待时间过长: {lock_wait_time}s > {self.max_wait_seconds}s",
                metrics={"wait_seconds": lock_wait_time, "threshold": self.max_wait_seconds},
                check_name=self.name,
            )

        return CheckResult(
            passed=True,
            message="锁等待正常",
            metrics={"wait_seconds": lock_wait_time},
            check_name=self.name,
        )


class ConnectionPoolCheck(CheckHook):
    """连接池检查"""

    def __init__(self, max_pool_usage_pct: float = 80.0):
        super().__init__("ConnectionPoolCheck")
        self.max_pool_usage_pct = max_pool_usage_pct

    async def run(self, context: Dict[str, Any], check_type: CheckType) -> CheckResult:
        pool_used = context.get("connection_pool_used", 0)
        pool_max = context.get("connection_pool_max", 100)

        if pool_max <= 0:
            return CheckResult(
                passed=False,
                message="连接池配置异常",
                check_name=self.name,
            )

        usage_pct = (pool_used / pool_max) * 100

        if usage_pct > self.max_pool_usage_pct:
            return CheckResult(
                passed=False,
                message=f"连接池使用率过高: {usage_pct:.1f}% > {self.max_pool_usage_pct}%",
                metrics={"usage_pct": usage_pct, "used": pool_used, "max": pool_max},
                check_name=self.name,
            )

        return CheckResult(
            passed=True,
            message="连接池正常",
            metrics={"usage_pct": usage_pct, "used": pool_used, "max": pool_max},
            check_name=self.name,
        )


class CheckHookRegistry:
    """检查钩子注册表"""

    def __init__(self):
        self._hooks: Dict[str, CheckHook] = {}
        self._init_default_hooks()

    def _init_default_hooks(self):
        """初始化默认钩子"""
        self.register(InstanceHealthCheck())
        self.register(ReplicationLagCheck())
        self.register(SessionCountCheck())
        self.register(LockWaitCheck())
        self.register(ConnectionPoolCheck())

    def register(self, hook: CheckHook):
        """注册钩子"""
        self._hooks[hook.name] = hook

    def unregister(self, name: str) -> bool:
        """注销钩子"""
        if name in self._hooks:
            del self._hooks[name]
            return True
        return False

    def get(self, name: str) -> Optional[CheckHook]:
        """获取钩子"""
        return self._hooks.get(name)

    def list_hooks(self) -> list:
        """列出所有钩子"""
        return list(self._hooks.values())

    async def run_all(
        self,
        context: Dict[str, Any],
        check_type: CheckType,
    ) -> Dict[str, CheckResult]:
        """运行所有钩子"""
        results = {}
        for name, hook in self._hooks.items():
            result = await hook.run(context, check_type)
            results[name] = result
        return results

    async def run_pre_checks(self, context: Dict[str, Any]) -> Dict[str, CheckResult]:
        """运行所有预检查"""
        return await self.run_all(context, CheckType.PRE_CHECK)

    async def run_post_checks(self, context: Dict[str, Any]) -> Dict[str, CheckResult]:
        """运行所有后检查"""
        return await self.run_all(context, CheckType.POST_CHECK)
