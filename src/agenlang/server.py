"""A2A Server — FastAPI-based AgenLang contract receiver and executor.

Provides HTTP JSON-RPC endpoint and SSE streaming for A2A protocol.
Includes rate limiting, circuit breakers, observability, TLS support,
and input validation.
"""

import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .a2a import a2a_payload_to_contract, contract_to_a2a_payload
from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerExecutionError,
    CircuitBreakerOpenError,
    get_registry as get_cb_registry,
)
from .contract import Contract
from .keys import KeyManager
from .observability import AgentMetrics, Tracer, get_logger, get_metrics
from .rate_limiter import RateLimitExceeded, create_default_limiters
from .runtime import Runtime

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Path traversal validation
# ---------------------------------------------------------------------------

def validate_path_safe(path: str) -> str:
    """Validate a file path is safe (no path traversal).

    Returns the resolved absolute path if safe, raises ValueError otherwise.
    """
    expanded = os.path.expanduser(path)
    resolved = os.path.realpath(expanded)
    # Ensure no ".." components remain and path doesn't escape expected roots
    if ".." in os.path.normpath(path).split(os.sep):
        raise ValueError(f"Path traversal detected in: {path}")
    return resolved


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ExecuteRequest(BaseModel):
    """JSON-RPC 2.0 request for agenlang/execute."""

    jsonrpc: str = "2.0"
    method: str
    id: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[str] = None


class ServerConfig(BaseModel):
    """A2A Server configuration."""

    host: str = "0.0.0.0"
    port: int = 8000
    key_path: Optional[str] = None
    max_concurrent: int = 10
    request_timeout: float = 300.0  # 5 minutes

    # TLS configuration
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    ssl_ca_certs: Optional[str] = None

    # Input validation
    max_body_size: int = 10 * 1024 * 1024  # 10 MB default


# ---------------------------------------------------------------------------
# Middleware: Rate Limiting
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces per-IP rate limits on A2A endpoints."""

    RATE_LIMITED_PATHS = {"/a2a", "/a2a/stream"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path not in self.RATE_LIMITED_PATHS:
            return await call_next(request)

        # Use the global rate limiter
        rate_limiter = _rate_limiter
        if rate_limiter is None:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        try:
            # Check per-IP rate limit
            rate_limiter.check_or_raise("ip", client_ip)
        except RateLimitExceeded as exc:
            metrics = get_metrics()
            metrics.metrics.counter("rate_limit_exceeded", labels={"ip": client_ip, "path": path})
            return JSONResponse(
                status_code=429,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32029,
                        "message": f"Rate limit exceeded. Retry after {exc.retry_after:.1f}s",
                    },
                    "id": None,
                },
                headers={"Retry-After": str(int(exc.retry_after + 1))},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Middleware: Request Tracing
# ---------------------------------------------------------------------------

class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Middleware that creates a trace span for each request and records
    duration metrics.  Adds X-Request-ID header to every response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        metrics = get_metrics()
        tracer = metrics.tracer

        span = tracer.start_trace(
            name=f"{request.method} {request.url.path}",
            tags={
                "http.method": request.method,
                "http.url": str(request.url.path),
                "request_id": request_id,
            },
        )

        start = time.time()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            tracer.finish_span(span, error=str(exc))
            metrics.metrics.timer("request_duration_ms", duration_ms, labels={
                "method": request.method,
                "path": request.url.path,
                "status": "500",
            })
            raise
        else:
            duration_ms = (time.time() - start) * 1000
            span.tags["http.status_code"] = str(response.status_code)
            tracer.finish_span(span)
            metrics.metrics.timer("request_duration_ms", duration_ms, labels={
                "method": request.method,
                "path": request.url.path,
                "status": str(response.status_code),
            })

        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Middleware: Body Size Enforcement
# ---------------------------------------------------------------------------

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds max_body_size."""

    async def dispatch(self, request: Request, call_next):
        config = _server_config
        if config is not None:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > config.max_body_size:
                return JSONResponse(
                    status_code=413,
                    content={
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32600,
                            "message": f"Request body too large. Max {config.max_body_size} bytes.",
                        },
                        "id": None,
                    },
                )
        return await call_next(request)


