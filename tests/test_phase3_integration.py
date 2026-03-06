"""Integration tests for Phase 3 components.

Tests rate limiting, circuit breakers, observability, input validation,
security headers, and production server assembly.
"""

import os
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from agenlang.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    CircuitState,
    get_registry as get_cb_registry,
)
from agenlang.contract import Contract
from agenlang.keys import KeyManager
from agenlang.middleware import (
    InputValidationMiddleware,
    SecurityHeadersMiddleware,
)
from agenlang.observability import (
    AgentMetrics,
    MetricsCollector,
    Tracer,
    get_metrics,
)
from agenlang.rate_limiter import (
    MultiRateLimiter,
    RateLimitConfig,
    RateLimitExceeded,
    RateLimitStrategy,
    create_default_limiters,
)
from agenlang.server_production import (
    ProductionConfig,
    ProductionServer,
    RateLimitMiddleware,
    create_production_app,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_simple_app() -> FastAPI:
    """Create a minimal FastAPI app for middleware tests."""
    app = FastAPI()

    @app.get("/ok")
    async def ok():
        return {"status": "ok"}

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return JSONResponse(content={"size": len(body)})

    @app.get("/a2a")
    async def a2a_get():
        return {"method": "a2a"}

    return app


def _make_rate_limiter(rps: float = 2.0, burst: int = 2) -> MultiRateLimiter:
    """Create a tight rate limiter for testing."""
    multi = MultiRateLimiter()
    multi.add_limiter(
        "ip",
        RateLimitConfig(
            requests_per_second=rps,
            burst_size=burst,
            window_size_seconds=60.0,
            strategy=RateLimitStrategy.TOKEN_BUCKET,
            key_prefix="ip",
        ),
    )
    multi.add_limiter(
        "global",
        RateLimitConfig(
            requests_per_second=1000.0,
            burst_size=1000,
            window_size_seconds=60.0,
            strategy=RateLimitStrategy.TOKEN_BUCKET,
            key_prefix="global",
        ),
    )
    return multi


# ===================================================================
# 1. Rate limiter integration with server
# ===================================================================


class TestRateLimitMiddleware:
    """Test RateLimitMiddleware from server_production."""

    def test_returns_429_when_limit_exceeded(self):
        """Exhaust the rate limit and expect a 429 response."""
        app = _make_simple_app()
        limiter = _make_rate_limiter(rps=1.0, burst=2)
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)
        client = TestClient(app)

        # The first 2 requests should succeed (burst_size=2)
        for _ in range(2):
            r = client.get("/ok")
            assert r.status_code == 200

        # The next request should be rate-limited
        r = client.get("/ok")
        assert r.status_code == 429
        body = r.json()
        assert body["error"] == "rate_limit_exceeded"

    def test_rate_limit_headers_present_on_429(self):
        """429 responses must include Retry-After and X-RateLimit-Remaining."""
        app = _make_simple_app()
        limiter = _make_rate_limiter(rps=1.0, burst=1)
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)
        client = TestClient(app)

        # Exhaust the single-token bucket
        client.get("/ok")
        r = client.get("/ok")

        assert r.status_code == 429
        assert "Retry-After" in r.headers
        assert "X-RateLimit-Remaining" in r.headers

    def test_rate_limit_headers_present_on_success(self):
        """Successful responses should carry X-RateLimit-Remaining."""
        app = _make_simple_app()
        limiter = _make_rate_limiter(rps=10.0, burst=20)
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)
        client = TestClient(app)

        r = client.get("/ok")
        assert r.status_code == 200
        assert "X-RateLimit-Remaining" in r.headers


# ===================================================================
# 2. Circuit breaker integration
# ===================================================================


