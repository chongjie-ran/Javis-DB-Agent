"""Tracer - OpenTelemetry 集成 / Span 生命周期管理 / Trace Context 传播"""
import time
import uuid
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# ── Trace Context（线程安全，ContextVar 支持 async）────────────────────────────────

_current_span: ContextVar[Optional["Span"]] = ContextVar("current_span", default=None)
_current_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def get_current_trace_id() -> Optional[str]:
    """获取当前 Trace ID"""
    return _current_trace_id.get()


def get_current_span() -> Optional["Span"]:
    """获取当前活跃 Span"""
    return _current_span.get()


class SpanKind(str, Enum):
    """Span 类型"""
    INTERNAL = "internal"
    AGENT = "agent"              # Agent 生命周期
    TOOL = "tool"                # Tool 调用
    LLM = "llm"                  # LLM 推理
    HOOK = "hook"                # Hook 执行
    DB = "db"                    # 数据库操作
    HTTP = "http"                # HTTP 请求


@dataclass
class Span:
    """
    Trace Span

    Attributes:
        name: Span 名称
        trace_id: Trace ID（全局唯一）
        span_id: Span ID
        parent_id: 父 Span ID（顶层为 None）
        kind: Span 类型
        start_time: 开始时间（epoch 秒）
        end_time: 结束时间（epoch 秒，None 表示未结束）
        attributes: 属性字典
        events: 子事件列表
        status: 状态（ok / error）
        error_message: 错误信息（如果有）
    """
    name: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    parent_id: Optional[str] = None
    kind: SpanKind = SpanKind.INTERNAL
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    status: str = "ok"
    error_message: str = ""

    @property
    def duration_ms(self) -> float:
        """Span 耗时（毫秒）"""
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def set_attribute(self, key: str, value: Any) -> "Span":
        """设置属性"""
        self.attributes[key] = value
        return self

    def add_event(self, name: str, attributes: Optional[dict] = None) -> "Span":
        """添加子事件"""
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })
        return self

    def end(self, status: str = "ok", error_message: str = "") -> None:
        """结束 Span"""
        if self.end_time is not None:
            return  # 防止重复 end
        self.end_time = time.time()
        self.status = status
        self.error_message = error_message

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "kind": self.kind.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": self.events,
            "status": self.status,
            "error_message": self.error_message,
        }


class TraceContext:
    """
    Trace Context 传播载体

    用于在进程间（HTTP Header / MQ Message / DB Column）传播 trace 上下文。
    格式：trace_id:span_id:parent_id
    """

    SEPARATOR = ":"

    @classmethod
    def inject(cls, span: Span) -> str:
        """将 Span 序列化为传播字符串"""
        parts = [span.trace_id, span.span_id]
        if span.parent_id:
            parts.append(span.parent_id)
        return cls.SEPARATOR.join(parts)

    @classmethod
    def extract(cls, carrier: str) -> dict:
        """从传播字符串解析 Trace Context"""
        parts = carrier.split(cls.SEPARATOR)
        return {
            "trace_id": parts[0] if len(parts) > 0 else None,
            "span_id": parts[1] if len(parts) > 1 else None,
            "parent_id": parts[2] if len(parts) > 2 else None,
        }

    @classmethod
    def inject_span(cls, trace_id: str, span_id: str, parent_id: Optional[str] = None) -> "Span":
        """从传播信息创建 Span（用于接收下游请求）"""
        return Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_id=parent_id,
        )


