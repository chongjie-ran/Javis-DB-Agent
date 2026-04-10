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


# ── Token 预算追踪器 (V3.2 P1) ───────────────────────────────────────────────

@dataclass
class TokenBudgetAlert:
    """Token预算告警"""
    session_id: str
    threshold_percent: float  # 触发阈值 (e.g. 80.0)
    budget: int
    used: int
    remaining: int
    severity: str  # "warning" | "critical"
    timestamp: float


class TokenBudgetTracker:
    """
    Token消耗追踪器

    功能:
    - per-session token消耗记录（input/output/total）
    - Token预算告警（支持多会话并发）
    - Prometheus格式导出
    """

    DEFAULT_BUDGET = 100_000  # 默认预算 100k tokens

    def __init__(self, default_budget: int = DEFAULT_BUDGET):
        self._default_budget = default_budget
        self._lock = threading.Lock()
        # session_id -> {input, output, total, budget, warnings_sent}
        self._sessions: dict[str, dict] = defaultdict(
            lambda: {"input": 0, "output": 0, "total": 0, "budget": default_budget, "warnings_sent": set()}
        )
        self._alerts: list[TokenBudgetAlert] = []
        self._total_input = SimpleCounter()
        self._total_output = SimpleCounter()

    def set_budget(self, session_id: str, budget: int) -> None:
        """设置会话token预算"""
        with self._lock:
            self._sessions[session_id]["budget"] = budget

    def record_tokens(self, session_id: str, input_tokens: int = 0,
                      output_tokens: int = 0) -> list[TokenBudgetAlert]:
        """
        记录token消耗，返回触发的告警列表

        Returns:
            list of TokenBudgetAlert if thresholds crossed
        """
        alerts = []
        thresholds = [50.0, 80.0, 90.0, 100.0]

        with self._lock:
            sess = self._sessions[session_id]
            sess["input"] += input_tokens
            sess["output"] += output_tokens
            sess["total"] += input_tokens + output_tokens

            self._total_input.inc(input_tokens)
            self._total_output.inc(output_tokens)

            used = sess["total"]
            budget = sess["budget"]
            pct = (used / budget * 100) if budget > 0 else 0

            for threshold in thresholds:
                if pct >= threshold and threshold not in sess["warnings_sent"]:
                    severity = "critical" if threshold >= 90 else "warning"
                    alert = TokenBudgetAlert(
                        session_id=session_id,
                        threshold_percent=threshold,
                        budget=budget,
                        used=used,
                        remaining=max(0, budget - used),
                        severity=severity,
                        timestamp=time.time(),
                    )
                    alerts.append(alert)
                    self._alerts.append(alert)
                    sess["warnings_sent"].add(threshold)

        return alerts

    def get_session(self, session_id: str) -> dict:
        """获取会话token使用情况"""
        with self._lock:
            sess = self._sessions[session_id]
            budget = sess["budget"]
            total = sess["total"]
            return {
                "session_id": session_id,
                "input_tokens": sess["input"],
                "output_tokens": sess["output"],
                "total_tokens": total,
                "budget": budget,
                "remaining": max(0, budget - total),
                "usage_percent": round((total / budget * 100), 2) if budget > 0 else 0,
            }

    def get_all_sessions(self) -> list[dict]:
        """获取所有会话使用情况"""
        with self._lock:
            return [self.get_session(sid) for sid in self._sessions]

    def get_recent_alerts(self, since: float = 0) -> list[dict]:
        """获取最近的告警"""
        return [
            {
                "session_id": a.session_id,
                "threshold_percent": a.threshold_percent,
                "budget": a.budget,
                "used": a.used,
                "severity": a.severity,
                "timestamp": a.timestamp,
            }
            for a in self._alerts
            if a.timestamp >= since
        ]

    def reset_session(self, session_id: str) -> None:
        """重置会话计数器"""
        with self._lock:
            self._sessions.pop(session_id, None)

    def render_prometheus(self) -> str:
        lines = []
        lines.append("# HELP tokens_total_input Total input tokens")
        lines.append("# TYPE tokens_total_input counter")
        lines.append(f"tokens_total_input {self._total_input.get()}")

        lines.append("# HELP tokens_total_output Total output tokens")
        lines.append("# TYPE tokens_total_output counter")
        lines.append(f"tokens_total_output {self._total_output.get()}")

        with self._lock:
            for sid, sess in sorted(self._sessions.items()):
                labels = f'session_id="{sid}"'
                lines.append(f'{{# HELP session_tokens_total Session token usage')
                lines.append(f"# TYPE session_tokens_total gauge")
                lines.append(f'session_tokens_total{{{labels},type="input"}} {sess["input"]}')
                lines.append(f'session_tokens_total{{{labels},type="output"}} {sess["output"]}')
                lines.append(f'session_tokens_total{{{labels},type="total"}} {sess["total"]}')
                pct = (sess["total"] / sess["budget"] * 100) if sess["budget"] > 0 else 0
                lines.append(f'session_tokens_usage_percent{{{labels}}} {pct:.2f}')

        return "\n".join(lines) + "\n"