# ---------------------------------------------------------------------------
# Execution Queue
# ---------------------------------------------------------------------------

class ExecutionQueue:
    """In-memory queue for async contract execution."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._results: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def submit(
        self, contract: Contract, key_manager: KeyManager
    ) -> str:
        """Submit a contract for execution. Returns execution ID."""
        execution_id = str(uuid.uuid4())
        await self._queue.put({
            "execution_id": execution_id,
            "contract": contract,
            "key_manager": key_manager,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        })
        log.info("contract_submitted", execution_id=execution_id, contract_id=contract.contract_id)

        # Record metric
        metrics = get_metrics()
        metrics.metrics.counter("contracts_submitted")

        return execution_id

    async def get_result(self, execution_id: str, timeout: float = 300.0) -> Optional[Dict[str, Any]]:
        """Get execution result with timeout."""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            async with self._lock:
                if execution_id in self._results:
                    return self._results.pop(execution_id)
            await asyncio.sleep(0.1)
        return None

    async def process_queue(self) -> None:
        """Background task to process the execution queue."""
        # Get or create the circuit breaker for contract execution
        cb_registry = get_cb_registry()
        cb = cb_registry.get_or_create(
            "contract_execution",
            CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=3,
                timeout_seconds=30.0,
            ),
        )

        while True:
            try:
                item = await self._queue.get()
                execution_id = item["execution_id"]
                contract = item["contract"]
                key_manager = item["key_manager"]

                log.info("executing_contract", execution_id=execution_id, contract_id=contract.contract_id)

                # Get registry reference
                from .server import _registry

                metrics = get_metrics()
                exec_start = time.time()

                try:
                    # Execute with circuit breaker protection
                    def _do_execute():
                        runtime = Runtime(contract, key_manager=key_manager)
                        return runtime.execute()

                    try:
                        result, ser = cb.execute(_do_execute)
                    except CircuitBreakerOpenError:
                        raise RuntimeError(
                            "Circuit breaker 'contract_execution' is OPEN – too many recent failures"
                        )
                    except CircuitBreakerExecutionError as cbe:
                        raise cbe.original_error

                    exec_duration_ms = (time.time() - exec_start) * 1000
                    metrics.metrics.timer("execution_duration_ms", exec_duration_ms)
                    metrics.metrics.counter("contracts_executed", labels={"status": "success"})

                    async with self._lock:
                        self._results[execution_id] = {
                            "status": "success",
                            "result": result,
                            "ser": ser,
                            "execution_id": execution_id,
                        }

                    # Record execution in registry
                    if _registry:
                        try:
                            issuer_did = contract.issuer.agent_id
                            receiver_did = contract.receiver.agent_id if contract.receiver else "unknown"
                            joules_used = ser.get("resource_usage", {}).get("joules_used", 0)

                            _registry.record_execution(
                                execution_id=execution_id,
                                contract_id=contract.contract_id,
                                issuer_did=issuer_did,
                                receiver_did=receiver_did,
                                joules_used=joules_used,
                                status="success",
                                ser_summary={
                                    "joules_used": joules_used,
                                    "reputation_score": ser.get("reputation_score"),
                                    "steps_completed": result.get("steps_completed"),
                                }
                            )

                            # Update receiver reputation based on execution
                            new_reputation = _registry.calculate_reputation_from_history(receiver_did)
                            _registry.update_reputation(receiver_did, new_reputation)

                        except Exception as reg_error:
                            log.warning("registry_update_failed", error=str(reg_error))

                    log.info("execution_complete", execution_id=execution_id)

                except Exception as e:
                    exec_duration_ms = (time.time() - exec_start) * 1000
                    metrics.metrics.timer("execution_duration_ms", exec_duration_ms)
                    metrics.metrics.counter("contracts_executed", labels={"status": "failed"})

                    log.error("execution_failed", execution_id=execution_id, error=str(e))
                    async with self._lock:
                        self._results[execution_id] = {
                            "status": "failed",
                            "error": str(e),
                            "execution_id": execution_id,
                        }

                    # Record failed execution
                    if _registry:
                        try:
                            issuer_did = contract.issuer.agent_id
                            receiver_did = contract.receiver.agent_id if contract.receiver else "unknown"
                            _registry.record_execution(
                                execution_id=execution_id,
                                contract_id=contract.contract_id,
                                issuer_did=issuer_did,
                                receiver_did=receiver_did,
                                joules_used=0,
                                status="failed",
                            )
                        except Exception:
                            pass

            except Exception as e:
                log.error("queue_processor_error", error=str(e))
                await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_execution_queue: Optional[ExecutionQueue] = None
_server_config: Optional[ServerConfig] = None
_key_manager: Optional[KeyManager] = None
_registry: Optional[Any] = None  # AgentRegistry instance
_rate_limiter = None  # MultiRateLimiter instance


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server lifecycle."""
    global _execution_queue, _server_config, _key_manager, _registry, _rate_limiter

    _execution_queue = ExecutionQueue()
    _server_config = ServerConfig()

    # Initialize key manager (with path traversal check)
    key_path = _server_config.key_path or "~/.agenlang/keys.pem"
    safe_key_path = validate_path_safe(key_path)
    _key_manager = KeyManager(key_path=safe_key_path)
    if not _key_manager.key_exists():
        _key_manager.generate()
        log.info("generated_new_keypair", key_path=safe_key_path)

    # Initialize registry
    from .registry import AgentRegistry
    _registry = AgentRegistry()

    # Initialize rate limiters
    _rate_limiter = create_default_limiters()

    # Initialize observability and mark start time
    agent_metrics = get_metrics()
    agent_metrics.mark_start_time()
    obs_logger = get_logger("agenlang.server")
    obs_logger.info("Observability initialized")

    # Pre-create circuit breaker in registry
    cb_registry = get_cb_registry()
    cb_registry.get_or_create(
        "contract_execution",
        CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=30.0,
        ),
    )

    # Register this agent in its own registry
    did = _key_manager.derive_did_key()
    pubkey_pem = _key_manager.get_public_key_pem().decode("utf-8")
    endpoint = f"http://localhost:{_server_config.port}"
    try:
        _registry.register_agent(
            did_key=did,
            pubkey_pem=pubkey_pem,
            endpoint_url=endpoint,
            capabilities=["net:read", "compute:read", "compute:write"],
            name="AgenLang A2A Server",
            description="Default AgenLang A2A server instance",
            joule_rate=1.0,
        )
        log.info("registered_self_in_registry", did=did, endpoint=endpoint)
    except Exception as e:
        log.warning("self_registration_failed", error=str(e))

    # Start background queue processor
    queue_task = asyncio.create_task(_execution_queue.process_queue())

    log.info("a2a_server_started", host=_server_config.host, port=_server_config.port, did=did)

    yield

    # Shutdown
    queue_task.cancel()
    try:
        await queue_task
    except asyncio.CancelledError:
        pass
    log.info("a2a_server_shutdown")


