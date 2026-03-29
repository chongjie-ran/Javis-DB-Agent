"""可观测性指标收集 - Prometheus兼容格式
支持请求量、延迟、错误率指标
"""
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from contextlib import contextmanager


@dataclass
class Counter:
    """计数器"""
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
class Gauge:
    """仪表值"""
    value: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, v: float):
        with self._lock:
            self.value = v

    def get(self) -> float:
        return self.value


@dataclass
class Histogram:
    """直方图（延迟分布）"""
    buckets: dict[float, int] = field(default_factory=lambda: {
        0.005: 0, 0.01: 0, 0.025: 0, 0.05: 0, 0.1: 0,
        0.25: 0, 0.5: 0, 1.0: 0, 2.5: 0, 5.0: 0, 10.0: 0,
    })
    sum: float = 0.0
    count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float):
        with self._lock:
            self.sum += value
            self.count += 1
            for boundary, count in self.buckets.items():
                if value <= boundary:
                    self.buckets[boundary] = count + 1

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "count": self.count,
                "sum": self.sum,
                "avg": self.sum / self.count if self.count > 0 else 0.0,
                "buckets": dict(self.buckets),
            }


class MetricsCollector:
    """
    指标收集器 - Prometheus兼容格式
    
    指标类型:
    - Counter: 累计计数器 (如: 请求总数)
    - Gauge: 当前值 (如: 活跃会话数)
    - Histogram: 延迟分布 (如: 请求延迟)
    """

    def __init__(self):
        self._counters: dict[str, Counter] = defaultdict(Counter)
        self._gauges: dict[str, Gauge] = defaultdict(Gauge)
        self._histograms: dict[str, Histogram] = defaultdict(Histogram)
        self._start_time = time.time()
        self._lock = threading.Lock()

    # ==================== 通用接口 ====================

    def counter(self, name: str) -> Counter:
        return self._counters[name]

    def gauge(self, name: str) -> Gauge:
        return self._gauges[name]

    def histogram(self, name: str) -> Histogram:
        return self._histograms[name]

    # ==================== 快捷方法 ====================

    def inc_request(self, method: str, endpoint: str, status_code: int):
        """记录请求 (method, endpoint, status)"""
        self._counters[f"http_requests_total{method}_{endpoint}_{status_code}"].inc()
        self._counters["http_requests_total"].inc()
        # 按状态分类
        if 200 <= status_code < 300:
            self._counters["http_requests_success"].inc()
        elif 400 <= status_code < 500:
            self._counters["http_requests_client_error"].inc()
        elif status_code >= 500:
            self._counters["http_requests_server_error"].inc()

    def observe_latency(self, seconds: float):
        """记录请求延迟"""
        self._histograms["http_request_duration_seconds"].observe(seconds)

    def set_active_requests(self, n: int):
        """设置当前活跃请求数"""
        self._gauges["http_requests_active"].set(n)

    def inc_active_requests(self):
        self._gauges["http_requests_active"].set(self._gauges["http_requests_active"].get() + 1)

    def dec_active_requests(self):
        self._gauges["http_requests_active"].set(max(0, self._gauges["http_requests_active"].get() - 1))

    def set_session_count(self, n: int):
        self._gauges["sessions_active"].set(n)

    def set_ollama_status(self, connected: bool):
        self._gauges["ollama_connected"].set(1 if connected else 0)

    def inc_audit_records(self):
        self._counters["audit_records_total"].inc()

    def set_policy_version(self, version: int):
        self._gauges["policy_version"].set(version)

    def inc_policy_changes(self):
        self._counters["policy_changes_total"].inc()

    def set_approvals_pending(self, n: int):
        self._gauges["approvals_pending"].set(n)

    # ==================== Prometheus格式输出 ====================

    def render_prometheus(self) -> str:
        """渲染Prometheus文本格式"""
        lines = []
        uptime = time.time() - self._start_time

        lines.append("# HELP zcloud_uptime_seconds zCloud agent uptime in seconds")
        lines.append("# TYPE zcloud_uptime_seconds gauge")
        lines.append(f"zcloud_uptime_seconds {uptime:.3f}")

        # HTTP 请求总量
        total = self._counters["http_requests_total"].get()
        lines.append("# HELP http_requests_total Total HTTP requests")
        lines.append("# TYPE http_requests_total counter")
        lines.append(f"http_requests_total {total}")

        # HTTP 成功/失败
        success = self._counters["http_requests_success"].get()
        client_err = self._counters["http_requests_client_error"].get()
        server_err = self._counters["http_requests_server_error"].get()
        lines.append("# HELP http_requests_total_by_status HTTP requests by status class")
        lines.append("# TYPE http_requests_total_by_status counter")
        lines.append(f'http_requests_total_by_status{{status="2xx"}} {success}')
        lines.append(f'http_requests_total_by_status{{status="4xx"}} {client_err}')
        lines.append(f'http_requests_total_by_status{{status="5xx"}} {server_err}')

        # 错误率
        error_rate = (server_err / total * 100) if total > 0 else 0.0
        lines.append("# HELP http_requests_error_rate_percent HTTP server error rate percent")
        lines.append("# TYPE http_requests_error_rate_percent gauge")
        lines.append(f"http_requests_error_rate_percent {error_rate:.2f}")

        # 请求延迟
        lat_hist = self._histograms["http_request_duration_seconds"]
        lat_stats = lat_hist.get_stats()
        lines.append("# HELP http_request_duration_seconds HTTP request latency in seconds")
        lines.append("# TYPE http_request_duration_seconds histogram")
        for bucket_ms, count in lat_hist.buckets.items():
            lines.append(f'http_request_duration_seconds_bucket{{le="{bucket_ms}"}} {count}')
        lines.append('http_request_duration_seconds_bucket{le="+Inf"} {lat_count}')
        lines.append(f"http_request_duration_seconds_count {lat_stats['count']}")
        lines.append(f"http_request_duration_seconds_sum {lat_stats['sum']:.6f}")
        if lat_stats['count'] > 0:
            lines.append(f'http_request_duration_seconds_avg {lat_stats["sum"] / lat_stats["count"]:.6f}')

        # 活跃请求
        active = self._gauges["http_requests_active"].get()
        lines.append("# HELP http_requests_active Current active HTTP requests")
        lines.append("# TYPE http_requests_active gauge")
        lines.append(f"http_requests_active {active}")

        # 活跃会话
        sessions = self._gauges["sessions_active"].get()
        lines.append("# HELP sessions_active Active sessions")
        lines.append("# TYPE sessions_active gauge")
        lines.append(f"sessions_active {sessions}")

        # Ollama状态
        ollama = self._gauges["ollama_connected"].get()
        lines.append("# HELP ollama_connected Ollama LLM connection status (1=up, 0=down)")
        lines.append("# TYPE ollama_connected gauge")
        lines.append(f"ollama_connected {int(ollama)}")

        # 审计记录
        audit_total = self._counters["audit_records_total"].get()
        lines.append("# HELP audit_records_total Total audit log records")
        lines.append("# TYPE audit_records_total counter")
        lines.append(f"audit_records_total {audit_total}")

        # 策略版本
        policy_ver = int(self._gauges["policy_version"].get())
        lines.append("# HELP policy_version Current policy version number")
        lines.append("# TYPE policy_version gauge")
        lines.append(f"policy_version {policy_ver}")

        # 策略变更
        policy_changes = self._counters["policy_changes_total"].get()
        lines.append("# HELP policy_changes_total Total policy changes")
        lines.append("# TYPE policy_changes_total counter")
        lines.append(f"policy_changes_total {policy_changes}")

        # 待审批
        pending = self._gauges["approvals_pending"].get()
        lines.append("# HELP approvals_pending Pending approval requests")
        lines.append("# TYPE approvals_pending gauge")
        lines.append(f"approvals_pending {int(pending)}")

        return "\n".join(lines) + "\n"

    def get_summary(self) -> dict:
        """获取指标摘要"""
        total = self._counters["http_requests_total"].get()
        lat_stats = self._histograms["http_request_duration_seconds"].get_stats()
        return {
            "uptime_seconds": time.time() - self._start_time,
            "requests_total": total,
            "requests_success": self._counters["http_requests_success"].get(),
            "requests_client_error": self._counters["http_requests_client_error"].get(),
            "requests_server_error": self._counters["http_requests_server_error"].get(),
            "error_rate_percent": (
                self._counters["http_requests_server_error"].get() / total * 100
                if total > 0 else 0.0
            ),
            "latency_avg_ms": (
                lat_stats["sum"] / lat_stats["count"] * 1000
                if lat_stats["count"] > 0 else 0.0
            ),
            "latency_p95_ms": self._estimate_percentile(lat_stats, 0.95) * 1000,
            "latency_count": lat_stats["count"],
            "active_requests": self._gauges["http_requests_active"].get(),
            "active_sessions": self._gauges["sessions_active"].get(),
            "ollama_connected": bool(self._gauges["ollama_connected"].get()),
            "policy_version": int(self._gauges["policy_version"].get()),
            "policy_changes_total": self._counters["policy_changes_total"].get(),
            "approvals_pending": int(self._gauges["approvals_pending"].get()),
        }

    def _estimate_percentile(self, lat_stats: dict, p: float) -> float:
        """估算百分位数（基于直方图桶，返回实际观测值而非桶边界）"""
        if lat_stats["count"] == 0:
            return 0.0
        # 使用线性插值：在最近的桶边界之间插值
        sorted_buckets = sorted(lat_stats["buckets"].items())
        cumulative = 0
        prev_boundary = 0.0
        prev_cumulative = 0
        
        target = lat_stats["count"] * p
        
        for boundary, count in sorted_buckets:
            if cumulative + count >= target:
                # 在 prev_boundary 和 boundary 之间插值
                bucket_count = cumulative + count - prev_cumulative
                if bucket_count > 0:
                    position_in_bucket = (target - cumulative) / bucket_count
                    return prev_boundary + (boundary - prev_boundary) * position_in_bucket
                else:
                    return boundary
            prev_boundary = boundary
            prev_cumulative = cumulative + count
            cumulative += count
        
        return list(sorted(lat_stats["buckets"].keys()))[-1]

    def reset(self):
        """重置所有指标（用于测试）"""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._start_time = time.time()


