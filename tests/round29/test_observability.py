"""测试 P0: 可观测性框架 - Tracer / Metrics / Logger
覆盖 src/observability/ 所有模块
"""
import pytest
import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


class TestTracer:
    """测试 JavisTracer"""

    def setup_method(self):
        from src.observability.tracer import JavisTracer, get_tracer
        self.tracer = JavisTracer(service_name="test-agent")

    def teardown_method(self):
        self.tracer.clear()

    def test_span_lifecycle(self):
        """测试 Span 生命周期"""
        span = self.tracer.start_span("test_span", kind="tool")
        assert span.name == "test_span"
        assert span.trace_id is not None
        assert span.span_id is not None
        assert span.end_time is None

        self.tracer.end_span(span)
        assert span.end_time is not None
        assert span.duration_ms >= 0

    def test_span_attributes(self):
        """测试 Span 属性"""
        span = (
            self.tracer
            .start_span("test_attr")
            .set_attribute("tool_name", "execute_sql")
            .set_attribute("risk_level", 3)
        )
        assert span.attributes["tool_name"] == "execute_sql"
        assert span.attributes["risk_level"] == 3
        self.tracer.end_span(span)

    def test_span_events(self):
        """测试 Span 事件"""
        span = self.tracer.start_span("test_event")
        span.add_event("sub_step_1", {"key": "value"})
        span.add_event("sub_step_2")
        assert len(span.events) == 2
        assert span.events[0]["name"] == "sub_step_1"
        assert span.events[0]["attributes"]["key"] == "value"
        self.tracer.end_span(span)

    def test_span_error_status(self):
        """测试 Span 错误状态"""
        span = self.tracer.start_span("error_span")
        self.tracer.end_span(span, status="error", error_message="connection timeout")
        assert span.status == "error"
        assert span.error_message == "connection timeout"

    def test_span_duration(self):
        """测试 Span 耗时计算"""
        span = self.tracer.start_span("timed_span")
        time.sleep(0.01)
        self.tracer.end_span(span)
        assert span.duration_ms >= 10

    def test_span_parent_child(self):
        """测试父子 Span 关系"""
        parent = self.tracer.start_span("parent")
        child = self.tracer.start_span("child", parent=parent)
        assert child.parent_id == parent.span_id
        assert child.trace_id == parent.trace_id
        self.tracer.end_span(child)
        self.tracer.end_span(parent)

    def test_trace_context_propagation(self):
        """测试 Trace Context 注入/提取"""
        from src.observability.tracer import TraceContext

        span = self.tracer.start_span("propagate_test")
        carrier = TraceContext.inject(span)
        ctx = TraceContext.extract(carrier)

        assert ctx["trace_id"] == span.trace_id
        assert ctx["span_id"] == span.span_id
        assert ctx["parent_id"] is None

        self.tracer.end_span(span)

    def test_otel_export(self):
        """测试 OpenTelemetry 格式导出"""
        span = self.tracer.start_span("export_span", kind="agent")
        span.set_attribute("agent.name", "diagnostic")
        self.tracer.end_span(span)

        otel = self.tracer.export_otel_dict()
        assert "resourceSpans" in otel
        assert len(otel["resourceSpans"]) == 1
        spans = otel["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans) == 1
        assert spans[0]["name"] == "export_span"
        assert spans[0]["attributes"][0]["key"] == "agent.name"

    def test_span_kind_enum(self):
        """测试 SpanKind 枚举"""
        from src.observability.tracer import SpanKind

        span = self.tracer.start_span("kind_test", kind=SpanKind.TOOL)
        assert span.kind == SpanKind.TOOL
        self.tracer.end_span(span)

    def test_span_to_dict(self):
        """测试 Span 序列化"""
        span = self.tracer.start_span("serialize_test")
        span.set_attribute("key", "value")
        d = span.to_dict()
        assert d["name"] == "serialize_test"
        assert d["attributes"]["key"] == "value"
        assert "duration_ms" in d
        self.tracer.end_span(span)

    def test_span_context_manager(self):
        """测试 with 语法糖"""
        with self.tracer.trace("ctx_span") as span:
            span.set_attribute("auto", True)
        assert span.end_time is not None


class TestAgentMetrics:
    """测试 AgentMetricsCollector"""

    def setup_method(self):
        from src.observability.metrics import AgentMetricsCollector
        self.m = AgentMetricsCollector()

    def test_record_invocation(self):
        """测试记录调用"""
        self.m.record_invocation("diagnostic", success=True, duration_seconds=0.05)
        self.m.record_invocation("diagnostic", success=False, duration_seconds=0.10)
        self.m.record_invocation("sql_analyzer", success=True)

        assert self.m.get_total_invocations("diagnostic") == 2
        assert self.m.get_total_invocations("sql_analyzer") == 1
        assert self.m.get_total_invocations() == 3

    def test_error_rate(self):
        """测试错误率计算"""
        for _ in range(9):
            self.m.record_invocation("risk", success=True)
        for _ in range(1):
            self.m.record_invocation("risk", success=False)

        assert self.m.get_total_errors("risk") == 1
        assert self.m.get_error_rate("risk") == 10.0

    def test_duration_histogram(self):
        """测试延迟直方图"""
        self.m.record_invocation("perf", success=True, duration_seconds=0.05)
        self.m.record_invocation("perf", success=True, duration_seconds=0.15)
        stats = self.m.get_duration_stats()
        assert stats["count"] == 2
        assert stats["sum"] == pytest.approx(0.20, rel=1e-3)

    def test_active_count(self):
        """测试活跃计数"""
        assert self.m.get_active_count() == 0
        self.m.inc_active()
        self.m.inc_active()
        assert self.m.get_active_count() == 2
        self.m.dec_active()
        assert self.m.get_active_count() == 1

    def test_summary(self):
        """测试摘要"""
        self.m.record_invocation("diagnostic", success=True, duration_seconds=0.05)
        summary = self.m.get_summary("diagnostic")
        assert summary["agent_name"] == "diagnostic"
        assert summary["invocations_total"] == 1
        assert summary["errors_total"] == 0

    def test_reset(self):
        """测试重置"""
        self.m.record_invocation("diagnostic", success=True)
        self.m.reset()
        assert self.m.get_total_invocations() == 0

    def test_prometheus_format(self):
        """测试 Prometheus 格式"""
        self.m.record_invocation("diagnostic", success=True)
        self.m.record_invocation("diagnostic", success=False)
        output = self.m.render_prometheus()
        assert "agent_invocations_total" in output
        assert 'agent_name="diagnostic"' in output
        assert "agent_errors_total" in output


class TestToolMetrics:
    """测试 ToolMetricsCollector"""

    def setup_method(self):
        from src.observability.metrics import ToolMetricsCollector
        self.m = ToolMetricsCollector()

    def test_record_call(self):
        """测试记录工具调用"""
        self.m.record_call("execute_sql", success=True, duration_seconds=0.02)
        self.m.record_call("execute_sql", success=False, error="timeout")
        self.m.record_call("describe_table", success=True)

        assert self.m.get_total_calls("execute_sql") == 2
        assert self.m.get_total_calls("describe_table") == 1

    def test_error_rate(self):
        """测试错误率"""
        for _ in range(19):
            self.m.record_call("sql", success=True)
        for _ in range(1):
            self.m.record_call("sql", success=False)
        assert self.m.get_error_rate("sql") == 5.0

    def test_summary(self):
        """测试摘要"""
        self.m.record_call("execute_sql", success=True, duration_seconds=0.05)
        summary = self.m.get_summary("execute_sql")
        assert summary["tool_name"] == "execute_sql"
        assert summary["calls_total"] == 1
        assert summary["errors_total"] == 0

    def test_reset(self):
        """测试重置"""
        self.m.record_call("sql", success=True)
        self.m.reset()
        assert self.m.get_total_calls() == 0

    def test_prometheus_format(self):
        """测试 Prometheus 格式"""
        self.m.record_call("execute_sql", success=True)
        output = self.m.render_prometheus()
        assert "tool_calls_total" in output
        assert 'tool_name="execute_sql"' in output


class TestStructuredLogger:
    """测试 StructuredLogger"""

    def setup_method(self):
        from src.observability.structured_logger import StructuredLogger
        import logging
        # 使用内存 handler 捕获日志
        self._captured = []
        self.logger = StructuredLogger(service_name="test-javis")
        self.logger._logger.setLevel(logging.INFO)

        class CaptureHandler(logging.Handler):
            def __init__(cap_self, captured_list):
                super().__init__()
                cap_self._captured_list = captured_list
            def emit(cap_self, record):
                cap_self._captured_list.append(record.getMessage())
        self._handler = CaptureHandler(self._captured)
        self.logger._logger.addHandler(self._handler)

    def teardown_method(self):
        self.logger._logger.removeHandler(self._handler)

    def test_log_hook_event(self):
        """测试 Hook 事件日志"""
        self.logger.log_hook_event(
            event="tool:before_execute",
            session_id="sess_123",
            user_id="user_456",
            blocked=False,
            message="",
            warnings=[],
            matched_rules=["rule1"],
            duration_ms=5.2,
            payload={"tool_name": "execute_sql"},
        )
        assert len(self._captured) == 1
        line = self._captured[0]
        parsed = json.loads(line)
        assert parsed["event"] == "tool:before_execute"
        assert parsed["session_id"] == "sess_123"
        assert parsed["blocked"] is False
        assert parsed["payload"]["tool_name"] == "execute_sql"

    def test_log_agent_decision(self):
        """测试 Agent 决策日志"""
        self.logger.log_agent_decision(
            agent_name="diagnostic",
            session_id="sess_123",
            user_id="user_456",
            decision_type="select_tool",
            decision_data={"tool": "execute_sql", "reason": "goal requires db access"},
            goal="帮我执行一个 SQL",
            success=True,
            execution_time_ms=50,
            trace_id="abc123",
        )
        assert len(self._captured) == 1
        parsed = json.loads(self._captured[0])
        assert parsed["agent_name"] == "diagnostic"
        assert parsed["decision_type"] == "select_tool"
        assert parsed["trace_id"] == "abc123"

    def test_sanitize_payload(self):
        """测试敏感字段脱敏"""
        self.logger.log_hook_event(
            event="tool:before_execute",
            session_id="sess_1",
            user_id="u1",
            payload={"tool_name": "api", "password": "secret123", "api_key": "key123"},
        )
        parsed = json.loads(self._captured[0])
        assert parsed["payload"]["password"] == "[REDACTED]"
        assert parsed["payload"]["api_key"] == "[REDACTED]"
        assert parsed["payload"]["tool_name"] == "api"

    def test_generic_log(self):
        """测试通用日志"""
        self.logger.info("test message", extra_field="value")
        parsed = json.loads(self._captured[0])
        assert parsed["message"] == "test message"
        assert parsed["extra_field"] == "value"
        assert parsed["level"] == "INFO"

    def test_decision_types(self):
        """测试不同决策类型"""
        for dtype in ["select_tool", "llm_response", "route", "fallback"]:
            self._captured.clear()
            self.logger.log_agent_decision(
                agent_name="test",
                session_id="s1",
                user_id="u1",
                decision_type=dtype,
                decision_data={},
            )
            parsed = json.loads(self._captured[0])
            assert parsed["decision_type"] == dtype


class TestObservabilityManager:
    """测试 ObservabilityManager"""

    def setup_method(self):
        from src.observability.observability_manager import ObservabilityManager, reset_observability_manager
        reset_observability_manager()
        self.obs = ObservabilityManager(
            service_name="test-javis",
            enable_tracer=True,
            enable_metrics=True,
            enable_logger=True,
        )

    def test_initialization(self):
        """测试初始化"""
        assert self.obs.tracer is not None
        assert self.obs.agent_metrics is not None
        assert self.obs.tool_metrics is not None
        assert self.obs.structured_logger is not None

    def test_record_agent_invocation(self):
        """测试记录 Agent 调用"""
        self.obs.record_agent_invocation(
            agent_name="diagnostic",
            session_id="sess_123",
            user_id="user_456",
            success=True,
            execution_time_ms=100,
            goal="帮我诊断告警",
            decision_type="direct",
        )
        summary = self.obs.agent_metrics.get_summary("diagnostic")
        assert summary["invocations_total"] == 1
        assert summary["errors_total"] == 0

    def test_record_tool_call(self):
        """测试记录 Tool 调用"""
        self.obs.record_tool_call(
            tool_name="execute_sql",
            success=True,
            duration_seconds=0.05,
            session_id="sess_123",
            user_id="user_456",
        )
        summary = self.obs.tool_metrics.get_summary("execute_sql")
        assert summary["calls_total"] == 1

    def test_record_agent_decision(self):
        """测试记录 Agent 决策"""
        self.obs.record_agent_decision(
            agent_name="diagnostic",
            session_id="sess_123",
            user_id="user_456",
            decision_type="select_tool",
            decision_data={"tool": "execute_sql", "reason": "requires db access"},
            goal="帮我执行 SQL",
            success=True,
        )

    def test_export_traces_otel(self):
        """测试导出 OTEL 格式"""
        with self.obs.tracer.trace("test_export"):
            pass
        otel = self.obs.export_traces_otel()
        assert "resourceSpans" in otel

    def test_export_metrics_prometheus(self):
        """测试导出 Prometheus 格式"""
        self.obs.record_tool_call("execute_sql", success=True)
        self.obs.record_agent_invocation("diagnostic", "s1", "u1", True)
        output = self.obs.export_metrics_prometheus()
        assert "agent_invocations_total" in output
        assert "tool_calls_total" in output

    def test_get_all_summaries(self):
        """测试获取所有摘要"""
        self.obs.record_tool_call("execute_sql", success=True)
        summaries = self.obs.get_all_summaries()
        assert "agent" in summaries
        assert "tool" in summaries
        assert "tracer" in summaries

    def test_reset(self):
        """测试重置"""
        self.obs.record_tool_call("sql", success=True)
        self.obs.reset()
        assert self.obs.tool_metrics.get_total_calls() == 0
        assert self.obs.agent_metrics.get_total_invocations() == 0
        assert len(self.obs.tracer.spans) == 0

    def test_global_singleton(self):
        """测试全局单例"""
        from src.observability.observability_manager import get_observability_manager
        obs1 = get_observability_manager()
        obs2 = get_observability_manager()
        assert obs1 is obs2

    def test_trace_integration(self):
        """测试 Trace 与 Metrics 协同"""
        with self.obs.tracer.trace("agent:diagnostic", kind="agent") as span:
            span.set_attribute("agent.name", "diagnostic")
            self.obs.record_agent_invocation(
                agent_name="diagnostic",
                session_id="sess_1",
                user_id="u1",
                success=True,
                execution_time_ms=100,
            )
        assert len(self.obs.tracer.spans) == 1
        summary = self.obs.agent_metrics.get_summary("diagnostic")
        assert summary["invocations_total"] == 1


class TestHookEventIntegration:
    """测试 Hook 事件与可观测性集成"""

    def setup_method(self):
        from src.observability.observability_manager import ObservabilityManager, reset_observability_manager
        from src.observability.metrics import get_agent_metrics, get_tool_metrics
        reset_observability_manager()
        # 确保指标完全清零
        get_agent_metrics().reset()
        get_tool_metrics().reset()
        self.obs = ObservabilityManager(enable_tracer=True, enable_metrics=True, enable_logger=True)

    def test_hook_events_record_metrics(self):
        """测试 Hook 事件自动记录指标"""
        # 模拟 TOOL_BEFORE/AFTER 事件
        self.obs.record_tool_call(
            tool_name="execute_sql",
            success=True,
            duration_seconds=0.05,
            session_id="sess_test",
            user_id="user_test",
        )
        self.obs.record_tool_call(
            tool_name="execute_sql",
            success=False,
            error="timeout",
            duration_seconds=5.0,
            session_id="sess_test",
            user_id="user_test",
        )
        summary = self.obs.tool_metrics.get_summary("execute_sql")
        assert summary["calls_total"] == 2
        assert summary["errors_total"] == 1

    def test_agent_invoke_events_record_metrics(self):
        """测试 Agent invoke 事件自动记录指标"""
        self.obs.record_agent_invocation(
            agent_name="diagnostic",
            session_id="sess_test",
            user_id="user_test",
            success=True,
            execution_time_ms=200,
        )
        self.obs.record_agent_invocation(
            agent_name="diagnostic",
            session_id="sess_test",
            user_id="user_test",
            success=False,
            execution_time_ms=50,
        )
        summary = self.obs.agent_metrics.get_summary("diagnostic")
        assert summary["invocations_total"] == 2
        assert summary["errors_total"] == 1
        assert summary["error_rate_percent"] == 50.0

    def test_trace_context_preserved(self):
        """测试 Trace Context 在操作间保持"""
        from src.observability.tracer import get_current_trace_id, get_current_span

        with self.obs.tracer.trace("root_span", kind="agent"):
            trace_id = get_current_trace_id()
            assert trace_id is not None

            # Tool call 应该继承相同的 trace_id
            with self.obs.tracer.trace("child_tool", kind="tool") as tool_span:
                assert tool_span.trace_id == trace_id
                assert tool_span.parent_id is not None

    def test_error_rate_calculation(self):
        """测试错误率计算"""
        for _ in range(18):
            self.obs.record_agent_invocation("perf", "s1", "u1", True, 50)
        for _ in range(2):
            self.obs.record_agent_invocation("perf", "s1", "u1", False, 10)

        summary = self.obs.agent_metrics.get_summary("perf")
        assert summary["error_rate_percent"] == pytest.approx(10.0, rel=1e-2)

    def test_latency_stats(self):
        """测试延迟统计"""
        latencies = [0.01, 0.05, 0.10, 0.50, 1.00]
        for lat in latencies:
            self.obs.record_agent_invocation(
                "perf", "s1", "u1", True, int(lat * 1000)
            )
        stats = self.obs.agent_metrics.get_duration_stats()
        assert stats["count"] == 5
        assert stats["sum"] == pytest.approx(1.66, rel=1e-1)
