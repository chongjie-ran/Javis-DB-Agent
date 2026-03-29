"""测试 P0-1: 监控告警接入 - metrics和health端点"""
import pytest
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


class TestMetricsCollector:
    """测试指标收集器"""

    def setup_method(self):
        """每个测试前重置指标"""
        from src.api.metrics import get_metrics
        self.metrics = get_metrics()
        self.metrics.reset()

    def test_counter_inc(self):
        """测试计数器递增"""
        c = self.metrics.counter("test_requests")
        assert c.get() == 0
        c.inc()
        assert c.get() == 1
        c.inc(5)
        assert c.get() == 6

    def test_gauge_set(self):
        """测试仪表设置"""
        g = self.metrics.gauge("test_value")
        assert g.get() == 0.0
        g.set(42.5)
        assert g.get() == 42.5

    def test_histogram_observe(self):
        """测试直方图记录"""
        h = self.metrics.histogram("test_latency")
        h.observe(0.1)
        h.observe(0.5)
        h.observe(1.0)
        stats = h.get_stats()
        assert stats["count"] == 3
        assert stats["sum"] == pytest.approx(1.6)
        assert stats["avg"] == pytest.approx(1.6 / 3)

    def test_inc_request(self):
        """测试请求记录"""
        self.metrics.inc_request("GET", "/api/v1/chat", 200)
        self.metrics.inc_request("GET", "/api/v1/chat", 200)
        self.metrics.inc_request("POST", "/api/v1/diagnose", 500)
        
        assert self.metrics.counter("http_requests_total").get() == 3
        assert self.metrics.counter("http_requests_success").get() == 2
        assert self.metrics.counter("http_requests_server_error").get() == 1

    def test_observe_latency(self):
        """测试延迟记录"""
        self.metrics.observe_latency(0.05)
        self.metrics.observe_latency(0.15)
        stats = self.metrics.histogram("http_request_duration_seconds").get_stats()
        assert stats["count"] == 2
        assert stats["sum"] == pytest.approx(0.20, rel=1e-3)

    def test_active_requests(self):
        """测试活跃请求计数"""
        assert self.metrics.gauge("http_requests_active").get() == 0
        self.metrics.inc_active_requests()
        self.metrics.inc_active_requests()
        assert self.metrics.gauge("http_requests_active").get() == 2
        self.metrics.dec_active_requests()
        assert self.metrics.gauge("http_requests_active").get() == 1

    def test_render_prometheus(self):
        """测试Prometheus格式输出"""
        self.metrics.inc_request("GET", "/api/v1/health", 200)
        self.metrics.observe_latency(0.05)
        self.metrics.set_ollama_status(True)
        
        output = self.metrics.render_prometheus()
        
        assert "javis_uptime_seconds" in output
        assert "http_requests_total 1" in output
        assert 'http_requests_total_by_status{status="2xx"} 1' in output
        assert "ollama_connected 1" in output
        assert "# HELP" in output
        assert "# TYPE" in output

    def test_get_summary(self):
        """测试指标摘要"""
        self.metrics.inc_request("GET", "/api/v1/chat", 200)
        self.metrics.inc_request("POST", "/api/v1/diagnose", 500)
        self.metrics.observe_latency(0.1)
        self.metrics.observe_latency(0.2)
        
        summary = self.metrics.get_summary()
        
        assert summary["requests_total"] == 2
        assert summary["requests_success"] == 1
        assert summary["requests_server_error"] == 1
        assert summary["error_rate_percent"] == 50.0
        assert summary["latency_count"] == 2
        assert "latency_avg_ms" in summary
        assert "latency_p95_ms" in summary

    def test_policy_metrics(self):
        """测试策略相关指标"""
        self.metrics.set_policy_version(3)
        self.metrics.inc_policy_changes()
        
        assert self.metrics.gauge("policy_version").get() == 3.0
        assert self.metrics.counter("policy_changes_total").get() == 1

    def test_session_metrics(self):
        """测试会话指标"""
        self.metrics.set_session_count(42)
        assert self.metrics.gauge("sessions_active").get() == 42.0

    def test_approval_metrics(self):
        """测试审批指标"""
        self.metrics.set_approvals_pending(5)
        assert self.metrics.gauge("approvals_pending").get() == 5.0

    def test_track_request_context(self):
        """测试请求追踪上下文"""
        from src.api.metrics import track_request
        
        with track_request("POST", "/api/v1/chat"):
            time.sleep(0.01)
        
        assert self.metrics.counter("http_requests_total").get() == 1
        latency_stats = self.metrics.histogram("http_request_duration_seconds").get_stats()
        assert latency_stats["count"] == 1
        assert latency_stats["sum"] >= 0.01

    def test_error_rate_calculation(self):
        """测试错误率计算"""
        # 100个请求，5个服务器错误
        for _ in range(95):
            self.metrics.inc_request("GET", "/api/v1/chat", 200)
        for _ in range(5):
            self.metrics.inc_request("GET", "/api/v1/chat", 500)
        
        summary = self.metrics.get_summary()
        assert summary["error_rate_percent"] == 5.0

    def test_percentile_estimation(self):
        """测试百分位数估算"""
        # 使用更多观测值，让直方图更密集，估算更准确
        import random
        random.seed(42)
        latencies = [random.uniform(0.01, 0.2) for _ in range(50)]
        latencies.extend([0.3, 0.5, 1.0, 2.0])
        for lat in latencies:
            self.metrics.observe_latency(lat)
        
        summary = self.metrics.get_summary()
        # P95应该大于平均值的一半
        assert summary["latency_p95_ms"] >= summary["latency_avg_ms"] * 0.5
        # P95应该小于最大值（2秒）
        assert summary["latency_p95_ms"] <= 2000

    def test_reset(self):
        """测试指标重置"""
        self.metrics.inc_request("GET", "/api/v1/chat", 200)
        self.metrics.set_session_count(10)
        
        self.metrics.reset()
        
        assert self.metrics.counter("http_requests_total").get() == 0
        assert self.metrics.gauge("sessions_active").get() == 0.0