# ---------------------------------------------------------------------------
# FastAPI app creation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AgenLang A2A Server",
    description="Agent-to-Agent protocol server for AgenLang contracts",
    version="0.5.0",
    lifespan=lifespan,
)

# Add middleware (order matters: last added is outermost)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestTracingMiddleware)


# ---------------------------------------------------------------------------
# Health & Discovery Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "agenlang-a2a",
        "version": "0.5.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/.well-known/agent.json")
async def agent_discovery() -> Dict[str, Any]:
    """Agent discovery endpoint per A2A spec."""
    global _key_manager
    if _key_manager is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    did = _key_manager.derive_did_key()
    pubkey_pem = _key_manager.get_public_key_pem().decode("utf-8")

    return {
        "@type": "Agent",
        "@id": did,
        "name": "AgenLang Agent",
        "description": "AgenLang A2A-compatible agent",
        "version": "0.5.0",
        "protocols": ["agenlang/1.0", "a2a/1.0"],
        "publicKey": {
            "type": "ECDSA_P256",
            "pem": pubkey_pem,
        },
        "endpoint": {
            "url": f"http://localhost:{_server_config.port if _server_config else 8000}/a2a",
            "transport": "http",
        },
        "capabilities": ["net:read", "compute:read", "compute:write"],
    }


