"""ObservabilityManager - 可观测性框架统一管理器
负责初始化和编排 Tracer / Metrics / Logger 三大组件
并与 HookEngine 深度集成，实现自动埋点
"""
import time
import logging
from typing import Optional

from .tracer import JavisTracer, SpanKind, get_tracer, get_current_trace_id, get_current_span
from .metrics import AgentMetricsCollector, ToolMetricsCollector, get_agent_metrics, get_tool_metrics
from .structured_logger import StructuredLogger, get_structured_logger

logger = logging.getLogger(__name__)


class ObservabilityManager:
    """
    可观测性统一管理器

    功能：
    1. 初始化 Tracer / Metrics / Logger 三大组件
    2. 与 HookEngine 集成，自动记录 TOOL_BEFORE/AFTER_EXECUTE / AGENT_BEFORE/AFTER_INVOKE
    3. 提供统一的配置接口
    4. 支持 Prometheus 格式指标导出
    5. 支持 OpenTelemetry 格式 Trace 导出

    使用方式：
        obs = get_observability_manager()
        obs.setup_hook_integration()  # 挂载 Hook 埋点

        # Agent 执行
        with obs.tracer.trace("my_agent", SpanKind.AGENT):
            ...

        # Tool 执行
        obs.record_tool_call("execute_sql", success=True, duration_seconds=0.05)
    """

    def __init__(
        self,
        service_name: str = "javis-db-agent",
        enable_tracer: bool = True,
        enable_metrics: bool = True,
        enable_logger: bool = True,
    ):
        self._service_name = service_name
        self._enable_tracer = enable_tracer
        self._enable_metrics = enable_metrics
        self._enable_logger = enable_logger
        self._hook_integrated = False

        # 初始化组件
        self._tracer: Optional[JavisTracer] = get_tracer(service_name) if enable_tracer else None
        self._agent_metrics: Optional[AgentMetricsCollector] = get_agent_metrics() if enable_metrics else None
        self._tool_metrics: Optional[ToolMetricsCollector] = get_tool_metrics() if enable_metrics else None
        self._structured_logger: Optional[StructuredLogger] = get_structured_logger(service_name) if enable_logger else None

    # ── 组件访问 ─────────────────────────────────────────────────────────────

    @property
    def tracer(self) -> Optional[JavisTracer]:
        return self._tracer

    @property
    def agent_metrics(self) -> Optional[AgentMetricsCollector]:
        return self._agent_metrics

    @property
    def tool_metrics(self) -> Optional[ToolMetricsCollector]:
        return self._tool_metrics

    @property
    def structured_logger(self) -> Optional[StructuredLogger]:
        return self._structured_logger

    # ── Hook 系统集成 ────────────────────────────────────────────────────────

    def setup_hook_integration(self):
        """
        将可观测性埋点注入到 HookEngine

        注入内容：
        - TOOL_BEFORE_EXECUTE: 记录开始 Span / Metrics
        - TOOL_AFTER_EXECUTE: 记录结束 Span / Metrics
        - TOOL_ERROR: 记录错误 Span / Metrics
        - AGENT_BEFORE_INVOKE: 记录 Agent Span 开始
        - AGENT_AFTER_INVOKE: 记录 Agent Span 结束
        """
        if self._hook_integrated:
            logger.warning("Hook integration already set up, skipping.")
            return

        try:
            from src.gateway.hooks import HookEvent, emit_hook, get_hook_engine
            from src.gateway.hooks.hook_rule import HookRule, HookAction
            from src.gateway.hooks.hook_registry import get_hook_registry
        except ImportError as e:
            logger.warning(f"Hook system not importable, observability integration skipped: {e}")
            return

        registry = get_hook_registry()

        # ── TOOL_BEFORE_EXECUTE 埋点 ────────────────────────────────────────
        before_tool_rule = HookRule(
            name="obs_tool_before_execute",
            event=HookEvent.TOOL_BEFORE_EXECUTE,
            action=HookAction.ALLOW,  # 只记录，不阻断
            enabled=True,
            handler=self._on_tool_before_execute,
            description="Observability: trace + metrics for tool before execute",
        )
        registry.register(before_tool_rule)

        # ── TOOL_AFTER_EXECUTE 埋点 ──────────────────────────────────────────
        after_tool_rule = HookRule(
            name="obs_tool_after_execute",
            event=HookEvent.TOOL_AFTER_EXECUTE,
            action=HookAction.ALLOW,
            enabled=True,
            handler=self._on_tool_after_execute,
            description="Observability: trace + metrics for tool after execute",
        )
        registry.register(after_tool_rule)

        # ── TOOL_ERROR 埋点 ───────────────────────────────────────────────────
        error_tool_rule = HookRule(
            name="obs_tool_error",
            event=HookEvent.TOOL_ERROR,
            action=HookAction.ALLOW,
            enabled=True,
            handler=self._on_tool_error,
            description="Observability: trace error for tool execution",
        )
        registry.register(error_tool_rule)

        # ── AGENT_BEFORE_INVOKE 埋点 ─────────────────────────────────────────
        before_agent_rule = HookRule(
            name="obs_agent_before_invoke",
            event=HookEvent.AGENT_BEFORE_INVOKE,
            action=HookAction.ALLOW,
            enabled=True,
            handler=self._on_agent_before_invoke,
            description="Observability: trace + metrics for agent before invoke",
        )
        registry.register(before_agent_rule)

        # ── AGENT_AFTER_INVOKE 埋点 ──────────────────────────────────────────
        after_agent_rule = HookRule(
            name="obs_agent_after_invoke",
            event=HookEvent.AGENT_AFTER_INVOKE,
            action=HookAction.ALLOW,
            enabled=True,
            handler=self._on_agent_after_invoke,
            description="Observability: trace + metrics for agent after invoke",
        )
        registry.register(after_agent_rule)

        self._hook_integrated = True
        logger.info("Observability hook integration complete: TOOL_BEFORE/AFTER/ERROR + AGENT_BEFORE/AFTER")

    # ── Hook Handlers ─────────────────────────────────────────────────────────

    def _on_tool_before_execute(self, context: "HookContext") -> "HookContext":
        """TOOL_BEFORE_EXECUTE 埋点"""
        start = time.time()
        payload = context.payload or {}
        tool_name = payload.get("tool_name", "unknown")

        # Tracer: 启动 Span
        if self._tracer:
            span = self._tracer.start_span(
                name=f"tool:{tool_name}",
                kind=SpanKind.TOOL,
                attributes={
                    "tool.name": tool_name,
                    "tool.risk_level": payload.get("risk_level", "unknown"),
                    "tool.policy_allowed": payload.get("policy_allowed", True),
                },
            )
            context.extra["_obs_span"] = span
            context.extra["_obs_start"] = start

        # Structured Logger
        if self._structured_logger:
            self._structured_logger.log_hook_event(
                event=HookEvent.TOOL_BEFORE_EXECUTE.value,
                session_id=context.session_id,
                user_id=context.user_id,
                blocked=context.blocked,
                message=context.blocked_reason,
                warnings=list(context.warnings),
                matched_rules=[],  # 从 context 传入时 matched_rules 已在 context 中
                duration_ms=0.0,
                payload={"tool_name": tool_name, "risk_level": payload.get("risk_level")},
            )

        return context

    def _on_tool_after_execute(self, context: "HookContext") -> "HookContext":
        """TOOL_AFTER_EXECUTE 埋点"""
        start = time.time()
        payload = context.payload or {}
        tool_name = payload.get("tool_name", "unknown")
        success = payload.get("success", True)
        duration_ms = payload.get("execution_time_ms", 0.0)
        result_data = payload.get("result", {})

        # Tracer: 结束 Span
        if self._tracer:
            span = context.extra.get("_obs_span")
            if span:
                span.set_attribute("tool.success", success)
                span.set_attribute("tool.duration_ms", duration_ms)
                if result_data and isinstance(result_data, dict):
                    span.set_attribute("tool.result_keys", list(result_data.keys()))
                self._tracer.end_span(span, status="ok" if success else "error")

        # Metrics
        if self._tool_metrics:
            self._tool_metrics.record_call(
                tool_name=tool_name,
                success=success,
                duration_seconds=duration_ms / 1000.0 if duration_ms else 0.0,
            )

        # Structured Logger
        if self._structured_logger:
            self._structured_logger.log_hook_event(
                event=HookEvent.TOOL_AFTER_EXECUTE.value,
                session_id=context.session_id,
                user_id=context.user_id,
                blocked=context.blocked,
                message=context.blocked_reason,
                duration_ms=time.time() - start,
                payload={
                    "tool_name": tool_name,
                    "success": success,
                    "execution_time_ms": duration_ms,
                },
            )

        return context

    def _on_tool_error(self, context: "HookContext") -> "HookContext":
        """TOOL_ERROR 埋点"""
        payload = context.payload or {}
        tool_name = payload.get("tool_name", "unknown")
        error_msg = payload.get("error", "unknown")

        # Tracer: 结束 Span 为 error 状态
        if self._tracer:
            span = context.extra.get("_obs_span")
            if span:
                self._tracer.end_span(span, status="error", error_message=error_msg)

        # Metrics
        if self._tool_metrics:
            self._tool_metrics.record_call(
                tool_name=tool_name,
                success=False,
                duration_seconds=0.0,
                error=error_msg,
            )

        # Structured Logger
        if self._structured_logger:
            self._structured_logger.log_hook_event(
                event=HookEvent.TOOL_ERROR.value,
                session_id=context.session_id,
                user_id=context.user_id,
                blocked=False,
                message=error_msg,
                duration_ms=0.0,
                payload={"tool_name": tool_name, "error": error_msg},
            )

        return context

    def _on_agent_before_invoke(self, context: "HookContext") -> "HookContext":
        """AGENT_BEFORE_INVOKE 埋点"""
        payload = context.payload or {}
        agent_name = payload.get("agent_name", "unknown")
        goal = payload.get("goal", "")

        # Tracer
        if self._tracer:
            span = self._tracer.start_span(
                name=f"agent:{agent_name}",
                kind=SpanKind.AGENT,
                attributes={
                    "agent.name": agent_name,
                    "agent.goal": goal[:100],  # 截断
                },
            )
            context.extra["_obs_span"] = span

        # Metrics
        if self._agent_metrics:
            self._agent_metrics.inc_active()

        # Structured Logger
        if self._structured_logger:
            self._structured_logger.log_agent_decision(
                agent_name=agent_name,
                session_id=context.session_id,
                user_id=context.user_id,
                decision_type="invoke_start",
                decision_data={"goal": goal[:200]},
                goal=goal,
                success=True,
                trace_id=get_current_trace_id() or "",
            )

        return context

    def _on_agent_after_invoke(self, context: "HookContext") -> "HookContext":
        """AGENT_AFTER_INVOKE 埋点"""
        payload = context.payload or {}
        agent_name = payload.get("agent_name", "unknown")
        goal = payload.get("goal", "")
        success = payload.get("success", True)
        execution_time_ms = payload.get("execution_time_ms", 0)

        # Tracer
        if self._tracer:
            span = context.extra.get("_obs_span")
            if span:
                span.set_attribute("agent.success", success)
                span.set_attribute("agent.execution_time_ms", execution_time_ms)
                self._tracer.end_span(span, status="ok" if success else "error")

        # Metrics
        if self._agent_metrics:
            self._agent_metrics.record_invocation(
                agent_name=agent_name,
                success=success,
                duration_seconds=execution_time_ms / 1000.0 if execution_time_ms else 0.0,
            )
            self._agent_metrics.dec_active()

        # Structured Logger
        if self._structured_logger:
            self._structured_logger.log_agent_decision(
                agent_name=agent_name,
                session_id=context.session_id,
                user_id=context.user_id,
                decision_type="invoke_complete",
                decision_data={"success": success, "execution_time_ms": execution_time_ms},
                goal=goal,
                success=success,
                execution_time_ms=execution_time_ms,
                trace_id=get_current_trace_id() or "",
            )

        return context

    # ── 主动记录接口 ────────────────────────────────────────────────────────

    def record_agent_invocation(
        self,
        agent_name: str,
        session_id: str,
        user_id: str,
        success: bool = True,
        execution_time_ms: int = 0,
        goal: str = "",
        decision_type: str = "direct",
    ):
        """主动记录 Agent 调用（用于未通过 Hook 系统但需要记录的场景）"""
        if self._agent_metrics:
            self._agent_metrics.record_invocation(
                agent_name=agent_name,
                success=success,
                duration_seconds=execution_time_ms / 1000.0,
            )

        if self._structured_logger:
            self._structured_logger.log_agent_decision(
                agent_name=agent_name,
                session_id=session_id,
                user_id=user_id,
                decision_type=decision_type,
                decision_data={"success": success, "execution_time_ms": execution_time_ms},
                goal=goal,
                success=success,
                execution_time_ms=execution_time_ms,
                trace_id=get_current_trace_id() or "",
            )

    def record_tool_call(
        self,
        tool_name: str,
        success: bool = True,
        duration_seconds: float = 0.0,
        error: str = "",
        session_id: str = "",
        user_id: str = "",
    ):
        """主动记录 Tool 调用"""
        if self._tool_metrics:
            self._tool_metrics.record_call(
                tool_name=tool_name,
                success=success,
                duration_seconds=duration_seconds,
                error=error,
            )

        if self._structured_logger:
            self._structured_logger.log_hook_event(
                event="tool:direct_call",
                session_id=session_id,
                user_id=user_id,
                blocked=False,
                message=error if not success else "",
                duration_ms=duration_seconds * 1000,
                payload={"tool_name": tool_name, "success": success, "error": error},
            )

    def record_agent_decision(
        self,
        agent_name: str,
        session_id: str,
        user_id: str,
        decision_type: str,
        decision_data: dict,
        goal: str = "",
        success: bool = True,
        execution_time_ms: int = 0,
    ):
        """记录 Agent 决策（工具选择 / LLM 响应 / 路由 / 降级）"""
        if self._structured_logger:
            self._structured_logger.log_agent_decision(
                agent_name=agent_name,
                session_id=session_id,
                user_id=user_id,
                decision_type=decision_type,
                decision_data=decision_data,
                goal=goal,
                success=success,
                execution_time_ms=execution_time_ms,
                trace_id=get_current_trace_id() or "",
            )

    # ── 导出接口 ────────────────────────────────────────────────────────────

    def export_traces_otel(self) -> dict:
        """导出 Trace 为 OpenTelemetry 格式"""
        if self._tracer:
            return self._tracer.export_otel_dict()
        return {}

    def export_metrics_prometheus(self) -> str:
        """导出 Metrics 为 Prometheus 格式"""
        parts = []
        if self._agent_metrics:
            parts.append("# === Agent Metrics ===")
            parts.append(self._agent_metrics.render_prometheus())
        if self._tool_metrics:
            parts.append("# === Tool Metrics ===")
            parts.append(self._tool_metrics.render_prometheus())
        return "\n".join(parts)

    def get_all_summaries(self) -> dict:
        """获取所有组件的摘要"""
        summaries = {}
        if self._agent_metrics:
            summaries["agent"] = self._agent_metrics.get_summary()
        if self._tool_metrics:
            summaries["tool"] = self._tool_metrics.get_summary()
        if self._tracer:
            summaries["tracer"] = {
                "total_spans": len(self._tracer.spans),
                "active_span": get_current_span() is not None,
                "trace_id": get_current_trace_id(),
            }
        return summaries

    def reset(self):
        """重置所有指标和 Trace（用于测试）"""
        if self._agent_metrics:
            self._agent_metrics.reset()
        if self._tool_metrics:
            self._tool_metrics.reset()
        if self._tracer:
            self._tracer.clear()


# ── 全局单例 ─────────────────────────────────────────────────────────────────

_observability_manager: Optional[ObservabilityManager] = None


def get_observability_manager(
    service_name: str = "javis-db-agent",
    enable_tracer: bool = True,
    enable_metrics: bool = True,
    enable_logger: bool = True,
) -> ObservabilityManager:
    global _observability_manager
    if _observability_manager is None:
        _observability_manager = ObservabilityManager(
            service_name=service_name,
            enable_tracer=enable_tracer,
            enable_metrics=enable_metrics,
            enable_logger=enable_logger,
        )
    return _observability_manager


def reset_observability_manager():
    """重置全局管理器（用于测试）"""
    global _observability_manager
    if _observability_manager:
        _observability_manager.reset()
    _observability_manager = None
