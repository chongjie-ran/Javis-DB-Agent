"""执行闭环模块

提供SOP执行器、执行回流验证、Pre/Post Check钩子等能力。
"""
from .sop_executor import (
    SOPExecutor,
    SOPStatus,
    SOPExecutionResult,
    SOPStepResult,
    SOPStepStatus,
)
from .execution_feedback import (
    ExecutionFeedback,
    FeedbackResult,
    FeedbackVerificationResult,
    Deviation,
    BatchVerificationResult,
    FeedbackMetrics,
)
from .check_hooks import (
    CheckHook,
    CheckType,
    CheckResult,
    CheckHookRegistry,
    InstanceHealthCheck,
    ReplicationLagCheck,
    SessionCountCheck,
    LockWaitCheck,
    ConnectionPoolCheck,
)

__all__ = [
    # SOP执行器
    "SOPExecutor",
    "SOPStatus",
    "SOPExecutionResult",
    "SOPStepResult",
    "SOPStepStatus",
    # 执行回流验证
    "ExecutionFeedback",
    "FeedbackResult",
    "FeedbackVerificationResult",
    "Deviation",
    "BatchVerificationResult",
    "FeedbackMetrics",
    # Pre/Post Check Hooks
    "CheckHook",
    "CheckType",
    "CheckResult",
    "CheckHookRegistry",
    "InstanceHealthCheck",
    "ReplicationLagCheck",
    "SessionCountCheck",
    "LockWaitCheck",
    "ConnectionPoolCheck",
]