# ==================== 请求上下文管理器 ====================

_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


@contextmanager
def track_request(method: str, endpoint: str):
    """请求追踪上下文"""
    metrics = get_metrics()
    start = time.time()
    status_code = 200
    metrics.inc_active_requests()
    try:
        yield
    except Exception as e:
        status_code = 500
        raise
    finally:
        latency = time.time() - start
        metrics.inc_request(method, endpoint, status_code)
        metrics.observe_latency(latency)
        metrics.dec_active_requests()


# 全局中间件FastAPI
def setup_metrics_middleware(app):
    """为FastAPI应用设置指标中间件"""
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware
    import asyncio

    class MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # 跳过 metrics 端点自身，避免递归
            if request.url.path in ("/metrics", "/health", "/favicon.ico"):
                return await call_next(request)

            start = time.time()
            metrics = get_metrics()
            metrics.inc_active_requests()

            try:
                response = await call_next(request)
                status = response.status_code
                return response
            except Exception as e:
                status = 500
                raise
            finally:
                latency = time.time() - start
                # 规范端点（去掉动态部分）
                endpoint = self._normalize_endpoint(request.url.path)
                metrics.inc_request(request.method, endpoint, status)
                metrics.observe_latency(latency)
                metrics.dec_active_requests()

        @staticmethod
        def _normalize_endpoint(path: str) -> str:
            """规范端点路径，去掉动态ID部分"""
            parts = path.strip("/").split("/")
            normalized = []
            for i, part in enumerate(parts):
                # 跳过明显的UUID和数字ID
                if part and (len(part) == 36 or (part.isdigit() and len(part) > 8)):
                    normalized.append("{id}")
                else:
                    normalized.append(part)
            return "/" + "/".join(normalized) if normalized else "/"

    app.add_middleware(MetricsMiddleware)
