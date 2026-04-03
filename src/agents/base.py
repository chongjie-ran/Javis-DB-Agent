"""Agent基类"""
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass, field
import time
import logging

from src.llm.ollama_client import get_ollama_client, OllamaClient

logger = logging.getLogger(__name__)
from src.gateway.tool_registry import get_tool_registry, ToolRegistry
from src.gateway.policy_engine import get_policy_engine, PolicyEngine, PolicyContext, PolicyResult
from src.gateway.audit import get_audit_logger, AuditLogger, AuditAction
from src.gateway.hooks import HookEvent, emit_hook, get_hook_engine
from src.security.guard_rail import get_safety_guard_rail, ApprovalRequiredError
from src.tools.base import BaseTool, ToolResult, RiskLevel


@dataclass
class AgentResponse:
    """Agent响应"""
    success: bool
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    error: str = ""
    execution_time_ms: int = 0


class BaseAgent(ABC):
    """Agent基类"""
    
    name: str = "base"
    description: str = "基础Agent"
    system_prompt: str = ""
    available_tools: list[str] = []  # 可用工具名称列表
    max_iterations: int = 5
    timeout_seconds: int = 60
    
    def __init__(self, llm_provider=None):
        self._llm = llm_provider or get_ollama_client()
        self._registry = get_tool_registry()
        self._policy = get_policy_engine()
        self._audit = get_audit_logger()
    
    @abstractmethod
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        pass
    
    @abstractmethod
    async def _process_direct(self, goal: str, context: dict) -> AgentResponse:
        """直接处理（不使用工具时）"""
        pass
    
    async def process(self, goal: str, context: dict) -> AgentResponse:
        """处理任务入口"""
        start_time = time.time()
        session_id = context.get("session_id", "")
        user_id = context.get("user_id", "")
        
        self._audit.log_action(
            AuditAction.AGENT_INVOKE,
            user_id=user_id,
            session_id=session_id,
            agent_name=self.name,
            metadata={"goal": goal[:200]}
        )
        
        try:
            response = await self._process_direct(goal, context)
            response.execution_time_ms = int((time.time() - start_time) * 1000)
            return response
        except Exception as e:
            return AgentResponse(
                success=False,
                error=f"{self.name} 处理失败: {str(e)}",
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
    
    async def think(self, prompt: str, system: Optional[str] = None) -> str:
        """LLM推理（异常时优雅降级，返回结构化错误信息）"""
        sys_prompt = system or self._build_system_prompt()
        try:
            return await self._llm.complete(prompt, system=sys_prompt)
        except Exception as e:
            logger.warning(f"LLM调用失败，Agent={self.__class__.__name__}, error={e}")
            return f"[LLM调用失败] {type(e).__name__}: {str(e)[:200]}"
    
    async def think_stream(self, prompt: str, system: Optional[str] = None):
        """流式LLM推理"""
        sys_prompt = system or self._build_system_prompt()
        async for chunk in self._llm.complete_stream(prompt, system=sys_prompt):
            yield chunk
    
    async def call_tool(
        self,
        tool_name: str,
        params: dict,
        context: dict
    ) -> ToolResult:
        """调用工具（经过策略检查、Hook 事件、安全护栏）"""
        start_time = time.time()
        user_id = context.get("user_id", "")
        session_id = context.get("session_id", "")

        tool = self._registry.get_tool(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"工具不存在: {tool_name}",
                tool_name=tool_name
            )

        # 参数校验
        valid, err = tool.validate_params(params)
        if not valid:
            return ToolResult(success=False, error=err, tool_name=tool_name)

        # 策略检查
        risk_level = tool.get_risk_level()
        policy_ctx = PolicyContext(
            user_id=user_id,
            session_id=session_id
        )
        policy_result = self._policy.check(policy_ctx, f"tool.{tool_name}", risk_level)

        self._audit.log_action(
            AuditAction.TOOL_CALL,
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            risk_level=risk_level.value,
            params=params,
            result="policy_pass" if policy_result.allowed else "denied",
            metadata={"approval_required": policy_result.approval_required}
        )

        if not policy_result.allowed:
            return ToolResult(
                success=False,
                error=f"权限不足: {policy_result.reason}",
                tool_name=tool_name
            )

        # L5高风险工具：检查审批状态
        tool_call_id = f"call_{tool_name}_{user_id}_{int(start_time * 1000)}"
        if risk_level == RiskLevel.L5_HIGH:
            gate = self._policy.approval_gate
            if not gate.is_approved(tool_call_id):
                # 检查是否有待审批或已通过的记录
                status = gate.get_approval_status(tool_call_id)
                if status is None:
                    return ToolResult(
                        success=False,
                        error=f"L5高风险工具 [{tool_name}] 需要双人审批通过后方可执行，请先提交审批申请",
                        tool_name=tool_name
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"L5高风险工具 [{tool_name}] 审批状态: {status.value}，需双人审批通过",
                        tool_name=tool_name
                    )

        # ── F1: Hook TOOL_BEFORE_EXECUTE ──────────────────────────────────
        hook_context = context.copy()
        hook_context["params"] = params
        before_hook = await emit_hook(
            HookEvent.TOOL_BEFORE_EXECUTE,
            payload={
                "tool_name": tool_name,
                "params": params,
                "risk_level": risk_level.value if isinstance(risk_level, RiskLevel) else risk_level,
                "policy_allowed": policy_result.allowed,
            },
            session_id=session_id,
            user_id=user_id,
        )
        if before_hook.blocked:
            self._audit.log_action(
                AuditAction.TOOL_CALL,
                user_id=user_id,
                session_id=session_id,
                tool_name=tool_name,
                risk_level=str(risk_level),
                result="hook_blocked",
                metadata={"blocked_reason": before_hook.message},
            )
            return ToolResult(
                success=False,
                error=f"Hook 拦截: {before_hook.message}",
                tool_name=tool_name
            )

        # ── F3: SafetyGuardRail 强制审批检查（不可绕过）────────────────────
        try:
            guard_rail = get_safety_guard_rail()
            await guard_rail.enforce(
                tool_name=tool_name,
                risk_level=risk_level,
                context=context,
                timeout=300,
            )
        except ApprovalRequiredError as e:
            return ToolResult(
                success=False,
                error=str(e),
                tool_name=tool_name
            )

        # 前置检查
        pre_ok, pre_err = await tool.pre_execute(params, context)
        if not pre_ok:
            return ToolResult(success=False, error=pre_err, tool_name=tool_name)

        # 执行
        try:
            result = await tool.execute(params, context)
            result.execution_time_ms = int((time.time() - start_time) * 1000)
            result.tool_name = tool_name

            # L5高风险工具：标记已执行
            if risk_level == RiskLevel.L5_HIGH:
                self._policy.approval_gate.enforce_execution(
                    tool_call_id=tool_call_id,
                    executor=user_id,
                    result=f"{'success' if result.success else 'failure'}: {result.error or 'ok'}"
                )

            # 后置检查
            post_ok, post_err = await tool.post_execute(result)
            if not post_ok:
                result.success = False
                result.error = post_err

            self._audit.log_action(
                AuditAction.TOOL_RESULT,
                user_id=user_id,
                session_id=session_id,
                tool_name=tool_name,
                risk_level=risk_level.value,
                result="success" if result.success else "failure",
                error_message=result.error or "",
                duration_ms=result.execution_time_ms
            )

            # ── F1: Hook TOOL_AFTER_EXECUTE ────────────────────────────────
            await emit_hook(
                HookEvent.TOOL_AFTER_EXECUTE,
                payload={
                    "tool_name": tool_name,
                    "params": params,
                    "result": result.model_dump() if hasattr(result, "model_dump") else str(result),
                    "success": result.success,
                    "execution_time_ms": result.execution_time_ms,
                },
                session_id=session_id,
                user_id=user_id,
            )

            return result

        except Exception as e:
            # ── F1: Hook TOOL_ERROR ───────────────────────────────────────
            await emit_hook(
                HookEvent.TOOL_ERROR,
                payload={
                    "tool_name": tool_name,
                    "params": params,
                    "error": str(e),
                },
                session_id=session_id,
                user_id=user_id,
            )
            return ToolResult(
                success=False,
                error=str(e),
                tool_name=tool_name,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
    
    def get_available_tools(self) -> list[str]:
        """获取可用工具列表"""
        return [t for t in self.available_tools if self._registry.get_tool(t) is not None]
    
    def format_tool_call(self, tool_name: str, params: dict) -> str:
        """格式化工具调用"""
        import json
        return f"TOOL_CALL: {tool_name}\nPARAMS: {json.dumps(params, ensure_ascii=False)}"