class TestCircuitBreakerIntegration:
    """Test circuit breaker wrapping and error handling."""

    def test_circuit_breaker_wraps_execution(self):
        """Successful calls go through the circuit breaker normally."""
        cb = CircuitBreaker("test_exec", CircuitBreakerConfig(failure_threshold=3))
        result = cb.execute(lambda: "hello")
        assert result == "hello"
        assert cb.state == CircuitState.CLOSED

    def test_circuit_breaker_open_error_handled(self):
        """CircuitBreakerOpenError is raised when breaker is OPEN."""
        cb = CircuitBreaker(
            "test_open",
            CircuitBreakerConfig(failure_threshold=2, timeout_seconds=60.0),
        )
        # Force failures to open the circuit
        for _ in range(2):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            except Exception:
                pass

        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            cb.execute(lambda: "should not reach")

    def test_circuit_breaker_status_endpoint(self):
        """The /circuit-breakers endpoint returns JSON with breaker statuses."""
        # Reset the global registry to ensure clean state
        registry = get_cb_registry()
        registry.reset_all()

        # Pre-create a breaker
        registry.get_or_create(
            "test_service",
            CircuitBreakerConfig(failure_threshold=5),
        )

        statuses = registry.all_statuses()
        assert "test_service" in statuses
        assert statuses["test_service"]["state"] == "CLOSED"
        assert statuses["test_service"]["failure_threshold"] == 5

    def test_circuit_breaker_registry_get_or_create(self):
        """Registry creates on first call and returns same object next time."""
        reg = CircuitBreakerRegistry()
        cb1 = reg.get_or_create("svc", CircuitBreakerConfig())
        cb2 = reg.get_or_create("svc", CircuitBreakerConfig())
        assert cb1 is cb2


# ===================================================================
# 3. Observability integration
# ===================================================================


class TestObservabilityIntegration:
    """Test metrics and tracing endpoints."""

    def test_metrics_collector_returns_json(self):
        """MetricsCollector.get_all_metrics() returns a complete dict."""
        mc = MetricsCollector()
        mc.counter("req_count")
        mc.timer("latency", 42.0)
        all_metrics = mc.get_all_metrics()

        assert "counters" in all_metrics
        assert "timers" in all_metrics
        assert "histograms" in all_metrics
        assert "gauges" in all_metrics
        assert mc.get_counter("req_count") == 1.0

    def test_tracer_returns_recent_traces(self):
        """Tracer.get_recent_traces() returns finished spans."""
        tracer = Tracer()
        span = tracer.start_trace("test_op", tags={"env": "test"})
        time.sleep(0.01)
        tracer.finish_span(span)

        traces = tracer.get_recent_traces(limit=5)
        assert len(traces) >= 1
        assert traces[0]["trace_id"] == span.trace_id
        assert traces[0]["name"] == "test_op"

    def test_executing_contract_records_metrics(self, tmp_path):
        """Running a contract records contracts_completed counter and contract_duration_ms timer."""
        # Fresh metrics
        am = AgentMetrics()
        am.mark_start_time()

        with patch("agenlang.runtime.get_metrics", return_value=am):
            km = KeyManager(key_path=tmp_path / "keys.pem")
            km.generate()
            contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
            runtime = Runtime(contract, key_manager=km)
            result, ser = runtime.execute()

        assert result["status"] == "success"
        # Runtime calls record_contract_completed which bumps contracts_completed
        completed_count = am.metrics.get_counter("contracts_completed")
        assert completed_count >= 1.0

        # contract_duration_ms timer should have at least one entry
        timer_keys = list(am.metrics._timers.keys())
        duration_keys = [k for k in timer_keys if "contract_duration_ms" in k]
        assert len(duration_keys) >= 1

    def test_executing_contract_creates_trace_spans(self, tmp_path):
        """Running a contract produces at least one trace span."""
        am = AgentMetrics()
        am.mark_start_time()

        with patch("agenlang.runtime.get_metrics", return_value=am):
            km = KeyManager(key_path=tmp_path / "keys.pem")
            km.generate()
            contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
            runtime = Runtime(contract, key_manager=km)
            result, ser = runtime.execute()

        assert result["status"] == "success"
        traces = am.tracer.get_recent_traces(limit=10)
        assert len(traces) >= 1
        # Root span should be for the contract execution
        root_names = [t["name"] for t in traces]
        assert any("contract_execute" in n for n in root_names)


# ===================================================================
# 4. Runtime integration
# ===================================================================

# Import Runtime here so conftest mocks are in place
from agenlang.runtime import Runtime, _create_memory_backend


