"""执行回流验证器"""
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class FeedbackResult(Enum):
    """回流验证结果"""
    IMPROVED = "improved"          # 状态改善
    UNCHANGED = "unchanged"       # 状态无变化
    DEGRADED = "degraded"         # 状态恶化
    TIMEOUT = "timeout"          # 验证超时
    ERROR = "error"              # 验证错误


@dataclass
class Deviation:
    """偏差详情"""
    field: str
    expected: Any
    actual: Any
    severity: str = "warning"   # warning / error / critical

    def __getitem__(self, key):
        """支持dict-like访问"""
        return getattr(self, key)


@dataclass
class FeedbackVerificationResult:
    """验证结果"""
    verified: bool                    # 是否验证通过
    feedback_result: FeedbackResult    # 回流结果
    deviations: List[Deviation] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    message: str = ""
    critical_alert_triggered: bool = False
    execution_metrics: dict = field(default_factory=dict)


@dataclass
class BatchVerificationResult:
    """批量验证结果"""
    verified_count: int = 0
    failed_count: int = 0
    total_count: int = 0
    results: List[FeedbackVerificationResult] = field(default_factory=list)


@dataclass
class FeedbackMetrics:
    """执行闭环指标"""
    execution_id: str
    step_duration_ms: int = 0
    retry_count: int = 0
    improvement_rate: float = 0.0
    verification_time_ms: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