# ---------------------------------------------------------------------------
# Registry Endpoints
# ---------------------------------------------------------------------------

@app.get("/registry/agents")
async def list_registered_agents(limit: int = 100) -> Dict[str, Any]:
    """List agents in the registry."""
    global _registry
    if _registry is None:
        raise HTTPException(status_code=503, detail="Registry not initialized")

    agents = _registry.list_agents(limit=limit)
    return {
        "agents": [agent.to_dict() for agent in agents],
        "count": len(agents),
    }


@app.get("/registry/agents/{did_key:path}")
async def get_agent_by_did(did_key: str) -> Dict[str, Any]:
    """Get agent details by DID."""
    global _registry
    if _registry is None:
        raise HTTPException(status_code=503, detail="Registry not initialized")

    agent = _registry.get_agent(did_key)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return agent.to_dict()


@app.get("/registry/find")
async def find_agents_by_capability(
    capability: str, min_reputation: float = 0.0
) -> Dict[str, Any]:
    """Find agents by capability."""
    global _registry
    if _registry is None:
        raise HTTPException(status_code=503, detail="Registry not initialized")

    agents = _registry.find_agents_by_capability(capability, min_reputation)
    return {
        "agents": [agent.to_dict() for agent in agents],
        "count": len(agents),
        "capability": capability,
    }


@app.get("/registry/stats")
async def get_registry_stats() -> Dict[str, Any]:
    """Get registry statistics."""
    global _registry
    if _registry is None:
        raise HTTPException(status_code=503, detail="Registry not initialized")

    return _registry.get_stats()


# ---------------------------------------------------------------------------
# Observability Endpoints
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def metrics_endpoint() -> JSONResponse:
    """Return all collected metrics as JSON."""
    agent_metrics = get_metrics()
    return JSONResponse(content=agent_metrics.metrics.get_all_metrics())


@app.get("/traces")
async def traces_endpoint() -> JSONResponse:
    """Return recent traces as JSON."""
    agent_metrics = get_metrics()
    return JSONResponse(content=agent_metrics.tracer.get_recent_traces())


@app.get("/circuit-breakers")
async def circuit_breakers_endpoint() -> JSONResponse:
    """Return status of all circuit breakers."""
    cb_registry = get_cb_registry()
    return JSONResponse(content=cb_registry.all_statuses())


# ---------------------------------------------------------------------------
# A2A JSON-RPC Endpoint
# ---------------------------------------------------------------------------

@app.post("/a2a")
async def a2a_jsonrpc(request: ExecuteRequest) -> ExecuteResponse:
    """A2A JSON-RPC endpoint for contract execution."""
    global _execution_queue, _key_manager

    if _execution_queue is None or _key_manager is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    if request.method != "agenlang/execute":
        return ExecuteResponse(
            jsonrpc="2.0",
            error={"code": -32601, "message": f"Method not found: {request.method}"},
            id=request.id,
        )

    try:
        # Extract contract from params
        contract = a2a_payload_to_contract(request.params)

        # Verify signature if present
        if contract.issuer.proof and not contract.verify_signature():
            return ExecuteResponse(
                jsonrpc="2.0",
                error={"code": -32001, "message": "Invalid contract signature"},
                id=request.id,
            )

        # Verify receiver key if specified
        if not contract.verify_receiver_key(_key_manager):
            return ExecuteResponse(
                jsonrpc="2.0",
                error={"code": -32002, "message": "Contract not intended for this agent"},
                id=request.id,
            )

        # Submit for execution
        execution_id = await _execution_queue.submit(contract, _key_manager)

        # Wait for result
        result = await _execution_queue.get_result(
            execution_id, timeout=_server_config.request_timeout if _server_config else 300.0
        )

        if result is None:
            return ExecuteResponse(
                jsonrpc="2.0",
                error={"code": -32003, "message": "Execution timeout"},
                id=request.id,
            )

        if result["status"] == "failed":
            return ExecuteResponse(
                jsonrpc="2.0",
                error={"code": -32004, "message": result["error"]},
                id=request.id,
            )

        return ExecuteResponse(
            jsonrpc="2.0",
            result={
                "contract_id": contract.contract_id,
                "execution_id": execution_id,
                "output": result["result"]["output"],
                "ser": result["ser"],
            },
            id=request.id,
        )

    except ValueError as e:
        log.error("contract_validation_failed", error=str(e))
        return ExecuteResponse(
            jsonrpc="2.0",
            error={"code": -32700, "message": f"Invalid contract: {str(e)}"},
            id=request.id,
        )
    except Exception as e:
        log.error("execution_error", error=str(e))
        return ExecuteResponse(
            jsonrpc="2.0",
            error={"code": -32603, "message": f"Internal error: {str(e)}"},
            id=request.id,
        )


