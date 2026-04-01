"""SafetyGuardRail - 不可绕过安全护栏"""
import logging
from typing import Optional
from dataclasses import dataclass

from src.tools.base import RiskLevel
from src.gateway.approval import ApprovalGate, ApprovalStatus, ApprovalRequestResult
from src.gateway.hooks import HookEngine, HookEvent, HookResult, get_hook_engine

logger = logging.getLogger(__name__)


class ApprovalRequiredError(Exception):
    """
    审批未通过异常（不可绕过）

    当 L4/L5 操作未通过审批时抛出此异常。
    与普通错误不同，此异常表示操作被安全策略拦截。
    """
    pass


@dataclass
class GuardRailResult:
    """安全护栏检查结果"""
    allowed: bool
    approval_token: Optional[str] = None
    message: str = ""
    risk_level: str = "L1"


class SafetyGuardRail:
    """
    不可绕过安全护栏

    核心原则：
    1. Tool 执行前必须经过此 Gate
    2. L4/L5 操作无有效审批令牌则抛出 ApprovalRequiredError（不是返回错误）
    3. 审批令牌存储在执行上下文 context["approval_tokens"] 中
    4. Tool 执行层不持有审批判断权，只持有令牌验证权

    架构：
        ToolRegistry.execute()
              │
              ├──▶ HookEngine.emit(TOOL_BEFORE_EXECUTE)  ← 可阻断
              │         └──▶ DDL Hook: 检查 DDL 语句
              │
              ├──▶ SafetyGuardRail.enforce()            ← 不可绕过
              │         ├──▶ L1-L3: 直接放行
              │         ├──▶ L4: 强制单签审批
              │         └──▶ L5: 强制双人审批
              │
              └──▶ 执行 Tool（只有持有有效审批令牌的才能执行）
    """

    def __init__(
        self,
        approval_gate: Optional[ApprovalGate] = None,
        hook_engine: Optional[HookEngine] = None,
    ):
        self._approval_gate = approval_gate
        self._hook_engine = hook_engine

    @property
    def approval_gate(self) -> ApprovalGate:
        if self._approval_gate is None:
            from src.gateway.approval import get_approval_gate
            self._approval_gate = get_approval_gate()
        return self._approval_gate

    @property
    def hook_engine(self) -> HookEngine:
        if self._hook_engine is None:
            self._hook_engine = get_hook_engine()
        return self._hook_engine

    async def enforce(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        context: dict,
        timeout: int = 300,
    ) -> GuardRailResult:
        """
        强制执行安全检查

        Args:
            tool_name: 工具名称
            risk_level: 风险级别
            context: 执行上下文（含 user_id, session_id, params, approval_tokens）
            timeout: 审批超时时间（秒）

        Returns:
            GuardRailResult: 检查结果

        Raises:
            ApprovalRequiredError: L4/L5 操作无有效令牌且审批未通过
        """
        risk_str = f"L{int(risk_level)}" if isinstance(risk_level, (int, RiskLevel)) else str(risk_level)

        # L1-L3: 直接放行
        if risk_level <= RiskLevel.L3_LOW_RISK:
            return GuardRailResult(
                allowed=True,
                risk_level=risk_str,
                message="Risk level L1-L3, no approval required",
            )

        # L4: 单签审批
        if risk_level == RiskLevel.L4_MEDIUM:
            return await self._enforce_l4(tool_name, risk_str, context, timeout)

        # L5: 双人审批
        if risk_level == RiskLevel.L5_HIGH:
            return await self._enforce_l5(tool_name, risk_str, context, timeout)

        return GuardRailResult(allowed=True, risk_level=risk_str)

    async def _enforce_l4(
        self,
        tool_name: str,
        risk_str: str,
        context: dict,
        timeout: int,
    ) -> GuardRailResult:
        """L4 单签审批"""
        token_key = f"{tool_name}:L4"
        tokens = context.setdefault("approval_tokens", {})

        # 检查是否已有有效令牌
        if tokens.get(token_key):
            logger.debug(f"L4 token found for {tool_name}, skipping approval")
            return GuardRailResult(
                allowed=True,
                approval_token=tokens[token_key],
                risk_level=risk_str,
                message="L4 approval token valid",
            )

        # 发起审批请求
        logger.info(f"L4 operation requires approval: {tool_name}")
        result = await self._request_approval(
            tool_name=tool_name,
            risk_level="L4",
            requester=context.get("user_id", "unknown"),
            params=context.get("params", {}),
            timeout=timeout,
        )

        if not result.success:
            raise ApprovalRequiredError(
                f"L4 操作 {tool_name} 需要审批，当前未通过审批。"
                f"原因: {result.error}"
            )

        # 写入令牌
        tokens[token_key] = result.request_id
        return GuardRailResult(
            allowed=True,
            approval_token=result.request_id,
            risk_level=risk_str,
            message="L4 approval granted",
        )

    async def _enforce_l5(
        self,
        tool_name: str,
        risk_str: str,
        context: dict,
        timeout: int,
    ) -> GuardRailResult:
        """L5 双人审批"""
        token_key = f"{tool_name}:L5"
        tokens = context.setdefault("approval_tokens", {})

        # 检查是否已有有效令牌
        if tokens.get(token_key):
            logger.debug(f"L5 token found for {tool_name}, skipping dual approval")
            return GuardRailResult(
                allowed=True,
                approval_token=tokens[token_key],
                risk_level=risk_str,
                message="L5 dual approval token valid",
            )

        # 发起双人审批请求
        logger.warning(f"L5 operation requires DUAL approval: {tool_name}")
        result = await self._request_dual_approval(
            tool_name=tool_name,
            risk_level="L5",
            requester=context.get("user_id", "unknown"),
            params=context.get("params", {}),
            timeout=timeout,
        )

        if not result.success:
            raise ApprovalRequiredError(
                f"L5 操作 {tool_name} 需要双人审批，当前未通过。"
                f"原因: {result.error}"
            )

        tokens[token_key] = result.request_id
        return GuardRailResult(
            allowed=True,
            approval_token=result.request_id,
            risk_level=risk_str,
            message="L5 dual approval granted",
        )

    async def _request_approval(
        self,
        tool_name: str,
        risk_level: str,
        requester: str,
        params: dict,
        timeout: int,
    ) -> ApprovalRequestResult:
        """发起审批请求（带超时等待）"""
        import hashlib
        import time

        request_id = hashlib.md5(
            f"{tool_name}:{risk_level}:{requester}:{time.time()}".encode()
        ).hexdigest()[:16]

        # 直接使用 ApprovalGate 的接口
        gate = self.approval_gate

        # 创建请求（内部）
        await gate.request_approval(
            tool_name=tool_name,
            risk_level=risk_level,
            requester=requester,
            params=params,
        )

        # 带超时的等待循环
        import asyncio
        start_time = time.time()
        poll_interval = 2.0  # 每 2 秒轮询一次

        while True:
            status_resp = await gate.get_status(request_id)
            if status_resp.status != ApprovalStatus.PENDING:
                is_approved = status_resp.status == ApprovalStatus.APPROVED
                reason = status_resp.status.value
                if is_approved:
                    return ApprovalRequestResult(success=True, request_id=request_id)
                else:
                    return ApprovalRequestResult(
                        success=False, request_id=request_id, error=f"审批{reason}"
                    )

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return ApprovalRequestResult(
                    success=False, request_id=request_id, error="审批超时"
                )

            await asyncio.sleep(min(poll_interval, timeout - elapsed))

    async def _request_dual_approval(
        self,
        tool_name: str,
        risk_level: str,
        requester: str,
        params: dict,
        timeout: int,
    ) -> ApprovalRequestResult:
        """发起双人审批请求（带超时等待）"""
        import hashlib
        import time

        request_id = hashlib.md5(
            f"{tool_name}:{risk_level}:{requester}:dual:{time.time()}".encode()
        ).hexdigest()[:16]

        gate = self.approval_gate

        await gate.request_approval(
            tool_name=tool_name,
            risk_level=risk_level,
            requester=requester,
            params=params,
        )

        # 带超时的等待循环
        import asyncio
        start_time = time.time()
        poll_interval = 2.0

        while True:
            status_resp = await gate.get_status(request_id)
            if status_resp.status != ApprovalStatus.PENDING:
                is_approved = status_resp.status == ApprovalStatus.APPROVED
                reason = status_resp.status.value
                if is_approved:
                    return ApprovalRequestResult(success=True, request_id=request_id)
                else:
                    return ApprovalRequestResult(
                        success=False, request_id=request_id, error=f"双人审批{reason}"
                    )

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return ApprovalRequestResult(
                    success=False, request_id=request_id, error="双人审批超时"
                )

            await asyncio.sleep(min(poll_interval, timeout - elapsed))

    def verify_token(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        context: dict,
    ) -> bool:
        """
        验证审批令牌（Tool 执行层调用）

        Tool 执行前应调用此方法确认拥有有效令牌。
        """
        risk_str = f"L{int(risk_level)}" if isinstance(risk_level, (int, RiskLevel)) else str(risk_level)
        token_key = f"{tool_name}:{risk_str}"
        tokens = context.get("approval_tokens", {})
        return tokens.get(token_key) is not None

    async def check_ddl_with_hook(
        self,
        sql: str,
        context: dict,
    ) -> HookResult:
        """
        通过 Hook 系统检查 DDL 语句

        在 SQL 执行前调用，触发 SQL_DDL_DETECTED 事件。
        """
        return await self.hook_engine.emit(
            HookEvent.SQL_DDL_DETECTED,
            payload={"sql_statement": sql, "params": context.get("params", {})},
            session_id=context.get("session_id", ""),
            user_id=context.get("user_id", ""),
        )


# 全局单例
_guard_rail: Optional[SafetyGuardRail] = None


def get_safety_guard_rail() -> SafetyGuardRail:
    global _guard_rail
    if _guard_rail is None:
        _guard_rail = SafetyGuardRail()
    return _guard_rail