class ExecutionFeedback:
    """
    执行回流验证器

    职责：
    1. 执行前预校验（PreCheck）
    2. 执行后状态验证（PostCheck）
    3. 偏差检测与自动修复建议
    4. 重试机制
    5. 关键偏差告警
    """

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    async def verify(
        self,
        execution_record: dict,
        actual_result: Any,
        context: Optional[dict] = None,
    ) -> FeedbackVerificationResult:
        """
        验证执行结果是否符合预期（含自动重试）

        Args:
            execution_record: 执行记录（包含expected_result等）
            actual_result: 实际执行结果
            context: 验证上下文

        Returns:
            FeedbackVerificationResult
        """
        context = context or {}
        expected_result = execution_record.get("expected_result", {})
        execution_id = execution_record.get("execution_id", "unknown")
        is_critical = execution_record.get("critical", False)

        retry_count = 0
        max_retries = self.max_retries

        for attempt in range(max_retries + 1):
            result = FeedbackVerificationResult(
                verified=False,
                feedback_result=FeedbackResult.ERROR,
                max_retries=max_retries,
                retry_count=attempt,
            )

            # 比对预期与实际
            deviations = self._compare_results(expected_result, actual_result)

            if not deviations:
                result.verified = True
                result.feedback_result = FeedbackResult.IMPROVED
                result.message = "执行结果符合预期"
                return result

            result.deviations = deviations

            # 判断偏差严重程度
            has_critical = any(d.severity == "critical" for d in deviations)
            has_error = any(d.severity == "error" for d in deviations)

            if has_critical:
                result.feedback_result = FeedbackResult.DEGRADED
                result.verified = False
                result.message = "发现严重偏差"
                if is_critical:
                    result.critical_alert_triggered = True
            elif has_error:
                result.feedback_result = FeedbackResult.DEGRADED
                result.verified = False
                result.message = "发现错误级偏差"
            else:
                result.feedback_result = FeedbackResult.UNCHANGED
                result.verified = True  # 轻微偏差仍视为通过
                result.message = "发现轻微偏差"

            # 非最后一次尝试，等待后重试
            if attempt < max_retries:
                retry_count = attempt + 1
                await asyncio.sleep(0.5 * (attempt + 1))  # 指数退避
            else:
                # 最后一次，返回最终结果
                return result

        # 不应到达这里，但作为安全网返回
        return result

    async def batch_verify(
        self,
        executions: List[dict],
        actual_results: List[Any],
        context: Optional[dict] = None,
    ) -> BatchVerificationResult:
        """
        批量验证执行结果

        Returns:
            BatchVerificationResult
        """
        result = BatchVerificationResult(total_count=len(executions))

        for exec_rec, actual in zip(executions, actual_results):
            verify_result = await self.verify(exec_rec, actual, context)
            result.results.append(verify_result)

            if verify_result.verified:
                result.verified_count += 1
            else:
                result.failed_count += 1

        return result

    def _compare_results(
        self,
        expected: Any,
        actual: Any,
        path: str = "",
    ) -> List[Deviation]:
        """递归比对预期与实际结果"""
        deviations = []

        if isinstance(expected, dict) and isinstance(actual, dict):
            # 字典逐键比对
            all_keys = set(expected.keys()) | set(actual.keys())
            for key in all_keys:
                field_path = f"{path}.{key}" if path else key
                if key not in expected:
                    deviations.append(Deviation(
                        field=field_path,
                        expected=None,
                        actual=actual[key],
                        severity="warning",
                    ))
                elif key not in actual:
                    deviations.append(Deviation(
                        field=field_path,
                        expected=expected[key],
                        actual=None,
                        severity="error",
                    ))
                else:
                    # 递归比对
                    sub_deviations = self._compare_results(
                        expected[key], actual[key], field_path
                    )
                    deviations.extend(sub_deviations)

        elif isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
            # 列表按长度和元素比对
            if len(expected) != len(actual):
                deviations.append(Deviation(
                    field=path,
                    expected=f"list[{len(expected)}]",
                    actual=f"list[{len(actual)}]",
                    severity="error",
                ))
            else:
                for i, (exp_item, act_item) in enumerate(zip(expected, actual)):
                    sub_deviations = self._compare_results(exp_item, act_item, f"{path}[{i}]")
                    deviations.extend(sub_deviations)

        else:
            # 标量值比对
            if expected != actual:
                # 判断严重程度
                if expected is None or actual is None:
                    severity = "error"
                elif isinstance(expected, bool) or isinstance(actual, bool):
                    severity = "critical" if expected != actual else "info"
                else:
                    severity = "warning"

                deviations.append(Deviation(
                    field=path or "value",
                    expected=expected,
                    actual=actual,
                    severity=severity,
                ))

        return deviations

    async def pre_check(
        self,
        action: str,
        params: dict,
        context: dict,
    ) -> Tuple[bool, str]:
        """
        执行前预检查

        Returns:
            (passed, message)
        """
        # 预检查：验证参数合理性
        if not action:
            return False, "action不能为空"

        # 预检查：实例状态
        instance_id = context.get("instance_id")
        if not instance_id:
            return False, "缺少instance_id"

        # 预检查：权限
        permissions = context.get("permissions", [])
        if "execute" not in permissions and action in ["kill_session", "kill_backend"]:
            return False, "缺少execute权限"

        return True, "预检查通过"

    async def post_check(
        self,
        action: str,
        params: dict,
        result: Any,
        context: dict,
    ) -> Tuple[bool, str]:
        """
        执行后状态检查

        Returns:
            (passed, message)
        """
        # 基本成功检查
        if isinstance(result, dict):
            if result.get("error"):
                return False, f"执行返回错误: {result.get('error')}"
            if result.get("success") is False:
                return False, "执行失败"

        return True, "后检查通过"

    def emit_metrics(self, execution_id: str, verification_result: FeedbackVerificationResult) -> FeedbackMetrics:
        """发送执行闭环指标"""
        return FeedbackMetrics(
            execution_id=execution_id,
            retry_count=verification_result.retry_count,
            improvement_rate=1.0 if verification_result.verified else 0.0,
            timestamp=datetime.now(),
        )

    async def _check_result(
        self,
        execution_record: dict,
        actual_result: Any,
    ) -> Any:
        """
        内部验证方法（供超时场景patch）
        直接比对结果，不包含重试逻辑
        """
        expected = execution_record.get("expected_result", {})
        return self._compare_results(expected, actual_result)
