"""
Production Server: Hardened FastAPI server wrapper for AgenLang.

Combines the base A2A server app with production middleware, rate limiting,
circuit breakers, and observability into a single turn-key entry-point.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .circuit_breaker import (
    CircuitBreakerConfig,
    get_registry as get_cb_registry,
)
from .middleware import (
    CORSConfig,
    InputValidationMiddleware,
    SecurityHeadersMiddleware,
)
from .observability import get_logger, get_metrics
from .rate_limiter import (
    MultiRateLimiter,
    RateLimitConfig,
    RateLimitExceeded,
    create_default_limiters,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ProductionConfig:
    """Complete production server configuration."""

    # Network
    host: str = "0.0.0.0"
    port: int = 8000

    # Agent identity / storage
    key_path: Optional[str] = None
    data_dir: Optional[str] = None

    # TLS
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    ssl_ca_certs: Optional[str] = None

    # Rate limiting  (None → use defaults)
    rate_limit_config: Optional[Dict[str, RateLimitConfig]] = None

    # Observability flags
    enable_metrics: bool = True
    enable_tracing: bool = True

    # CORS preset name: "permissive", "restrictive", "a2a" (default)
    cors_preset: str = "a2a"
    cors_allowed_origins: Optional[List[str]] = None

    # Middleware tunables
    max_request_body_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Uvicorn workers (only effective with uvicorn process manager)
    workers: int = 1
    log_level: str = "info"

    @property
    def tls_enabled(self) -> bool:
        return bool(self.ssl_certfile and self.ssl_keyfile)


# ---------------------------------------------------------------------------
# Rate-limit middleware (wraps MultiRateLimiter into Starlette middleware)
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that enforces per-IP and global rate limits."""

    def __init__(self, app, rate_limiter: MultiRateLimiter):
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Derive a client key from the remote IP (or forwarded header)
        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or request.client.host
            if request.client
            else "unknown"
        )

        try:
            # Check IP-level limit
            self.rate_limiter.check_or_raise("ip", client_ip)
            # Check global limit
            self.rate_limiter.check_or_raise("global", "global")
        except RateLimitExceeded as exc:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": str(exc),
                    "retry_after": round(exc.retry_after, 2),
                },
                headers={
                    "Retry-After": str(int(exc.retry_after) + 1),
                    "X-RateLimit-Remaining": str(exc.remaining),
                },
            )

        response = await call_next(request)

        # Attach informational rate-limit headers
        ip_status = self.rate_limiter.get_status("ip", client_ip)
        if ip_status:
            response.headers["X-RateLimit-Remaining"] = str(
                ip_status.get("remaining", "?")
            )
            reset_time = ip_status.get("reset_time")
            if reset_time:
                response.headers["X-RateLimit-Reset"] = str(int(reset_time))

        return response


# ---------------------------------------------------------------------------
# Observability middleware (request timing / counters)
# ---------------------------------------------------------------------------

