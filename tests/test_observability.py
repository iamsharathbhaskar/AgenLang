"""Tests for observability module."""

import time
import pytest
from agenlang.observability import (
    MetricsCollector, Tracer, TraceSpan,
    AgentMetrics, StructuredLogger, JsonFormatter,
    get_metrics, get_logger,
    MetricType,
)


class TestMetricsCollector:
    """Test MetricsCollector."""

    def test_counter(self):
        """Test counter metric."""
        collector = MetricsCollector()

        collector.counter("requests", 1)
        collector.counter("requests", 2)

        assert collector.get_counter("requests") == 3

    def test_counter_with_labels(self):
        """Test counter with labels."""
        collector = MetricsCollector()

        collector.counter("requests", 1, {"method": "GET"})
        collector.counter("requests", 1, {"method": "POST"})
        collector.counter("requests", 1, {"method": "GET"})

        assert collector.get_counter("requests", {"method": "GET"}) == 2
        assert collector.get_counter("requests", {"method": "POST"}) == 1

    def test_gauge(self):
        """Test gauge metric."""
        collector = MetricsCollector()

        collector.gauge("active_connections", 10)
        assert collector.get_gauge("active_connections") == 10

        collector.gauge("active_connections", 5)
        assert collector.get_gauge("active_connections") == 5

    def test_timer(self):
        """Test timer metric."""
        collector = MetricsCollector()

        collector.timer("request_duration", 100.5)
        collector.timer("request_duration", 200.0)
        collector.timer("request_duration", 150.0)

        stats = collector.get_timer_stats("request_duration")
        assert stats["count"] == 3
        assert stats["mean"] == pytest.approx(150.17, rel=0.01)

    def test_histogram_stats(self):
        """Test histogram statistics calculation."""
        collector = MetricsCollector()

        for i in range(100):
            collector.histogram("response_size", float(i))

        stats = collector.get_histogram_stats("response_size")
        assert stats["count"] == 100
        assert stats["min"] == 0
        assert stats["max"] == 99
        assert stats["mean"] == 49.5
        assert stats["p95"] == 95
        assert stats["p99"] == 99

    def test_timed_context_manager(self):
        """Test timed context manager."""
        collector = MetricsCollector()

        with collector.timed("operation"):
            time.sleep(0.01)

        stats = collector.get_timer_stats("operation")
        assert stats["count"] == 1
        assert stats["mean"] >= 10  # At least 10ms

    def test_get_all_metrics(self):
        """Test getting all metrics."""
        collector = MetricsCollector()

        collector.counter("requests", 5)
        collector.gauge("active", 10)
        collector.timer("duration", 100)

        all_metrics = collector.get_all_metrics()
        assert "counters" in all_metrics
        assert "gauges" in all_metrics
        assert "timers" in all_metrics

    def test_reset(self):
        """Test reset functionality."""
        collector = MetricsCollector()

        collector.counter("requests", 5)
        collector.reset()

        assert collector.get_counter("requests") == 0


class TestTracer:
    """Test Tracer."""

    def test_start_trace(self):
        """Test starting a trace."""
        tracer = Tracer()

        span = tracer.start_trace("test-operation")

        assert span.name == "test-operation"
        assert span.trace_id is not None
        assert span.span_id is not None
        assert span.parent_id is None

    def test_start_span_with_parent(self):
        """Test starting a span with parent."""
        tracer = Tracer()

        root = tracer.start_trace("root")
        child = tracer.start_span("child", parent_id=root.span_id, trace_id=root.trace_id)

        assert child.parent_id == root.span_id
        assert child.trace_id == root.trace_id

    def test_finish_span(self):
        """Test finishing a span."""
        tracer = Tracer()

        span = tracer.start_trace("test")
        tracer.finish_span(span)

        assert span.end_time is not None
        assert span.duration_ms() >= 0

    def test_span_context_manager(self):
        """Test span context manager."""
        tracer = Tracer()

        with tracer.span("operation") as span:
            pass

        assert span.end_time is not None

    def test_span_context_manager_with_error(self):
        """Test span context manager records error."""
        tracer = Tracer()

        try:
            with tracer.span("operation") as span:
                raise ValueError("test error")
        except ValueError:
            pass

        assert span.error == "test error"

    def test_log_event(self):
        """Test logging events in spans."""
        tracer = Tracer()

        span = tracer.start_trace("test")
        tracer.log_event(span, "event_name", {"key": "value"})

        assert len(span.logs) == 1
        assert span.logs[0]["event"] == "event_name"

    def test_get_trace(self):
        """Test getting all spans for a trace."""
        tracer = Tracer()

        root = tracer.start_trace("root")
        child = tracer.start_span("child", parent_id=root.span_id, trace_id=root.trace_id)
        tracer.finish_span(child)
        tracer.finish_span(root)

        spans = tracer.get_trace(root.trace_id)
        assert len(spans) == 2

    def test_get_recent_traces(self):
        """Test getting recent traces."""
        tracer = Tracer()

        for i in range(5):
            span = tracer.start_trace(f"trace-{i}")
            tracer.finish_span(span)

        traces = tracer.get_recent_traces(limit=3)
        assert len(traces) == 3

    def test_to_jaeger_format(self):
        """Test export to Jaeger format."""
        tracer = Tracer()

        span = tracer.start_trace("test")
        tracer.finish_span(span)

        jaeger = tracer.to_jaeger_format()
        assert len(jaeger) == 1
        assert jaeger[0]["name"] == "test"


class TestAgentMetrics:
    """Test AgentMetrics."""

    def test_record_contract_created(self):
        """Test recording contract creation."""
        agent_metrics = AgentMetrics()

        agent_metrics.record_contract_created("contract-1", contract_type="test")

        assert agent_metrics.metrics.get_counter("contracts_created") == 1

    def test_record_contract_completed(self):
        """Test recording contract completion."""
        agent_metrics = AgentMetrics()

        agent_metrics.record_contract_completed(
            "contract-1",
            duration_ms=100.0,
            success=True,
            contract_type="test",
        )

        assert agent_metrics.metrics.get_counter("contracts_completed") == 1
        # Timer is recorded with labels, so check with labels
        assert agent_metrics.metrics.get_timer_stats(
            "contract_duration_ms",
            labels={"contract_type": "test", "status": "success"}
        )["count"] == 1

    def test_record_error(self):
        """Test recording errors."""
        agent_metrics = AgentMetrics()

        agent_metrics.record_error("timeout", protocol="A2A")
        agent_metrics.record_error("timeout", protocol="ACCP")

        assert agent_metrics.metrics.get_counter("errors_total") == 2


class TestStructuredLogger:
    """Test StructuredLogger."""

    def test_json_formatter(self):
        """Test JSON formatter output."""
        import logging

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.context = {"context": {"request_id": "123"}}

        output = formatter.format(record)
        parsed = eval(output)  # Safe for test

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        # Check that context info is present (structure may vary)
        assert "request_id" in str(parsed)


class TestGlobalInstances:
    """Test global instance functions."""

    def test_get_metrics_singleton(self):
        """Test get_metrics returns singleton."""
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_get_logger_singleton(self):
        """Test get_logger returns singleton."""
        l1 = get_logger()
        l2 = get_logger()
        assert l1 is l2
