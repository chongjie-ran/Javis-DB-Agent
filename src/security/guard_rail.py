"""SafetyGuardRail - 不可绕过安全护栏"""
import hashlib
import logging
import time
from typing import Optional, Any
from dataclasses import dataclass, field

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


@dataclass
class ApprovalToken:
    """
    审批令牌（带 TTL 和参数哈希校验）

    存储在 context["approval_tokens"] 中，格式：
        token_key -> ApprovalToken
    """
    request_id: str
    tool_name: str
    risk_level: str
    params_hash: str          # 审批时的 params SHA256
    created_at: float        # 创建时间戳
    expires_at: float        # 过期时间戳
    approver: str = ""       # 审批人（用于审计）


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
        l4_ttl_seconds: Optional[int] = None,
        l5_ttl_seconds: Optional[int] = None,
    ):
        self._approval_gate = approval_gate
        self._hook_engine = hook_engine
        # 从 config.py 读取 TTL 配置
        from src.config import get_settings
        settings = get_settings()
        self._l4_ttl_seconds = l4_ttl_seconds if l4_ttl_seconds is not None else settings.approval_l4_ttl_seconds
        self._l5_ttl_seconds = l5_ttl_seconds if l5_ttl_seconds is not None else settings.approval_l5_ttl_seconds

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
        params = context.get("params", {})

        # 检查是否已有有效令牌（TTL + params_hash 校验）
        if self._validate_token(token_key, params, tokens):
            logger.debug(f"L4 token valid for {tool_name}, skipping approval")
            token: ApprovalToken = tokens[token_key]
            return GuardRailResult(
                allowed=True,
                approval_token=token.request_id,
                risk_level=risk_str,
                message="L4 approval token valid",
            )

        # 发起审批请求
        logger.info(f"L4 operation requires approval: {tool_name}")
        result = await self._request_approval(
            tool_name=tool_name,
            risk_level="L4",
            requester=context.get("user_id", "unknown"),
            params=params,
            timeout=timeout,
        )

        if not result.success:
            raise ApprovalRequiredError(
                f"L4 操作 {tool_name} 需要审批，当前未通过审批。"
                f"原因: {result.error}"
            )

        # 写入令牌（带 TTL）
        params_hash = self._hash_params(params)
        now = time.time()
        token = ApprovalToken(
            request_id=result.request_id,
            tool_name=tool_name,
            risk_level="L4",
            params_hash=params_hash,
            created_at=now,
            expires_at=now + self._l4_ttl_seconds,
            approver="",
        )
        tokens[token_key] = token
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
        params = context.get("params", {})

        # 检查是否已有有效令牌（TTL + params_hash 校验）
        if self._validate_token(token_key, params, tokens):
            logger.debug(f"L5 token valid for {tool_name}, skipping dual approval")
            token: ApprovalToken = tokens[token_key]
            return GuardRailResult(
                allowed=True,
                approval_token=token.request_id,
                risk_level=risk_str,
                message="L5 dual approval token valid",
            )

        # 发起双人审批请求
        logger.warning(f"L5 operation requires DUAL approval: {tool_name}")
        result = await self._request_dual_approval(
            tool_name=tool_name,
            risk_level="L5",
            requester=context.get("user_id", "unknown"),
            params=params,
            timeout=timeout,
        )

        if not result.success:
            raise ApprovalRequiredError(
                f"L5 操作 {tool_name} 需要双人审批，当前未通过。"
                f"原因: {result.error}"
            )

        # 写入令牌（带 TTL）
        params_hash = self._hash_params(params)
        now = time.time()
        token = ApprovalToken(
            request_id=result.request_id,
            tool_name=tool_name,
            risk_level="L5",
            params_hash=params_hash,
            created_at=now,
            expires_at=now + self._l5_ttl_seconds,
            approver="",
        )
        tokens[token_key] = token
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
        gate = self.approval_gate

        # 构建 context 供 ApprovalGate 使用
        context = {
            "user_id": requester,
            "risk_level": risk_level,
            "action": tool_name,
        }

        # 创建审批请求
        result = await gate.request_approval(
            action=tool_name,
            context=context,
            params=params,
        )

        if not result.success:
            return result

        # 带超时的等待循环
        import asyncio
        start_time = time.time()
        poll_interval = 2.0  # 每 2 秒轮询一次
        request_id = result.request_id

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
        gate = self.approval_gate

        context = {
            "user_id": requester,
            "risk_level": risk_level,
            "action": tool_name,
        }

        result = await gate.request_approval(
            action=tool_name,
            context=context,
            params=params,
        )

        if not result.success:
            return result

        # 带超时的等待循环
        import asyncio
        start_time = time.time()
        poll_interval = 2.0
        request_id = result.request_id

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

    def _hash_params(self, params: dict) -> str:
        """计算 params 的 SHA256 哈希（用于参数漂移检测）"""
        content = str(sorted(params.items()))
        return hashlib.sha256(content.encode()).hexdigest()

    def _validate_token(self, token_key: str, params: dict, tokens: dict) -> bool:
        """
        验证令牌有效性（TTL 过期 + 参数漂移检测）

        Args:
            token_key: 令牌 key
            params: 当前执行参数
            tokens: 令牌字典

        Returns:
            True 表示令牌有效，False 表示无效（需重新审批）
        """
        token = tokens.get(token_key)
        if not token:
            return False

        # TTL 过期检查
        if time.time() > token.expires_at:
            logger.info(f"Token expired for {token_key}, removing")
            tokens.pop(token_key, None)
            return False

        # 参数漂移检测
        current_hash = self._hash_params(params)
        if current_hash != token.params_hash:
            logger.warning(
                f"Params drift detected for {token_key}: "
                f"approved={token.params_hash[:8]}... current={current_hash[:8]}..."
            )
            tokens.pop(token_key, None)
            return False

        return True

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
        params = context.get("params", {})
        return self._validate_token(token_key, params, tokens)

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
