"""Metrics - Agent / Tool 执行指标收集器
提供执行计数、响应时间直方图、错误率计数器
"""
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


# ── 基础指标类型 ─────────────────────────────────────────────────────────────

@dataclass
class SimpleCounter:
    """简单计数器（线程安全）"""
    value: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, n: int = 1):
        with self._lock:
            self.value += n

    def get(self) -> int:
        return self.value

    def reset(self):
        with self._lock:
            self.value = 0


@dataclass
class SimpleHistogram:
    """
    简单直方图（延迟分布）

    预定义 buckets（毫秒）：
    10, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000, 60000
    """
    buckets: dict[float, int] = field(default_factory=lambda: {
        0.010: 0, 0.050: 0, 0.100: 0, 0.200: 0, 0.500: 0,
        1.000: 0, 2.000: 0, 5.000: 0, 10.000: 0, 30.000: 0, 60.000: 0,
    })
    sum: float = 0.0
    count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float):
        """记录观测值（秒）"""
        with self._lock:
            self.sum += value
            self.count += 1
            for boundary in self.buckets:
                if value <= boundary:
                    self.buckets[boundary] += 1

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "count": self.count,
                "sum": self.sum,
                "avg": self.sum / self.count if self.count > 0 else 0.0,
                "buckets": dict(self.buckets),
            }


# ── Agent 指标收集器 ──────────────────────────────────────────────────────────

class AgentMetricsCollector:
    """
    Agent 执行指标收集器

    指标类型：
    - agent_invocations_total: Agent 调用总次数（Counter，按 agent_name 标签）
    - agent_errors_total: Agent 错误次数（Counter）
    - agent_duration_seconds: Agent 执行时间直方图（Histogram）
    - agent_active: 当前活跃 Agent 数量（Gauge）
    """

    METRIC_INVOCATIONS = "agent_invocations_total"
    METRIC_ERRORS = "agent_errors_total"
    METRIC_DURATION = "agent_duration_seconds"
    METRIC_ACTIVE = "agent_active"

    def __init__(self):
        # 全局计数器（按 agent_name）
        self._counters: dict[str, SimpleCounter] = defaultdict(SimpleCounter)
        self._errors: dict[str, SimpleCounter] = defaultdict(SimpleCounter)
        # 全局直方图
        self._histogram = SimpleHistogram()
        # 活跃数
        self._active = SimpleCounter()
        self._lock = threading.Lock()
        self._start_time = time.time()

    # ── 记录 ─────────────────────────────────────────────────────────────────

    def record_invocation(self, agent_name: str, success: bool = True, duration_seconds: float = 0.0):
        """记录一次 Agent 调用"""
        with self._lock:
            self._counters[agent_name].inc()
            if not success:
                self._errors[agent_name].inc()
            if duration_seconds > 0:
                self._histogram.observe(duration_seconds)

    def inc_active(self):
        self._active.inc()

    def dec_active(self):
        self._active.inc(-1)

    # ── 查询 ─────────────────────────────────────────────────────────────────

    def get_total_invocations(self, agent_name: Optional[str] = None) -> int:
        if agent_name:
            return self._counters[agent_name].get()
        return sum(c.get() for c in self._counters.values())

    def get_total_errors(self, agent_name: Optional[str] = None) -> int:
        if agent_name:
            return self._errors[agent_name].get()
        return sum(e.get() for e in self._errors.values())

    def get_error_rate(self, agent_name: Optional[str] = None) -> float:
        total = self.get_total_invocations(agent_name)
        errors = self.get_total_errors(agent_name)
        return (errors / total * 100) if total > 0 else 0.0

    def get_duration_stats(self) -> dict:
        return self._histogram.get_stats()

    def get_active_count(self) -> int:
        return max(0, self._active.get())

    def get_summary(self, agent_name: Optional[str] = None) -> dict:
        """获取指标摘要"""
        total = self.get_total_invocations(agent_name)
        errors = self.get_total_errors(agent_name)
        stats = self._histogram.get_stats()
        return {
            "agent_name": agent_name or "all",
            "invocations_total": total,
            "errors_total": errors,
            "error_rate_percent": round((errors / total * 100) if total > 0 else 0.0, 2),
            "latency_avg_ms": round((stats["sum"] / stats["count"] * 1000) if stats["count"] > 0 else 0.0, 3),
            "latency_count": stats["count"],
            "active_agents": self.get_active_count(),
        }

    def reset(self):
        """重置所有指标"""
        with self._lock:
            self._counters.clear()
            self._errors.clear()
            self._histogram = SimpleHistogram()
            self._active = SimpleCounter()

    def render_prometheus(self) -> str:
        """Prometheus 格式输出"""
        lines = []
        lines.append("# HELP agent_invocations_total Total agent invocations")
        lines.append("# TYPE agent_invocations_total counter")
        for name, counter in sorted(self._counters.items()):
            lines.append(f'agent_invocations_total{{agent_name="{name}"}} {counter.get()}')

        lines.append("# HELP agent_errors_total Total agent errors")
        lines.append("# TYPE agent_errors_total counter")
        for name, counter in sorted(self._errors.items()):
            lines.append(f'agent_errors_total{{agent_name="{name}"}} {counter.get()}')

        stats = self._histogram.get_stats()
        lines.append("# HELP agent_duration_seconds Agent execution duration in seconds")
        lines.append("# TYPE agent_duration_seconds histogram")
        for le, count in sorted(stats["buckets"].items()):
            lines.append(f'agent_duration_seconds_bucket{{le="{le}"}} {count}')
        lines.append(f'agent_duration_seconds_count {stats["count"]}')
        lines.append(f'agent_duration_seconds_sum {stats["sum"]:.6f}')

        lines.append("# HELP agent_active Current active agent invocations")
        lines.append("# TYPE agent_active gauge")
        lines.append(f"agent_active {self.get_active_count()}")

        return "\n".join(lines) + "\n"


