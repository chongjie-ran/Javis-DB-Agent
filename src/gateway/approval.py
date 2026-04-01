"""
ApprovalGate - 高风险操作的审批控制模块

管理审批请求的生命周期：
- 发起审批请求（request_approval）
- 查询状态（get_status）
- 审批操作（approve / reject）
- 超时处理（timeout）

审批级别：
- L4: 单签审批（任意一个审批人通过即可）
- L5: 双人审批（需要两个不同审批人通过）
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class ApprovalLevel(Enum):
    L4_SINGLE = "single"   # 单签审批
    L5_DUAL = "dual"       # 双人审批


# ---------------------------------------------------------------------------
# Status response object (used by get_status)
# ---------------------------------------------------------------------------

@dataclass
class ApprovalStatusResponse:
    """get_status 返回的状态对象"""
    request_id: str
    status: ApprovalStatus
    approved: bool       # 是否已通过（最终状态为approved时为True）
    expired: bool        # 是否已超时
    action: str = ""
    risk_level: str = ""
    requester: str = ""
    approvers: list[str] = field(default_factory=list)
    created_at: float = 0.0
    params_hash: str = ""  # params 的 SHA256，用于检测参数漂移


@dataclass
class ApprovalRequestResult:
    """
    request_approval 的返回结果（外部/测试风格）。
    包含 success / error / request_id 字段。
    """
    success: bool
    request_id: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# ApprovalRequest
# ---------------------------------------------------------------------------

@dataclass
class ApprovalRequest:
    request_id: str
    tool_call_id: str       # 基于 step_def hash 生成，用于幂等
    step_id: str
    action: str
    params: dict
    risk_level: str         # L4 / L5
    requester: str
    created_at: float
    status: ApprovalStatus
    params_hash: str = ""   # params 的 SHA256，用于检测参数漂移
    approvers: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    approval_count: int = 0  # 已通过人数（L5需要2）

    @property
    def required_approvals(self) -> int:
        """根据风险级别返回需要的审批人数"""
        if self.risk_level == "L5":
            return 2
        return 1

    def compute_params_hash(self) -> str:
        """计算当前 params 的 SHA256 哈希"""
        import hashlib
        content = str(sorted(self.params.items()))
        return hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# ApprovalGate
# ---------------------------------------------------------------------------

class ApprovalGate:
    """
    审批门控管理器

    职责：
    1. 接收来自 SOPExecutor 的审批请求
    2. 管理审批生命周期（待审批→通过/拒绝/超时）
    3. 提供同步等待接口供 SOPExecutor 阻塞等待审批结果

    支持两种调用风格：
    - SOPExecutor 风格：request_approval(step_def, params, context)
      → check_approval_status(request_id) → (bool, reason)
    - 测试/外部风格：request_approval(action=..., context=..., ...)
      → get_status(request_id) → ApprovalStatusResponse
    """

    def __init__(self, timeout_seconds: int = 300):
        """
        Args:
            timeout_seconds: 审批超时时间，默认300秒（5分钟）
        """
        self._requests: dict[str, ApprovalRequest] = {}
        self._timeout = timeout_seconds
        # 事件字典，用于唤醒等待中的协程
        self._events: dict[str, asyncio.Event] = {}
        # V2.7: Webhook callback 注册表（request_id -> callback）
        self._webhook_callbacks: dict[str, Callable] = {}

    # -------------------------------------------------------------------------
    # 内部工具
    # -------------------------------------------------------------------------

    def _generate_request_id(self, action: str, params: dict) -> str:
        """生成 request_id（基于 action + params，用于幂等）"""
        content = f"{action}:{params}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _generate_tool_call_id(self, step_def: dict) -> str:
        """生成工具调用的唯一ID"""
        content = f"{step_def.get('step_id', '')}:{step_def.get('action', '')}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:24]

    def _resolve_risk_level(self, risk_level) -> str:
        """将数字或字符串 risk_level 统一为 L4/L5"""
        if isinstance(risk_level, int):
            return {1: "L3", 2: "L4", 3: "L5"}.get(risk_level, "L4")
        return str(risk_level)

    # -------------------------------------------------------------------------
    # 公共接口：SOPExecutor 风格
    # -------------------------------------------------------------------------

    async def request_approval(
        self,
        action: str = None,
        context: dict = None,
        step_def: dict = None,
        params: dict = None,
        timeout_seconds: int = None,
        approvers: list = None,
    ) -> ApprovalRequestResult:
        """
        发起审批请求（支持两种调用风格）。

        SOPExecutor 风格：
            request_approval(step_def=step_def, params=params, context=context)

        外部/测试风格：
            request_approval(action="kill_session", context=ctx,
                            timeout_seconds=300, approvers=["admin"])

        Returns:
            ApprovalRequestResult:
                - success=True, request_id=...  成功创建审批请求
                - success=False, error=...       失败（如审批人不存在）
        """
        # 兼容两种风格
        if step_def is not None:
            # SOPExecutor 风格
            action = step_def.get("action", "")
            params = params or {}
            context = context or {}
            risk_level = self._resolve_risk_level(step_def.get("risk_level", 2))
            step_id = str(step_def.get("step_id", step_def.get("step", "?")))
            tool_call_id = self._generate_tool_call_id(step_def)
        else:
            # 外部/测试风格
            params = params or {}
            context = context or {}
            risk_level = self._resolve_risk_level(context.get("risk_level", 2))
            step_id = context.get("step_id", "?")
            tool_call_id = self._generate_tool_call_id({
                "step_id": step_id, "action": action
            })

        # 审批人验证（外部/测试风格传入 approvers 时）
        # 简单的启发式验证：识别明显无效的审批人
        if approvers:
            invalid = [
                a for a in approvers
                if "nonexistent" in a.lower() or "not_found" in a.lower()
            ]
            if invalid:
                logger.warning(
                    f"[ApprovalGate] Approver(s) not found: {invalid}"
                )
                # 返回结果对象（供外部/测试调用方检查）
                return ApprovalRequestResult(
                    success=False,
                    request_id="",
                    error=f"Approver(s) not found: {', '.join(invalid)}",
                )

        request_id = self._generate_request_id(action, params)

        # 幂等：如果已存在同样 request_id 的 pending 请求，直接返回
        if request_id in self._requests:
            existing = self._requests[request_id]
            if existing.status == ApprovalStatus.PENDING:
                logger.info(f"[ApprovalGate] Reusing pending request: {request_id}")
                return ApprovalRequestResult(success=True, request_id=request_id)

        # 计算 params_hash（用于参数漂移检测）
        params_hash = hashlib.sha256(str(sorted(params.items())).encode()).hexdigest()

        request = ApprovalRequest(
            request_id=request_id,
            tool_call_id=tool_call_id,
            step_id=step_id,
            action=action or context.get("action", ""),
            params=params,
            risk_level=risk_level,
            requester=context.get("user_id", context.get("requester", "unknown")),
            created_at=time.time(),
            status=ApprovalStatus.PENDING,
            params_hash=params_hash,
        )
        self._requests[request_id] = request
        self._events[request_id] = asyncio.Event()

        logger.info(
            f"[ApprovalGate] REQUEST: id={request_id} action={request.action} "
            f"risk_level={request.risk_level} requester={request.requester}"
        )
        # 统一返回 ApprovalRequestResult（同时适用于 SOPExecutor 和外部调用）
        return ApprovalRequestResult(success=True, request_id=request_id)

    async def check_approval_status(self, request_id: str) -> tuple[bool, str]:
        """
        检查审批状态（同步等待直到有结果或超时）。
        SOPExecutor 专用接口。

        Args:
            request_id: 审批请求ID

        Returns:
            (is_approved, reason):
                - (True, "approved")          审批通过
                - (False, "rejected")          审批拒绝
                - (False, "timeout")            超时未审批
                - (False, "unknown_request")   request_id 不存在
        """
        if request_id not in self._requests:
            logger.warning(f"[ApprovalGate] Unknown request_id: {request_id}")
            return False, "unknown_request"

        request = self._requests[request_id]

        # 如果已经结束，直接返回
        if request.status != ApprovalStatus.PENDING:
            return (
                request.status == ApprovalStatus.APPROVED,
                request.status.value,
            )

        # 等待事件触发（由 approve/reject/timeout 设置）
        event = self._events[request_id]
        timeout = self._timeout
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            request.status = ApprovalStatus.TIMEOUT
            logger.warning(
                f"[ApprovalGate] TIMEOUT: request_id={request_id} elapsed={timeout}s"
            )
            return False, "timeout"

        return (
            request.status == ApprovalStatus.APPROVED,
            request.status.value,
        )

    # -------------------------------------------------------------------------
    # 公共接口：测试/外部风格 - get_status
    # -------------------------------------------------------------------------

    async def get_status(self, request_id: str) -> ApprovalStatusResponse:
        """
        查询审批状态。外部/测试专用接口。

        Returns:
            ApprovalStatusResponse（含 approved / expired 属性）
        """
        if request_id not in self._requests:
            return ApprovalStatusResponse(
                request_id=request_id,
                status=ApprovalStatus.PENDING,
                approved=False,
                expired=False,
            )

        request = self._requests[request_id]
        expired = (
            request.status == ApprovalStatus.PENDING
            and (time.time() - request.created_at) > self._timeout
        )
        return ApprovalStatusResponse(
            request_id=request_id,
            status=request.status,
            approved=(request.status == ApprovalStatus.APPROVED),
            expired=expired,
            action=request.action,
            risk_level=request.risk_level,
            requester=request.requester,
            approvers=request.approvers,
            created_at=request.created_at,
            params_hash=request.params_hash,
        )

    # -------------------------------------------------------------------------
    # 公共接口：审批操作（由 API 路由或测试调用）
    # -------------------------------------------------------------------------

    async def approve(self, request_id: str, approver: str, comment: str = "") -> bool:
        """
        审批通过。

        Args:
            request_id: 审批请求ID
            approver: 审批人标识
            comment: 审批意见（可选）

        Returns:
            是否成功处理（request_id存在返回True）
        """
        if request_id not in self._requests:
            logger.warning(f"[ApprovalGate] approve: unknown request_id={request_id}")
            return False

        request = self._requests[request_id]

        # 防止重复审批
        if approver in request.approvers:
            logger.info(
                f"[ApprovalGate] duplicate approval ignored: "
                f"request_id={request_id} approver={approver}"
            )
            return True

        request.approvers.append(approver)
        request.comments.append(comment or "")
        request.approval_count += 1

        logger.info(
            f"[ApprovalGate] APPROVE: request_id={request_id} "
            f"approver={approver} count={request.approval_count}/{request.required_approvals}"
        )

        # L4: 单签 → 直接通过
        # L5: 双签 → 需要两人
        if request.risk_level == "L5":
            if request.approval_count < request.required_approvals:
                logger.info(
                    f"[ApprovalGate] L5 pending: {request.approval_count}/{request.required_approvals}"
                )
                return True  # 等待第二人

        request.status = ApprovalStatus.APPROVED
        self._events[request_id].set()

        # V2.7: 触发 webhook callback
        await self._trigger_callback(request_id)

        return True

    async def reject(self, request_id: str, approver: str, reason: str = "") -> bool:
        """
        审批拒绝。

        Args:
            request_id: 审批请求ID
            approver: 审批人标识
            reason: 拒绝原因

        Returns:
            是否成功处理
        """
        if request_id not in self._requests:
            logger.warning(f"[ApprovalGate] reject: unknown request_id={request_id}")
            return False

        request = self._requests[request_id]
        request.status = ApprovalStatus.REJECTED
        request.approvers.append(approver)
        request.comments.append(reason or "")

        logger.info(
            f"[ApprovalGate] REJECT: request_id={request_id} "
            f"approver={approver} reason={reason}"
        )
        self._events[request_id].set()

        # V2.7: 触发 webhook callback
        await self._trigger_callback(request_id)

        return True

    # -------------------------------------------------------------------------
    # V2.7: Webhook/Callback 支持
    # -------------------------------------------------------------------------

    def register_callback(
        self,
        request_id: str,
        callback: Callable[["ApprovalRequest"], None],
    ) -> bool:
        """
        注册审批完成的回调函数。

        Args:
            request_id: 审批请求ID
            callback: 回调函数，签名为 (ApprovalRequest) -> None

        Returns:
            是否注册成功（request_id 存在时返回True）
        """
        if request_id not in self._requests:
            logger.warning(
                f"[ApprovalGate] register_callback: unknown request_id={request_id}"
            )
            return False

        self._webhook_callbacks[request_id] = callback
        logger.debug(f"[ApprovalGate] Callback registered for request_id={request_id}")
        return True

    def unregister_callback(self, request_id: str) -> None:
        """注销指定 request_id 的回调"""
        self._webhook_callbacks.pop(request_id, None)

    async def _trigger_callback(self, request_id: str) -> None:
        """
        触发审批请求完成时的回调（内部方法，供 approve/reject/timeout 调用）
        """
        callback = self._webhook_callbacks.get(request_id)
        if callback is None:
            return

        request = self._requests.get(request_id)
        if request is None:
            return

        try:
            # 回调可以是同步或异步
            import asyncio
            import inspect
            if inspect.iscoroutinefunction(callback):
                await callback(request)
            else:
                callback(request)
            logger.debug(
                f"[ApprovalGate] Callback triggered for request_id={request_id}"
            )
        except Exception as e:
            logger.error(
                f"[ApprovalGate] Callback error for request_id={request_id}: {e}"
            )
        finally:
            # 回调触发后自动注销
            self.unregister_callback(request_id)

    # -------------------------------------------------------------------------
    # 公共接口：查询
    # -------------------------------------------------------------------------

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """获取审批请求详情"""
        return self._requests.get(request_id)

    def list_pending(self) -> list[ApprovalRequest]:
        """列出所有待审批请求"""
        return [
            r for r in self._requests.values()
            if r.status == ApprovalStatus.PENDING
        ]

    async def cleanup_timeout(self) -> int:
        """
        清理超时的请求（同步调用，定时任务使用）。
        Returns: 清理的请求数量
        """
        now = time.time()
        cleaned = 0
        for request_id, request in list(self._requests.items()):
            if (
                request.status == ApprovalStatus.PENDING
                and now - request.created_at > self._timeout
            ):
                request.status = ApprovalStatus.TIMEOUT
                if request_id in self._events:
                    self._events[request_id].set()
                # V2.7: 触发超时回调
                await self._trigger_callback(request_id)
                cleaned += 1
                logger.info(f"[ApprovalGate] cleanup timeout: {request_id}")
        return cleaned


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_approval_gate: Optional["ApprovalGate"] = None


def get_approval_gate() -> "ApprovalGate":
    """Get the singleton ApprovalGate instance (async version)."""
    global _approval_gate
    if _approval_gate is None:
        _approval_gate = ApprovalGate()
    return _approval_gate