class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Record per-request metrics and optional trace spans."""

    def __init__(self, app, enable_metrics: bool = True, enable_tracing: bool = True):
        super().__init__(app)
        self.enable_metrics = enable_metrics
        self.enable_tracing = enable_tracing

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        metrics = get_metrics() if self.enable_metrics else None
        logger = get_logger()

        start = time.time()
        span = None

        if self.enable_tracing:
            span = metrics.tracer.start_trace(
                name=f"{request.method} {request.url.path}",
                tags={
                    "http.method": request.method,
                    "http.url": str(request.url),
                },
            ) if metrics else None

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            if metrics:
                metrics.record_error("unhandled_exception", protocol="http")
                metrics.metrics.timer(
                    "http_request_duration_ms",
                    duration_ms,
                    labels={
                        "method": request.method,
                        "path": request.url.path,
                        "status": "500",
                    },
                )
            if span and metrics:
                metrics.tracer.finish_span(span, error=str(exc))
            logger.error(
                "unhandled_request_error",
                method=request.method,
                path=request.url.path,
                error=str(exc),
            )
            raise

        duration_ms = (time.time() - start) * 1000
        status_code = str(response.status_code)

        if metrics:
            metrics.metrics.counter(
                "http_requests_total",
                labels={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                },
            )
            metrics.metrics.timer(
                "http_request_duration_ms",
                duration_ms,
                labels={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                },
            )

        if span and metrics:
            span.tags["http.status_code"] = status_code
            metrics.tracer.finish_span(span)

        return response


# ---------------------------------------------------------------------------
# ProductionServer
# ---------------------------------------------------------------------------

class ProductionServer:
    """Turn-key production server that wraps the base AgenLang FastAPI app.

    Usage::

        server = ProductionServer(ProductionConfig(port=9000))
        server.start()          # blocks (runs uvicorn)

    Or get the configured app for programmatic use::

        app = create_production_app(ProductionConfig())
    """

    def __init__(self, config: Optional[ProductionConfig] = None):
        self.config = config or ProductionConfig()
        self.logger = get_logger("agenlang.server")
        self.app = self._build_app()

    # -- App assembly -----------------------------------------------------

    def _build_app(self) -> FastAPI:
        """Construct the FastAPI application with all production middleware."""
        # Import the base server app (contains routes, lifespan, etc.)
        from .server import app as base_app  # noqa: WPS433

        app = base_app

        # 1. CORS ----------------------------------------------------------
        cors = self._make_cors_config()
        app.add_middleware(CORSMiddleware, **cors.as_middleware_kwargs())

        # 2. Security headers ----------------------------------------------
        app.add_middleware(
            SecurityHeadersMiddleware,
            enable_hsts=self.config.tls_enabled,
        )

        # 3. Input validation ----------------------------------------------
        app.add_middleware(
            InputValidationMiddleware,
            max_body_bytes=self.config.max_request_body_bytes,
        )

        # 4. Rate limiting -------------------------------------------------
        rate_limiter = self._make_rate_limiter()
        app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

        # 5. Observability -------------------------------------------------
        if self.config.enable_metrics or self.config.enable_tracing:
            app.add_middleware(
                ObservabilityMiddleware,
                enable_metrics=self.config.enable_metrics,
                enable_tracing=self.config.enable_tracing,
            )

        # 6. Circuit breakers for known backend services -------------------
        self._setup_circuit_breakers()

        # 7. Observability initialization ----------------------------------
        self._init_observability()

        # 8. Extra production routes (metrics, health-deep, circuit status) -
        self._add_production_routes(app)

        self.logger.info(
            "production_app_configured",
            host=self.config.host,
            port=self.config.port,
            tls=self.config.tls_enabled,
            metrics=self.config.enable_metrics,
            tracing=self.config.enable_tracing,
        )

        return app

    # -- Helpers ----------------------------------------------------------

    def _make_cors_config(self) -> CORSConfig:
        preset = self.config.cors_preset
        if preset == "permissive":
            return CORSConfig.permissive()
        elif preset == "restrictive":
            return CORSConfig.restrictive(self.config.cors_allowed_origins)
        else:
            return CORSConfig.agent_to_agent()

    def _make_rate_limiter(self) -> MultiRateLimiter:
        if self.config.rate_limit_config:
            multi = MultiRateLimiter()
            for name, cfg in self.config.rate_limit_config.items():
                multi.add_limiter(name, cfg)
            return multi
        return create_default_limiters()

    def _setup_circuit_breakers(self) -> None:
        """Pre-register circuit breakers for typical backend services."""
        registry = get_cb_registry()

        # External LLM / inference service
        registry.get_or_create(
            "llm_inference",
            CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=2,
                timeout_seconds=60.0,
            ),
        )

        # Database / storage backend
        registry.get_or_create(
            "database",
            CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=30.0,
            ),
        )

        # External agent communication
        registry.get_or_create(
            "agent_outbound",
            CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=3,
                timeout_seconds=45.0,
            ),
        )

        # Settlement / payment service
        registry.get_or_create(
            "settlement",
            CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_seconds=60.0,
            ),
        )

        self.logger.info(
            "circuit_breakers_configured",
            breakers=list(registry.all_statuses().keys()),
        )

    def _init_observability(self) -> None:
        """Bootstrap metrics collector and mark start time."""
        if self.config.enable_metrics:
            metrics = get_metrics()
            metrics.mark_start_time()
            self.logger.info("metrics_collector_initialized")

        if self.config.enable_tracing:
            self.logger.info("tracing_enabled")

    def _add_production_routes(self, app: FastAPI) -> None:
        """Register additional routes useful in production."""

        @app.get("/metrics")
        async def metrics_endpoint() -> Dict[str, Any]:
            """Expose internal metrics as JSON."""
            m = get_metrics()
            return {
                "health": m.get_health_metrics(),
                "metrics": m.metrics.get_all_metrics(),
            }

        @app.get("/circuit-breakers")
        async def circuit_breaker_status() -> Dict[str, Any]:
            """Current state of all circuit breakers."""
            return get_cb_registry().all_statuses()

        @app.get("/health/deep")
        async def deep_health_check() -> Dict[str, Any]:
            """Deep health check including subsystem status."""
            cb_statuses = get_cb_registry().all_statuses()
            all_closed = all(
                s.get("state") == "CLOSED" for s in cb_statuses.values()
            )
            m = get_metrics()
            return {
                "status": "healthy" if all_closed else "degraded",
                "circuit_breakers": cb_statuses,
                "health_metrics": m.get_health_metrics(),
            }

        @app.get("/traces")
        async def recent_traces(limit: int = 20) -> Dict[str, Any]:
            """List recent traces."""
            m = get_metrics()
            return {"traces": m.tracer.get_recent_traces(limit=limit)}

    # -- Start / Run ------------------------------------------------------

    def start(self) -> None:
        """Start the production server (blocking)."""
        import uvicorn

        uvicorn_kwargs: Dict[str, Any] = {
            "app": self.app,
            "host": self.config.host,
            "port": self.config.port,
            "log_level": self.config.log_level,
            "workers": self.config.workers,
        }

        if self.config.tls_enabled:
            uvicorn_kwargs["ssl_certfile"] = self.config.ssl_certfile
            uvicorn_kwargs["ssl_keyfile"] = self.config.ssl_keyfile
            if self.config.ssl_ca_certs:
                uvicorn_kwargs["ssl_ca_certs"] = self.config.ssl_ca_certs

        scheme = "https" if self.config.tls_enabled else "http"
        self.logger.info(
            "starting_production_server",
            url=f"{scheme}://{self.config.host}:{self.config.port}",
        )

        uvicorn.run(**uvicorn_kwargs)


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def create_production_app(
    config: Optional[ProductionConfig] = None,
) -> FastAPI:
    """Create and return a fully configured production FastAPI application.

    This is the recommended entry-point when you need the app object
    without immediately starting the server (e.g. for ``gunicorn`` or
    testing).

    Example::

        # gunicorn -k uvicorn.workers.UvicornWorker myapp:app
        app = create_production_app(ProductionConfig(port=9000))
    """
    server = ProductionServer(config)
    return server.app