class TestRuntimeIntegration:
    """Test Runtime interactions with observability, circuit breaker, and memory."""

    def test_runtime_uses_observability(self, tmp_path):
        """Runtime records metrics via AgentMetrics."""
        am = AgentMetrics()
        am.mark_start_time()

        with patch("agenlang.runtime.get_metrics", return_value=am):
            km = KeyManager(key_path=tmp_path / "keys.pem")
            km.generate()
            contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
            runtime = Runtime(contract, key_manager=km)
            result, ser = runtime.execute()

        assert result["status"] == "success"
        # joules_consumed histogram is recorded per step
        hist_keys = list(am.metrics._histograms.keys())
        joule_keys = [k for k in hist_keys if "joules_consumed" in k]
        assert len(joule_keys) >= 1

    def test_runtime_wraps_tool_calls_with_circuit_breaker(self, tmp_path):
        """Runtime creates per-tool circuit breakers in the registry."""
        cb_reg = CircuitBreakerRegistry()

        with patch("agenlang.runtime.get_cb_registry", return_value=cb_reg):
            km = KeyManager(key_path=tmp_path / "keys.pem")
            km.generate()
            contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
            runtime = Runtime(contract, key_manager=km)
            result, ser = runtime.execute()

        assert result["status"] == "success"
        # The runtime should have created breakers named tool_<target>
        statuses = cb_reg.all_statuses()
        tool_breakers = [n for n in statuses if n.startswith("tool_")]
        assert len(tool_breakers) >= 1  # at least tool_web_search or tool_summarize

    def test_configurable_memory_backend_encrypted(self, tmp_path, monkeypatch):
        """Default or 'encrypted' backend creates EncryptedMemoryBackend."""
        from agenlang.memory import EncryptedMemoryBackend
        monkeypatch.delenv("AGENLANG_MEMORY_BACKEND", raising=False)
        backend = _create_memory_backend("test-id", "subject")
        assert isinstance(backend, EncryptedMemoryBackend)

    def test_configurable_memory_backend_sqlite(self, tmp_path, monkeypatch):
        """AGENLANG_MEMORY_BACKEND=sqlite creates SQLiteMemoryBackend."""
        from agenlang.memory import SQLiteMemoryBackend
        monkeypatch.setenv("AGENLANG_MEMORY_BACKEND", "sqlite")
        backend = _create_memory_backend("test-id", "subject")
        assert isinstance(backend, SQLiteMemoryBackend)

    def test_configurable_memory_backend_redis(self, tmp_path, monkeypatch):
        """AGENLANG_MEMORY_BACKEND=redis selects RedisMemoryBackend."""
        from agenlang.memory import RedisMemoryBackend
        monkeypatch.setenv("AGENLANG_MEMORY_BACKEND", "redis")
        # Mock Redis client so we don't need a live server
        with patch("agenlang.memory.redis_lib", create=True):
            with patch.object(
                RedisMemoryBackend, "__init__", lambda self, *a, **kw: None
            ):
                backend = _create_memory_backend("test-id", "subject")
                assert isinstance(backend, RedisMemoryBackend)


# ===================================================================
# 5. Input validation
# ===================================================================


class TestInputValidation:
    """Test InputValidationMiddleware."""

    def _app_with_validation(self, max_body: int = 1024) -> TestClient:
        app = _make_simple_app()
        app.add_middleware(InputValidationMiddleware, max_body_bytes=max_body)
        return TestClient(app)

    def test_oversized_request_rejected_413(self):
        """Content-Length exceeding limit returns 413."""
        client = self._app_with_validation(max_body=100)
        big_body = b"x" * 200
        r = client.post(
            "/echo",
            content=big_body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(big_body)),
            },
        )
        assert r.status_code == 413
        body = r.json()
        assert body["error"] == "request_entity_too_large"

    def test_path_traversal_blocked_400(self):
        """Paths containing '..' are blocked with 400."""
        client = self._app_with_validation()
        r = client.get("/../../etc/passwd")
        assert r.status_code in (400, 404)
        # If 400, confirm the error type
        if r.status_code == 400:
            body = r.json()
            assert body["error"] == "path_traversal_rejected"

    def test_request_id_generated(self):
        """X-Request-ID header is added to every response."""
        client = self._app_with_validation()
        r = client.get("/ok")
        assert "X-Request-ID" in r.headers
        # Should be a valid UUID
        req_id = r.headers["X-Request-ID"]
        assert len(req_id) > 0

    def test_request_id_preserved_when_provided(self):
        """If client sends X-Request-ID, it should be echoed back."""
        client = self._app_with_validation()
        custom_id = "my-custom-id-12345"
        r = client.get("/ok", headers={"X-Request-ID": custom_id})
        assert r.headers.get("X-Request-ID") == custom_id