class TestHealthEndpoint:
    """测试健康检查端点"""

    def test_health_response_schema(self):
        """测试健康响应schema"""
        from src.api.schemas import HealthResponse
        
        response = HealthResponse(
            status="healthy",
            version="v1.0",
            ollama_status="connected",
            timestamp=time.time(),
            metadata={"session_db": "ok", "disk_usage_percent": 50},
        )
        
        assert response.status == "healthy"
        assert response.metadata["session_db"] == "ok"

    def test_health_status_degraded(self):
        """测试降级状态判断"""
        # 当ollama断开但session_db正常
        from src.api.schemas import HealthResponse
        
        response = HealthResponse(
            status="degraded",
            version="v1.0",
            ollama_status="disconnected",
            timestamp=time.time(),
        )
        assert response.status == "degraded"

    def test_health_status_unhealthy(self):
        """测试不健康状态判断"""
        from src.api.schemas import HealthResponse
        
        response = HealthResponse(
            status="unhealthy",
            version="v1.0",
            ollama_status="disconnected",
            timestamp=time.time(),
        )
        assert response.status == "unhealthy"


class TestPrometheusFormat:
    """测试Prometheus格式合规性"""

    def setup_method(self):
        from src.api.metrics import get_metrics
        self.metrics = get_metrics()
        self.metrics.reset()

    def test_help_and_type_present(self):
        """测试HELP和TYPE注释存在"""
        self.metrics.inc_request("GET", "/api/v1/health", 200)
        output = self.metrics.render_prometheus()
        
        # 检查HELP和TYPE行
        lines = output.split("\n")
        help_lines = [l for l in lines if l.startswith("# HELP")]
        type_lines = [l for l in lines if l.startswith("# TYPE")]
        
        assert len(help_lines) > 0, "应该有HELP注释"
        assert len(type_lines) > 0, "应该有TYPE注释"

    def test_histogram_buckets(self):
        """测试直方图桶格式"""
        self.metrics.observe_latency(0.05)
        output = self.metrics.render_prometheus()
        
        assert "http_request_duration_seconds_bucket{le=" in output
        assert 'le="0.05"' in output or 'le="0.1"' in output
        assert 'le="+Inf"}' in output

    def test_counter_format(self):
        """测试计数器格式"""
        self.metrics.inc_request("GET", "/api/v1/chat", 200)
        output = self.metrics.render_prometheus()
        
        # counter应该只有非负整数
        lines = output.split("\n")
        for line in lines:
            if line.startswith("http_requests_total "):
                value = float(line.split(" ")[1])
                assert value >= 0
                assert value == int(value)  # 整数

    def test_gauge_format(self):
        """测试gauge格式"""
        self.metrics.set_session_count(42)
        output = self.metrics.render_prometheus()
        
        assert "sessions_active 42.0" in output or "sessions_active 42" in output

    def test_labels_format(self):
        """测试标签格式"""
        self.metrics.inc_request("GET", "/api/v1/chat", 200)
        self.metrics.inc_request("POST", "/api/v1/diagnose", 400)
        output = self.metrics.render_prometheus()
        
        assert '{status="2xx"}' in output
        assert '{status="4xx"}' in output