# ── Hook 执行耗时追踪器 (V3.2 P1) ────────────────────────────────────────────

class HookMetricsCollector:
    """
    Hook 执行耗时收集器

    指标:
    - hook_duration_seconds: 按 hook_name + event 的直方图
    - hook_invocations_total: 调用次数
    - hook_errors_total: 错误次数
    """

    def __init__(self):
        self._histograms: dict[str, SimpleHistogram] = defaultdict(SimpleHistogram)
        self._counters: dict[str, SimpleCounter] = defaultdict(SimpleCounter)
        self._errors: dict[str, SimpleCounter] = defaultdict(SimpleCounter)
        self._lock = threading.Lock()

    def record(self, hook_name: str, event: str, duration_seconds: float,
               error: bool = False) -> None:
        """记录一次Hook执行"""
        key = f"{hook_name}.{event}"
        with self._lock:
            self._histograms[key].observe(duration_seconds)
            self._counters[key].inc()
            if error:
                self._errors[key].inc()

    def get_stats(self, hook_name: Optional[str] = None,
                  event: Optional[str] = None) -> dict:
        """获取Hook执行统计"""
        with self._lock:
            result = {}
            for key, hist in self._histograms.items():
                if hook_name and event:
                    if key == f"{hook_name}.{event}":
                        result[key] = hist.get_stats()
                elif hook_name:
                    if key.startswith(f"{hook_name}."):
                        result[key] = hist.get_stats()
                else:
                    result[key] = hist.get_stats()
            return result

    def get_summary(self) -> list[dict]:
        """获取所有Hook指标摘要"""
        with self._lock:
            summary = []
            for key in sorted(self._histograms.keys()):
                stats = self._histograms[key].get_stats()
                summary.append({
                    "hook_event": key,
                    "calls": self._counters[key].get(),
                    "errors": self._errors[key].get(),
                    "avg_ms": round((stats["sum"] / stats["count"] * 1000), 3) if stats["count"] > 0 else 0,
                    "p50_ms": self._p50(key),
                    "p95_ms": self._p95(key),
                    "p99_ms": self._p99(key),
                })
            return summary

    def _p50(self, key: str) -> float:
        """估算p50（秒）"""
        hist = self._histograms[key]
        with self._lock:
            total = hist.count
            if total == 0:
                return 0
            cumsum = 0
            for le, count in sorted(hist.buckets.items()):
                cumsum += count
                if cumsum >= total * 0.50:
                    return le * 1000
        return 0

    def _p95(self, key: str) -> float:
        hist = self._histograms[key]
        with self._lock:
            total = hist.count
            if total == 0:
                return 0
            cumsum = 0
            for le, count in sorted(hist.buckets.items()):
                cumsum += count
                if cumsum >= total * 0.95:
                    return le * 1000
        return 0

    def _p99(self, key: str) -> float:
        hist = self._histograms[key]
        with self._lock:
            total = hist.count
            if total == 0:
                return 0
            cumsum = 0
            for le, count in sorted(hist.buckets.items()):
                cumsum += count
                if cumsum >= total * 0.99:
                    return le * 1000
        return 0

    def reset(self) -> None:
        with self._lock:
            self._histograms.clear()
            self._counters.clear()
            self._errors.clear()

    def render_prometheus(self) -> str:
        lines = []
        lines.append("# HELP hook_duration_seconds Hook execution duration in seconds")
        lines.append("# TYPE hook_duration_seconds histogram")
        with self._lock:
            for key, hist in sorted(self._histograms.items()):
                parts = key.rsplit(".", 1)
                hook_name, event = parts[0], parts[1] if len(parts) > 1 else ""
                labels = f'hook_name="{hook_name}",event="{event}"'
                stats = hist.get_stats()
                for le, count in sorted(hist.buckets.items()):
                    lines.append(f'hook_duration_seconds_bucket{{{labels},le="{le}"}} {count}')
                lines.append(f'hook_duration_seconds_count{{{labels}}} {stats["count"]}')
                lines.append(f'hook_duration_seconds_sum{{{labels}}} {stats["sum"]:.6f}')

            lines.append("# HELP hook_invocations_total Total hook invocations")
            lines.append("# TYPE hook_invocations_total counter")
            for key, counter in sorted(self._counters.items()):
                parts = key.rsplit(".", 1)
                hook_name, event = parts[0], parts[1] if len(parts) > 1 else ""
                lines.append(f'hook_invocations_total{{hook_name="{hook_name}",event="{event}"}} {counter.get()}')

        return "\n".join(lines) + "\n"


# ── 全局单例 ─────────────────────────────────────────────────────────────────

_token_tracker: Optional[TokenBudgetTracker] = None
_hook_metrics: Optional[HookMetricsCollector] = None


def get_token_tracker() -> TokenBudgetTracker:
    global _token_tracker
    if _token_tracker is None:
        _token_tracker = TokenBudgetTracker()
    return _token_tracker


def get_hook_metrics() -> HookMetricsCollector:
    global _hook_metrics
    if _hook_metrics is None:
        _hook_metrics = HookMetricsCollector()
    return _hook_metrics