class JavisTracer:
    """
    OpenTelemetry 风格的 Tracer 实现

    特性：
    - Span 生命周期管理（start/end）
    - ContextVar 自动传播（无需手动传递）
    - Span 属性 / 事件 / 状态管理
    - Trace Context 注入/提取（跨进程传播）
    - OpenTelemetry 兼容格式导出
    """

    def __init__(self, service_name: str = "javis-db-agent"):
        self._service_name = service_name
        self._span_store: list[Span] = []

    # ── Span 管理 ─────────────────────────────────────────────────────────────

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Optional[Span] = None,
        attributes: Optional[dict] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Span:
        """
        启动一个新 Span

        Args:
            name: Span 名称
            kind: Span 类型
            parent: 父 Span（从 ContextVar 自动获取）
            attributes: 初始属性
            trace_id: 指定 trace_id（用于跨进程接收）
            span_id: 指定 span_id（用于跨进程接收）
            parent_id: 指定 parent_id（用于跨进程接收）

        Returns:
            Span 实例
        """
        # 确定父 Span
        if parent is None:
            parent = _current_span.get()

        # 确定 trace_id
        if trace_id is None:
            trace_id = parent.trace_id if parent else uuid.uuid4().hex[:16]

        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id or uuid.uuid4().hex[:8],
            parent_id=parent_id or (parent.span_id if parent else None),
            kind=kind,
            attributes=dict(attributes) if attributes else {},
        )

        # 自动传播到 ContextVar
        token = _current_trace_id.set(trace_id)
        _current_span.set(span)

        self._span_store.append(span)
        return span

    def end_span(self, span: Span, status: str = "ok", error_message: str = "") -> None:
        """结束 Span"""
        span.end(status=status, error_message=error_message)
        _current_span.set(None)
        _current_trace_id.set(None)

    @property
    def spans(self) -> list[Span]:
        """获取所有已记录的 Span"""
        return list(self._span_store)

    def clear(self) -> None:
        """清空所有 Span（用于测试）"""
        self._span_store.clear()
        _current_span.set(None)
        _current_trace_id.set(None)

    # ── Context Manager 风格的 Span ───────────────────────────────────────────

    def trace(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[dict] = None,
    ) -> "_SpanContext":
        """Context Manager 方式使用 Span"""
        return _SpanContext(self, name, kind, attributes)

    # ── OpenTelemetry 兼容导出 ─────────────────────────────────────────────────

    def export_otel_dict(self) -> dict:
        """
        导出为 OpenTelemetry ResourceSpans 兼容格式

        可对接 jaeger-agent / otel-collector / Tempo 等后端
        """
        _version = "2.6.3"

        spans_data = []
        for span in self._span_store:
            if span.end_time is None:
                continue  # 跳过未结束的 Span
            spans_data.append({
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "parent_span_id": span.parent_id or "",
                "name": span.name,
                "kind": span.kind.value.upper() if hasattr(span.kind, "value") else str(span.kind).upper(),
                "start_time_unix_nano": int(span.start_time * 1e9),
                "end_time_unix_nano": int(span.end_time * 1e9),
                "attributes": [
                    {"key": k, "value": {"string_value": str(v)}}
                    for k, v in span.attributes.items()
                ],
                "events": [
                    {
                        "time_unix_nano": int(e["timestamp"] * 1e9),
                        "name": e["name"],
                        "attributes": [
                            {"key": k, "value": {"string_value": str(v)}}
                            for k, v in (e.get("attributes") or {}).items()
                        ],
                    }
                    for e in span.events
                ],
                "status": {"code": 1 if span.status == "ok" else 2, "message": span.error_message},
            })

        return {
            "resourceSpans": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"string_value": self._service_name}},
                        {"key": "service.version", "value": {"string_value": _version}},
                    ]
                },
                "scopeSpans": [{
                    "scope": {"name": "javis-tracer", "version": "1.0.0"},
                    "spans": spans_data,
                }],
            }]
        }


class _SpanContext:
    """Span Context Manager"""

    def __init__(
        self,
        tracer: JavisTracer,
        name: str,
        kind: SpanKind,
        attributes: Optional[dict],
    ):
        self._tracer = tracer
        self._name = name
        self._kind = kind
        self._attributes = attributes
        self._span: Optional[Span] = None
        self._status = "ok"
        self._error_message = ""

    def __enter__(self) -> Span:
        self._span = self._tracer.start_span(
            name=self._name,
            kind=self._kind,
            attributes=self._attributes,
        )
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._status = "error"
            self._error_message = str(exc_val) if exc_val else "unknown error"
        self._tracer.end_span(self._span, status=self._status, error_message=self._error_message)
        return False  # 不吞掉异常


# ── 全局单例 ─────────────────────────────────────────────────────────────────

_tracer: Optional[JavisTracer] = None


def get_tracer(service_name: str = "javis-db-agent") -> JavisTracer:
    global _tracer
    if _tracer is None:
        _tracer = JavisTracer(service_name=service_name)
    return _tracer