# ── Tool 指标收集器 ───────────────────────────────────────────────────────────

class ToolMetricsCollector:
    """
    Tool 执行指标收集器

    指标类型：
    - tool_calls_total: Tool 调用总次数（Counter，按 tool_name 标签）
    - tool_errors_total: Tool 错误次数（Counter）
    - tool_duration_seconds: Tool 执行时间直方图（Histogram）
    - tool_active: 当前活跃 Tool 调用数量（Gauge）
    """

    def __init__(self):
        self._counters: dict[str, SimpleCounter] = defaultdict(SimpleCounter)
        self._errors: dict[str, SimpleCounter] = defaultdict(SimpleCounter)
        self._histogram = SimpleHistogram()
        self._active = SimpleCounter()
        self._lock = threading.Lock()

    def record_call(
        self,
        tool_name: str,
        success: bool = True,
        duration_seconds: float = 0.0,
        error: str = "",
    ):
        """记录一次 Tool 调用"""
        with self._lock:
            self._counters[tool_name].inc()
            if not success:
                self._errors[tool_name].inc()
            if duration_seconds > 0:
                self._histogram.observe(duration_seconds)

    def get_total_calls(self, tool_name: Optional[str] = None) -> int:
        if tool_name:
            return self._counters[tool_name].get()
        return sum(c.get() for c in self._counters.values())

    def get_total_errors(self, tool_name: Optional[str] = None) -> int:
        if tool_name:
            return self._errors[tool_name].get()
        return sum(e.get() for e in self._errors.values())

    def get_error_rate(self, tool_name: Optional[str] = None) -> float:
        total = self.get_total_calls(tool_name)
        errors = self.get_total_errors(tool_name)
        return (errors / total * 100) if total > 0 else 0.0

    def get_duration_stats(self) -> dict:
        return self._histogram.get_stats()

    def get_summary(self, tool_name: Optional[str] = None) -> dict:
        total = self.get_total_calls(tool_name)
        errors = self.get_total_errors(tool_name)
        stats = self._histogram.get_stats()
        return {
            "tool_name": tool_name or "all",
            "calls_total": total,
            "errors_total": errors,
            "error_rate_percent": round((errors / total * 100) if total > 0 else 0.0, 2),
            "latency_avg_ms": round((stats["sum"] / stats["count"] * 1000) if stats["count"] > 0 else 0.0, 3),
            "latency_count": stats["count"],
        }

    def reset(self):
        with self._lock:
            self._counters.clear()
            self._errors.clear()
            self._histogram = SimpleHistogram()
            self._active = SimpleCounter()

    def render_prometheus(self) -> str:
        """Prometheus 格式输出"""
        lines = []
        lines.append("# HELP tool_calls_total Total tool calls")
        lines.append("# TYPE tool_calls_total counter")
        for name, counter in sorted(self._counters.items()):
            lines.append(f'tool_calls_total{{tool_name="{name}"}} {counter.get()}')

        lines.append("# HELP tool_errors_total Total tool errors")
        lines.append("# TYPE tool_errors_total counter")
        for name, counter in sorted(self._errors.items()):
            lines.append(f'tool_errors_total{{tool_name="{name}"}} {counter.get()}')

        stats = self._histogram.get_stats()
        lines.append("# HELP tool_duration_seconds Tool execution duration in seconds")
        lines.append("# TYPE tool_duration_seconds histogram")
        for le, count in sorted(stats["buckets"].items()):
            lines.append(f'tool_duration_seconds_bucket{{le="{le}"}} {count}')
        lines.append(f'tool_duration_seconds_count {stats["count"]}')
        lines.append(f'tool_duration_seconds_sum {stats["sum"]:.6f}')

        return "\n".join(lines) + "\n"


# ── 全局单例 ─────────────────────────────────────────────────────────────────

_agent_metrics: Optional[AgentMetricsCollector] = None
_tool_metrics: Optional[ToolMetricsCollector] = None


def get_agent_metrics() -> AgentMetricsCollector:
    global _agent_metrics
    if _agent_metrics is None:
        _agent_metrics = AgentMetricsCollector()
    return _agent_metrics


def get_tool_metrics() -> ToolMetricsCollector:
    global _tool_metrics
    if _tool_metrics is None:
        _tool_metrics = ToolMetricsCollector()
    return _tool_metrics