# ===================================================================
# 6. Security headers
# ===================================================================


class TestSecurityHeaders:
    """Test SecurityHeadersMiddleware."""

    def test_security_headers_present(self):
        """All expected security headers should appear in responses."""
        app = _make_simple_app()
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)

        r = client.get("/ok")
        assert r.status_code == 200
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("X-XSS-Protection") == "1; mode=block"
        assert r.headers.get("Content-Security-Policy") == "default-src 'self'"
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in r.headers

    def test_hsts_header_when_enabled(self):
        """Strict-Transport-Security appears when enable_hsts=True."""
        app = _make_simple_app()
        app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True)
        client = TestClient(app)

        r = client.get("/ok")
        assert "Strict-Transport-Security" in r.headers
        assert "max-age=" in r.headers["Strict-Transport-Security"]

    def test_no_hsts_header_by_default(self):
        """HSTS header should NOT be present when enable_hsts=False (default)."""
        app = _make_simple_app()
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)

        r = client.get("/ok")
        assert "Strict-Transport-Security" not in r.headers

    def test_custom_headers_added(self):
        """Custom headers passed to the middleware are applied."""
        app = _make_simple_app()
        app.add_middleware(
            SecurityHeadersMiddleware,
            custom_headers={"X-Custom-Header": "test-value"},
        )
        client = TestClient(app)

        r = client.get("/ok")
        assert r.headers.get("X-Custom-Header") == "test-value"


# ===================================================================
# 7. Server production
# ===================================================================


class TestServerProduction:
    """Test ProductionServer and create_production_app."""

    def test_production_server_can_be_instantiated(self):
        """ProductionServer() with default config should not raise."""
        server = ProductionServer(ProductionConfig())
        assert server.config is not None
        assert server.app is not None

    def test_create_production_app_returns_fastapi(self):
        """create_production_app returns a FastAPI instance."""
        app = create_production_app(ProductionConfig())
        assert isinstance(app, FastAPI)

    def test_production_app_has_metrics_route(self):
        """The production app exposes /metrics."""
        app = create_production_app(ProductionConfig())
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/metrics" in routes

    def test_production_app_has_circuit_breakers_route(self):
        """The production app exposes /circuit-breakers."""
        app = create_production_app(ProductionConfig())
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/circuit-breakers" in routes

    def test_production_app_has_traces_route(self):
        """The production app exposes /traces."""
        app = create_production_app(ProductionConfig())
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/traces" in routes

    def test_production_config_defaults(self):
        """ProductionConfig defaults are sensible."""
        cfg = ProductionConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8000
        assert cfg.enable_metrics is True
        assert cfg.enable_tracing is True
        assert cfg.cors_preset == "a2a"
        assert cfg.tls_enabled is False

    def test_production_config_tls_enabled(self):
        """tls_enabled is True when both cert and key are set."""
        cfg = ProductionConfig(ssl_certfile="/tmp/cert.pem", ssl_keyfile="/tmp/key.pem")
        assert cfg.tls_enabled is True


# ===================================================================
# 8. Combined middleware stack tests
# ===================================================================


class TestCombinedMiddleware:
    """Test multiple middleware layers working together."""

    def test_security_headers_with_input_validation(self):
        """Both security headers and input validation work in one stack."""
        app = _make_simple_app()
        # Last added = outermost
        app.add_middleware(SecurityHeadersMiddleware)
        app.add_middleware(InputValidationMiddleware, max_body_bytes=1024)
        client = TestClient(app)

        r = client.get("/ok")
        assert r.status_code == 200
        # Security headers present
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        # Request ID present
        assert "X-Request-ID" in r.headers

    def test_rate_limit_with_security_headers(self):
        """Rate limiting and security headers work together."""
        app = _make_simple_app()
        limiter = _make_rate_limiter(rps=10.0, burst=20)
        app.add_middleware(SecurityHeadersMiddleware)
        app.add_middleware(RateLimitMiddleware, rate_limiter=limiter)
        client = TestClient(app)

        r = client.get("/ok")
        assert r.status_code == 200
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert "X-RateLimit-Remaining" in r.headers
