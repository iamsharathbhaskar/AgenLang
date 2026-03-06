"""AgenLang — standardized contract substrate for secure inter-agent communication."""

__version__ = "0.5.0"

# Core modules - PRESERVED from original
from .contract import Contract
from .keys import KeyManager
from .runtime import Runtime
from .memory import Memory, EncryptedMemoryBackend, SQLiteMemoryBackend, RedisMemoryBackend
from .settlement import SignedLedger, LedgerEntry
from .tools import TOOLS, register_tool
from .utils import (
    EmbeddingConfig, EmbeddingClient, LLMConfig,
    sha256_hash, current_timestamp, canonical_json,
)
from .a2a import a2a_payload_to_contract, contract_to_a2a_payload

# Server - NEW
from .server import (
    run_server,
    ExecuteRequest,
    ExecuteResponse,
    ServerConfig,
)

# Registry and discovery - NEW
from .registry import AgentRegistry

# Observability and monitoring - NEW
from .observability import (
    AgentMetrics, MetricsCollector, Tracer, TraceSpan,
    StructuredLogger, JsonFormatter, get_metrics, get_logger,
    MetricType, Metric,
)

# Rate limiting - NEW
from .rate_limiter import (
    MultiRateLimiter, RateLimiter, RateLimitConfig,
    RateLimitStrategy, RateLimitExceeded, RateLimiterFactory,
    TokenBucketRateLimiter, SlidingWindowRateLimiter, FixedWindowRateLimiter,
    create_default_limiters,
)

# Circuit breakers and resilience - NEW
from .circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerRegistry,
    CircuitState, CircuitBreakerOpenError, CircuitBreakerExecutionError,
    RetryPolicy, TimeoutPolicy,
    circuit_breaker, with_retry, with_timeout,
    get_registry as get_circuit_breaker_registry,
)

# Middleware - NEW
from .middleware import (
    InputValidationMiddleware,
    SecurityHeadersMiddleware,
    CORSConfig,
)

# Production server - NEW
from .server_production import (
    ProductionServer,
    ProductionConfig,
    create_production_app,
)

__all__ = [
    # Version
    "__version__",
    # Core - PRESERVED
    "Contract", "Runtime", "KeyManager", "Memory",
    "EncryptedMemoryBackend", "SQLiteMemoryBackend", "RedisMemoryBackend",
    "SignedLedger", "LedgerEntry",
    "TOOLS", "register_tool",
    "EmbeddingConfig", "EmbeddingClient", "LLMConfig",
    "a2a_payload_to_contract", "contract_to_a2a_payload",
    # Server - NEW
    "run_server", "ExecuteRequest", "ExecuteResponse", "ServerConfig",
    # Registry - NEW
    "AgentRegistry",
    # Observability - NEW
    "AgentMetrics", "MetricsCollector", "Tracer", "TraceSpan",
    "StructuredLogger", "JsonFormatter", "get_metrics", "get_logger",
    "MetricType", "Metric",
    # Rate limiting - NEW
    "MultiRateLimiter", "RateLimiter", "RateLimitConfig",
    "RateLimitStrategy", "RateLimitExceeded", "RateLimiterFactory",
    "TokenBucketRateLimiter", "SlidingWindowRateLimiter", "FixedWindowRateLimiter",
    "create_default_limiters",
    # Circuit breakers - NEW
    "CircuitBreaker", "CircuitBreakerConfig", "CircuitBreakerRegistry",
    "CircuitState", "CircuitBreakerOpenError", "CircuitBreakerExecutionError",
    "RetryPolicy", "TimeoutPolicy",
    "circuit_breaker", "with_retry", "with_timeout",
    "get_circuit_breaker_registry",
    # Middleware - NEW
    "InputValidationMiddleware", "SecurityHeadersMiddleware", "CORSConfig",
    # Production server - NEW
    "ProductionServer", "ProductionConfig", "create_production_app",
]
