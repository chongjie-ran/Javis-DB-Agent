"""可观测性框架 - Javis-DB-Agent V2.6 R3
提供 Tracer / Metrics / Logger 三大能力
"""
from .tracer import (
    JavisTracer,
    Span,
    SpanKind,
    get_tracer,
    TraceContext,
)
from .metrics import (
    AgentMetricsCollector,
    ToolMetricsCollector,
    get_agent_metrics,
    get_tool_metrics,
)
from .structured_logger import (
    StructuredLogger,
    AgentDecisionLog,
    HookEventLog,
    get_structured_logger,
)
from .observability_manager import (
    ObservabilityManager,
    get_observability_manager,
)
from .metrics import (
    TokenBudgetTracker,
    HookMetricsCollector,
    get_token_tracker,
    get_hook_metrics,
)

__all__ = [
    # Tracer
    "JavisTracer",
    "Span",
    "SpanKind",
    "get_tracer",
    "TraceContext",
    # Metrics
    "AgentMetricsCollector",
    "ToolMetricsCollector",
    "get_agent_metrics",
    "get_tool_metrics",
    # Logger
    "StructuredLogger",
    "AgentDecisionLog",
    "HookEventLog",
    "TokenBudgetTracker",
    "HookMetricsCollector",
    "get_token_tracker",
    "get_hook_metrics",
    "get_structured_logger",
    # Manager
    "ObservabilityManager",
    "get_observability_manager",
]
