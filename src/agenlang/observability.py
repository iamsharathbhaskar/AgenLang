"""
Observability: Metrics, Logging, and Tracing for AgenLang
Production-grade monitoring for agent communication
"""

import time
import uuid
import json
import logging
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .contract import Contract


class MetricType(Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class Metric:
    """A single metric point."""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class TraceSpan:
    """A trace span for distributed tracing."""
    name: str
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    tags: Dict[str, str] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def duration_ms(self) -> float:
        """Get span duration in milliseconds."""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms(),
            "tags": self.tags,
            "logs": self.logs,
            "error": self.error,
        }


class MetricsCollector:
    """Collect and aggregate metrics."""

    def __init__(self):
        self._metrics: List[Metric] = []
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()

    def counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Increment a counter."""
        with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] += value
            self._metrics.append(Metric(name, MetricType.COUNTER, value, labels or {}))

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Set a gauge value."""
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value
            self._metrics.append(Metric(name, MetricType.GAUGE, value, labels or {}))

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a histogram value."""
        with self._lock:
            key = self._make_key(name, labels)
            self._histograms[key].append(value)
            self._metrics.append(Metric(name, MetricType.HISTOGRAM, value, labels or {}))

    def timer(self, name: str, value_ms: float, labels: Optional[Dict[str, str]] = None):
        """Record a timer value."""
        with self._lock:
            key = self._make_key(name, labels)
            self._timers[key].append(value_ms)
            self._metrics.append(Metric(name, MetricType.TIMER, value_ms, labels or {}))

    @contextmanager
    def timed(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Context manager for timing operations."""
        start = time.time()
        try:
            yield self
        finally:
            duration = (time.time() - start) * 1000
            self.timer(name, duration, labels)

    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get counter value."""
        if labels is None or not labels:
            # Sum all counters with this base name
            total = 0.0
            for key, value in self._counters.items():
                base = self._get_base_key(key)
                if base == name:
                    total += value
            return total
        key = self._make_key(name, labels)
        return self._counters.get(key, 0.0)

    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> Optional[float]:
        """Get gauge value."""
        key = self._make_key(name, labels)
        return self._gauges.get(key)

    def get_histogram_stats(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get histogram statistics."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "mean": 0, "p95": 0, "p99": 0}

        sorted_vals = sorted(values)
        count = len(sorted_vals)
        return {
            "count": count,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "mean": sum(sorted_vals) / count,
            "p95": sorted_vals[int(count * 0.95)],
            "p99": sorted_vals[int(count * 0.99)],
        }

    def get_timer_stats(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Get timer statistics (alias for histogram)."""
        key = self._make_key(name, labels)
        values = self._timers.get(key, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "mean": 0, "p95": 0, "p99": 0}

        sorted_vals = sorted(values)
        count = len(sorted_vals)
        return {
            "count": count,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "mean": sum(sorted_vals) / count,
            "p95": sorted_vals[int(count * 0.95)],
            "p99": sorted_vals[int(count * 0.99)],
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics as dictionary."""
        with self._lock:
            # For timers and histograms, we need to look up by the full key
            # but the key is already the full labeled key
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: self.get_histogram_stats_for_key(k) for k in self._histograms.keys()},
                "timers": {k: self.get_timer_stats_for_key(k) for k in self._timers.keys()},
            }

    def get_histogram_stats_for_key(self, key: str) -> Dict[str, float]:
        """Get histogram stats for a pre-built key."""
        values = self._histograms.get(key, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "mean": 0, "p95": 0, "p99": 0}

        sorted_vals = sorted(values)
        count = len(sorted_vals)
        return {
            "count": count,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "mean": sum(sorted_vals) / count,
            "p95": sorted_vals[int(count * 0.95)] if count > 1 else sorted_vals[0],
            "p99": sorted_vals[int(count * 0.99)] if count > 1 else sorted_vals[0],
        }

    def get_timer_stats_for_key(self, key: str) -> Dict[str, float]:
        """Get timer stats for a pre-built key."""
        values = self._timers.get(key, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "mean": 0, "p95": 0, "p99": 0}

        sorted_vals = sorted(values)
        count = len(sorted_vals)
        return {
            "count": count,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "mean": sum(sorted_vals) / count,
            "p95": sorted_vals[int(count * 0.95)] if count > 1 else sorted_vals[0],
            "p99": sorted_vals[int(count * 0.99)] if count > 1 else sorted_vals[0],
        }

    def reset(self):
        """Reset all metrics."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._timers.clear()

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create unique key from name and labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def _get_base_key(self, key: str) -> str:
        """Extract base metric name from key."""
        if "{" in key:
            return key.split("{")[0]
        return key


class Tracer:
    """Distributed tracing for agent communication."""

    def __init__(self, service_name: str = "agenlang"):
        self.service_name = service_name
        self._spans: List[TraceSpan] = []
        self._lock = Lock()
        self._current_trace: Optional[str] = None

    def start_trace(self, name: str, tags: Optional[Dict[str, str]] = None) -> TraceSpan:
        """Start a new trace."""
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())[:16]
        span = TraceSpan(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            tags=tags or {},
        )
        with self._lock:
            self._spans.append(span)
            self._current_trace = trace_id
        return span

    def start_span(
        self,
        name: str,
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> TraceSpan:
        """Start a new span."""
        span = TraceSpan(
            name=name,
            trace_id=trace_id or self._current_trace or str(uuid.uuid4()),
            span_id=str(uuid.uuid4())[:16],
            parent_id=parent_id,
            tags=tags or {},
        )
        with self._lock:
            self._spans.append(span)
        return span

    def finish_span(self, span: TraceSpan, error: Optional[str] = None):
        """Finish a span."""
        span.end_time = time.time()
        span.error = error

    @contextmanager
    def span(
        self,
        name: str,
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ):
        """Context manager for spans."""
        span = self.start_span(name, parent_id, trace_id, tags)
        try:
            yield span
        except Exception as e:
            self.finish_span(span, error=str(e))
            raise
        else:
            self.finish_span(span)

    def log_event(self, span: TraceSpan, event: str, payload: Optional[Dict[str, Any]] = None):
        """Log an event within a span."""
        span.logs.append({
            "timestamp": time.time(),
            "event": event,
            "payload": payload or {},
        })

    def get_trace(self, trace_id: str) -> List[TraceSpan]:
        """Get all spans for a trace."""
        return [s for s in self._spans if s.trace_id == trace_id]

    def get_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent traces summary."""
        traces: Dict[str, List[TraceSpan]] = defaultdict(list)
        for span in self._spans:
            traces[span.trace_id].append(span)

        sorted_traces = sorted(
            traces.items(),
            key=lambda x: max(s.start_time for s in x[1]),
            reverse=True,
        )[:limit]

        result = []
        for trace_id, spans in sorted_traces:
            root = next((s for s in spans if s.parent_id is None), spans[0])
            result.append({
                "trace_id": trace_id,
                "name": root.name,
                "start_time": root.start_time,
                "duration_ms": max(s.end_time or time.time() for s in spans) - root.start_time,
                "span_count": len(spans),
                "error_count": sum(1 for s in spans if s.error),
            })
        return result

    def to_jaeger_format(self) -> List[Dict[str, Any]]:
        """Export spans in Jaeger-compatible format."""
        return [span.to_dict() for span in self._spans]

    def clear(self):
        """Clear all spans."""
        with self._lock:
            self._spans.clear()


class AgentMetrics:
    """High-level metrics for agent operations."""

    def __init__(self):
        self.metrics = MetricsCollector()
        self.tracer = Tracer()

    def record_contract_created(self, contract_id: str, contract_type: str = "default"):
        """Record contract creation."""
        self.metrics.counter("contracts_created", labels={
            "contract_type": contract_type,
        })

    def record_contract_completed(
        self,
        contract_id: str,
        duration_ms: float,
        success: bool = True,
        contract_type: str = "default",
    ):
        """Record contract completion."""
        self.metrics.counter("contracts_completed", labels={
            "contract_type": contract_type,
            "status": "success" if success else "failed",
        })
        self.metrics.timer("contract_duration_ms", duration_ms, labels={
            "contract_type": contract_type,
            "status": "success" if success else "failed",
        })

    def record_message_sent(self, protocol: str, message_type: str):
        """Record message sent."""
        self.metrics.counter("messages_sent", labels={
            "protocol": protocol,
            "type": message_type,
        })

    def record_message_received(self, protocol: str, message_type: str):
        """Record message received."""
        self.metrics.counter("messages_received", labels={
            "protocol": protocol,
            "type": message_type,
        })

    def record_contract_execution(self, contract_type: str, duration_ms: float, success: bool):
        """Record contract execution."""
        self.metrics.counter("contracts_executed", labels={
            "type": contract_type,
            "status": "success" if success else "failed",
        })
        self.metrics.timer("contract_execution_ms", duration_ms, labels={
            "type": contract_type,
        })

    def record_payment(self, amount: float, token: str, success: bool = True):
        """Record payment."""
        self.metrics.counter("payments_total", value=amount, labels={
            "token": token,
            "status": "success" if success else "failed",
        })
        self.metrics.counter("payments_count", labels={
            "token": token,
            "status": "success" if success else "failed",
        })

    def record_error(self, error_type: str, protocol: Optional[str] = None):
        """Record error."""
        labels = {"type": error_type}
        if protocol:
            labels["protocol"] = protocol
        self.metrics.counter("errors_total", labels=labels)

    def set_active_contracts(self, count: int):
        """Set active contracts gauge."""
        self.metrics.gauge("active_contracts", count)

    def set_connected_agents(self, count: int):
        """Set connected agents gauge."""
        self.metrics.gauge("connected_agents", count)

    def get_health_metrics(self) -> Dict[str, Any]:
        """Get health-related metrics."""
        return {
            "uptime_seconds": time.time() - self._start_time if hasattr(self, '_start_time') else 0,
            "active_contracts": self.metrics.get_gauge("active_contracts") or 0,
            "connected_agents": self.metrics.get_gauge("connected_agents") or 0,
            "contracts_created": self.metrics.get_counter("contracts_created"),
            "contracts_completed": self.metrics.get_counter("contracts_completed"),
            "errors_total": self.metrics.get_counter("errors_total"),
        }

    def mark_start_time(self):
        """Mark service start time."""
        self._start_time = time.time()


class StructuredLogger:
    """Structured JSON logger for production."""

    LEVELS = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    def __init__(self, name: str = "agenlang", level: str = "INFO"):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.LEVELS.get(level, logging.INFO))

        # Add JSON formatter handler if not already set
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter())
            self.logger.addHandler(handler)

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        self._log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self._log("CRITICAL", message, **kwargs)

    def _log(self, level: str, message: str, **kwargs):
        """Internal log method."""
        extra = {
            "logger": self.name,
            "context": kwargs,
        }
        log_method = getattr(self.logger, level.lower())
        log_method(message, extra={"context": extra})


class JsonFormatter(logging.Formatter):
    """JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context if present
        if hasattr(record, "context"):
            log_data.update(record.context)

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


# Global instances
_agent_metrics: Optional[AgentMetrics] = None
_structured_logger: Optional[StructuredLogger] = None


def get_metrics() -> AgentMetrics:
    """Get or create global metrics instance."""
    global _agent_metrics
    if _agent_metrics is None:
        _agent_metrics = AgentMetrics()
    return _agent_metrics


def get_logger(name: str = "agenlang") -> StructuredLogger:
    """Get or create global logger instance."""
    global _structured_logger
    if _structured_logger is None:
        _structured_logger = StructuredLogger(name)
    return _structured_logger


def set_metrics(metrics: AgentMetrics):
    """Set global metrics instance."""
    global _agent_metrics
    _agent_metrics = metrics


def set_logger(logger: StructuredLogger):
    """Set global logger instance."""
    global _structured_logger
    _structured_logger = logger