# ---------------------------------------------------------------------------
# A2A SSE Streaming Endpoint
# ---------------------------------------------------------------------------

@app.post("/a2a/stream")
async def a2a_sse(request: ExecuteRequest) -> EventSourceResponse:
    """A2A SSE streaming endpoint for async contract execution."""
    global _execution_queue, _key_manager

    if _execution_queue is None or _key_manager is None:
        raise HTTPException(status_code=503, detail="Server not initialized")

    if request.method != "agenlang/execute":
        async def error_stream():
            yield {
                "event": "error",
                "data": json.dumps({"code": -32601, "message": f"Method not found: {request.method}"}),
            }
        return EventSourceResponse(error_stream())

    async def event_stream() -> AsyncGenerator[Dict[str, str], None]:
        try:
            # Extract contract
            contract = a2a_payload_to_contract(request.params)

            # Validate
            if contract.issuer.proof and not contract.verify_signature():
                yield {
                    "event": "error",
                    "data": json.dumps({"code": -32001, "message": "Invalid contract signature"}),
                }
                return

            if not contract.verify_receiver_key(_key_manager):
                yield {
                    "event": "error",
                    "data": json.dumps({"code": -32002, "message": "Contract not intended for this agent"}),
                }
                return

            # Submit and yield execution ID
            execution_id = await _execution_queue.submit(contract, _key_manager)
            yield {
                "event": "submitted",
                "data": json.dumps({"execution_id": execution_id, "contract_id": contract.contract_id}),
            }

            # Poll for result
            while True:
                result = await _execution_queue.get_result(execution_id, timeout=1.0)
                if result:
                    if result["status"] == "failed":
                        yield {
                            "event": "error",
                            "data": json.dumps({"code": -32004, "message": result["error"]}),
                        }
                    else:
                        yield {
                            "event": "complete",
                            "data": json.dumps({
                                "contract_id": contract.contract_id,
                                "execution_id": execution_id,
                                "output": result["result"]["output"],
                                "ser": result["ser"],
                            }),
                        }
                    return
                yield {
                    "event": "heartbeat",
                    "data": json.dumps({"execution_id": execution_id, "status": "processing"}),
                }
                await asyncio.sleep(1)

        except Exception as e:
            log.error("sse_error", error=str(e))
            yield {
                "event": "error",
                "data": json.dumps({"code": -32603, "message": str(e)}),
            }

    return EventSourceResponse(event_stream())


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------

def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    key_path: Optional[str] = None,
    ssl_certfile: Optional[str] = None,
    ssl_keyfile: Optional[str] = None,
    ssl_ca_certs: Optional[str] = None,
) -> None:
    """Run the A2A server with uvicorn."""
    import uvicorn

    global _server_config
    _server_config = ServerConfig(
        host=host,
        port=port,
        key_path=key_path,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
        ssl_ca_certs=ssl_ca_certs,
    )

    uvicorn_kwargs: Dict[str, Any] = {
        "host": host,
        "port": port,
    }

    # Pass TLS config to uvicorn when provided
    if ssl_certfile:
        uvicorn_kwargs["ssl_certfile"] = validate_path_safe(ssl_certfile)
    if ssl_keyfile:
        uvicorn_kwargs["ssl_keyfile"] = validate_path_safe(ssl_keyfile)
    if ssl_ca_certs:
        uvicorn_kwargs["ssl_ca_certs"] = validate_path_safe(ssl_ca_certs)

    uvicorn.run(app, **uvicorn_kwargs)
