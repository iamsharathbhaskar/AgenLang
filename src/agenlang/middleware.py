"""
Middleware: Reusable Starlette middleware components for AgenLang servers.

Provides input validation, security headers, and CORS configuration
for production deployments.
"""

import uuid
import time
from dataclasses import dataclass, field
from typing import List, Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


# ---------------------------------------------------------------------------
# 1. InputValidationMiddleware
# ---------------------------------------------------------------------------

class InputValidationMiddleware(BaseHTTPMiddleware):
    """Validate incoming requests before they reach route handlers.

    Enforcements:
    - Max request body size (default 10 MB).
    - Content-Type must be ``application/json`` for POST/PUT/PATCH.
    - Path traversal sequences (``..``) are rejected.
    - Every response gets an ``X-Request-ID`` header (generated if absent).
    """

    def __init__(
        self,
        app,
        max_body_bytes: int = 10 * 1024 * 1024,  # 10 MB
        enforce_json_content_type: bool = True,
    ):
        super().__init__(app)
        self.max_body_bytes = max_body_bytes
        self.enforce_json_content_type = enforce_json_content_type

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # -- Request ID ---------------------------------------------------
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        # Stash on request state so downstream handlers can use it
        request.state.request_id = request_id

        # -- Path traversal check -----------------------------------------
        if ".." in request.url.path:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "path_traversal_rejected",
                    "detail": "Path contains disallowed traversal sequence '..'",
                    "request_id": request_id,
                },
            )

        # -- Content-Type check for mutating methods ----------------------
        if self.enforce_json_content_type and request.method in (
            "POST", "PUT", "PATCH",
        ):
            content_type = (request.headers.get("content-type") or "").lower()
            if not content_type.startswith("application/json"):
                return JSONResponse(
                    status_code=415,
                    content={
                        "error": "unsupported_media_type",
                        "detail": (
                            "Content-Type must be application/json for "
                            f"{request.method} requests"
                        ),
                        "request_id": request_id,
                    },
                )

        # -- Body size check ----------------------------------------------
        content_length_header = request.headers.get("content-length")
        if content_length_header is not None:
            try:
                content_length = int(content_length_header)
            except (ValueError, TypeError):
                content_length = 0
            if content_length > self.max_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "request_entity_too_large",
                        "detail": (
                            f"Request body exceeds maximum allowed size "
                            f"of {self.max_body_bytes} bytes"
                        ),
                        "request_id": request_id,
                    },
                )

        # For chunked / streaming uploads without Content-Length we read
        # the body ourselves and enforce the limit.
        if request.method in ("POST", "PUT", "PATCH") and content_length_header is None:
            body = await request.body()
            if len(body) > self.max_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "request_entity_too_large",
                        "detail": (
                            f"Request body exceeds maximum allowed size "
                            f"of {self.max_body_bytes} bytes"
                        ),
                        "request_id": request_id,
                    },
                )

        # -- Forward to next middleware / handler -------------------------
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# 2. SecurityHeadersMiddleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject standard security headers into every response.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Content-Security-Policy: default-src 'self'
    - Strict-Transport-Security (only when ``enable_hsts`` is True,
      i.e. the server is behind TLS)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: geolocation=(), camera=(), microphone=()
    """

    def __init__(
        self,
        app,
        enable_hsts: bool = False,
        hsts_max_age: int = 31_536_000,  # 1 year
        content_security_policy: str = "default-src 'self'",
        custom_headers: Optional[dict] = None,
    ):
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.hsts_max_age = hsts_max_age
        self.content_security_policy = content_security_policy
        self.custom_headers = custom_headers or {}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = self.content_security_policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=()"
        )

        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={self.hsts_max_age}; includeSubDomains"
            )

        for key, value in self.custom_headers.items():
            response.headers[key] = value

        return response


# ---------------------------------------------------------------------------
# 3. CORSConfig helper
# ---------------------------------------------------------------------------

@dataclass
class CORSConfig:
    """Convenience wrapper for FastAPI/Starlette CORS middleware settings.

    Usage::

        from fastapi.middleware.cors import CORSMiddleware
        cors = CORSConfig.permissive()
        app.add_middleware(CORSMiddleware, **cors.as_middleware_kwargs())
    """

    allow_origins: List[str] = field(default_factory=lambda: ["*"])
    allow_methods: List[str] = field(default_factory=lambda: ["*"])
    allow_headers: List[str] = field(default_factory=lambda: ["*"])
    allow_credentials: bool = False
    expose_headers: List[str] = field(
        default_factory=lambda: ["X-Request-ID", "X-RateLimit-Remaining"]
    )
    max_age: int = 600  # 10 minutes

    def as_middleware_kwargs(self) -> dict:
        """Return dict suitable for ``app.add_middleware(CORSMiddleware, ...)``."""
        return {
            "allow_origins": self.allow_origins,
            "allow_methods": self.allow_methods,
            "allow_headers": self.allow_headers,
            "allow_credentials": self.allow_credentials,
            "expose_headers": self.expose_headers,
            "max_age": self.max_age,
        }

    # -- Presets ----------------------------------------------------------

    @classmethod
    def permissive(cls) -> "CORSConfig":
        """Allow everything — useful for local development."""
        return cls(
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
            max_age=600,
        )

    @classmethod
    def restrictive(cls, allowed_origins: Optional[List[str]] = None) -> "CORSConfig":
        """Locked-down CORS for production.

        Only the explicitly listed origins are permitted.
        """
        return cls(
            allow_origins=allowed_origins or [],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            allow_credentials=True,
            max_age=3600,
        )

    @classmethod
    def agent_to_agent(cls) -> "CORSConfig":
        """Preset tuned for server-to-server A2A communication.

        No browser credentials, but wide method/header support.
        """
        return cls(
            allow_origins=["*"],
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-Request-ID",
                "X-Agent-DID",
            ],
            allow_credentials=False,
            expose_headers=[
                "X-Request-ID",
                "X-RateLimit-Remaining",
                "X-RateLimit-Reset",
            ],
            max_age=86400,  # 24 hours
        )
