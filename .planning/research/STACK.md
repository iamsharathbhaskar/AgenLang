# Technology Stack

**Project:** AgenLang Core Protocol
**Researched:** 2026-03-11
**Confidence:** HIGH

This document specifies the recommended technology stack for building a Python library for Agent-to-Agent (A2A) communication with DID identity, async transport, and cryptographic message signing.

---

## Recommended Stack

### Core Cryptography & Identity

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `cryptography` | >=44.0.0 | Ed25519 key generation, signing, verification | Industry-standard library (used by AWS, PyCA). Provides `cryptography.hazmat.primitives.asymmetric.ed25519` for secure key operations. Better ecosystem support than pynacl. |
| `rfc8785` | >=0.1.4 | RFC 8785 JSON Canonicalization Scheme | Pure-Python, no-dependency implementation by Trailofbits. Ensures deterministic serialization for cross-language signature verification. Use `rfc8785.canonicalize()` or `rfc8785.dumps()`. |

**Why not other options:**
- **pynacl**: While valid, `cryptography` has broader ecosystem support and is more mature
- **jsoncanon**: Less maintained, fewer features than rfc8785
- **cyberphone/json-canonicalization**: Reference implementation, but rfc8785 package is more Pythonic

---

### Schema & Validation

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `pydantic` | >=2.12.0 | Data validation using Python type hints | The standard for Python data validation. v2 is a ground-up rewrite with 6-10x performance improvements over v1. Use v2 for all new code. |
| `pydantic-settings` | >=2.7.0 | Settings management | Official Pydantic settings plugin. Use for configuration via env vars/config files. |
| `pyyaml` | >=6.0.2 | YAML parsing and serialization | Use `yaml.safe_load()` for parsing incoming messages. Never use `yaml.load()` (unsafe). |

**Why not other options:**
- **msgspec**: Faster than Pydantic, but smaller ecosystem. Stick with Pydantic for broader compatibility.
- **dataclass + manually**: Too error-prone for security-critical message validation.

---

### Async Transport

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `httpx` | >=0.28.0 | Async HTTP client/server | Modern async HTTP library. Supports both sync and async APIs, HTTP/2, connection pooling. Works natively with FastAPI. |
| `fastapi` | >=0.134.0 | Web framework for HTTP server | Built on Starlette + Pydantic. Highest performance Python web framework (comparable to NodeJS/Go). Native async support. Python >=3.10 required. |
| `websockets` | >=16.0 | Async WebSocket client/server | The standard async WebSocket library for Python. Built on asyncio. Supports both client and server modes. |

**Why not other options:**
- **aiohttp**: Valid alternative, but httpx provides unified sync/async API and better FastAPI integration
- **requests**: Synchronous only, cannot use in async context
- **Flask/Django**: Blocking I/O, not suitable for async agent message loops

---

### Persistence

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `aiosqlite` | >=0.22.0 | Async SQLite operations | Provides async/await interface to SQLite. Essential for non-blocking database operations in async message loops. |

**Why not other options:**
- **SQLAlchemy + asyncpg**: Overkill for single-file SQLite use case
- **tinyDB**: Not suitable for complex queries needed for contract/Joule tracking
- **blocking sqlite3**: Would block the async event loop

---

### Token Counting & Economy

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `tiktoken` | >=0.4.0 | BPE tokenization for LLM cost estimation | OpenAI's official tokenization library. 3-6x faster than comparable tokenizers. Use `tiktoken.get_encoding("cl100k_base")` for GPT-4/GPT-3.5 models. |

**Why not other options:**
- **transformers Tokenizer**: Heavy dependency, slower
- **character-based estimation**: Inaccurate for multi-lingual/code content

---

### Security & Key Storage

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `keyring` | >=25.0.0 | OS keyring integration | Cross-platform secure credential storage (macOS Keychain, Windows Credential Locker, Linux Secret Service). Use with passphrase fallback for agent keys. |

**Why not other options:**
- **raw file storage**: Insecure without additional encryption
- **hashicorp-vault**: Overkill for single-agent deployments

---

### Logging & Observability

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `structlog` | >=25.0.0 | Structured logging | Production-ready structured logging. Supports JSON output, logfmt, pretty console. Native asyncio support. Integrates with standard logging module. |

**Why not other options:**
- **standard logging**: Less structured, harder to parse in log aggregation systems
- **loguru**: Good alternative, but structlog has better observability integrations

---

### Protocol Integration

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `mcp` | >=1.26.0 | Model Context Protocol SDK | Anthropic's official MCP Python SDK. Use for building MCP client adapters in `agenlang.bridge` module. |

**Why not other options:**
- **manual MCP implementation**: Complex protocol, use official SDK
- **mcp-agent**: Higher-level framework, not needed for client-only use

---

### Local Discovery

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `zeroconf` | >=0.147.0 | mDNS/DNS-SD service discovery | Python-zeroconf provides mDNS for local network agent discovery. Publish `_agenlang._tcp.local` services. |

**Why not other options:**
- **pyzeroconf**: Outdated, python-zeroconf is the maintained fork
- **aiozeroconf**: Async version exists but zeroconf works fine in async context

---

## Optional Extras

### Broker Transport (install with `agenlang[brokers]`)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `nats-py` | >=0.24.0 | NATS broker client | High-reliability corporate LANs, pub/sub patterns |
| `redis` | >=5.2.0 | Redis client (async) | Message queuing, pub/sub, caching |

### Observability (install with `agenlang[observability]`)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `opentelemetry-api` | >=1.26.0 | OpenTelemetry interfaces | Distributed tracing hooks |
| `opentelemetry-sdk` | >=1.26.0 | OpenTelemetry implementation | W3C Trace-Context propagation |
| `opentelemetry-exporter-otlp` | >=1.26.0 | OTLP export | Send traces to Jaeger/Zipkin |

---

## Installation

### Core Dependencies

```bash
pip install \
    cryptography>=44.0.0 \
    rfc8785>=0.1.4 \
    pydantic>=2.12.0 \
    pydantic-settings>=2.7.0 \
    pyyaml>=6.0.2 \
    httpx>=0.28.0 \
    fastapi>=0.134.0 \
    websockets>=16.0 \
    aiosqlite>=0.22.0 \
    tiktoken>=0.4.0 \
    keyring>=25.0.0 \
    structlog>=25.0.0 \
    mcp>=1.26.0 \
    zeroconf>=0.147.0
```

### Development Dependencies

```bash
pip install -D \
    pytest>=8.0.0 \
    pytest-asyncio>=0.25.0 \
    ruff>=0.9.0 \
    mypy>=1.14.0
```

### Optional Extras

```bash
# For broker transport support
pip install agenlang[brokers]
# Or explicitly:
pip install nats-py>=0.24.0 redis>=5.2.0

# For observability
pip install agenlang[observability]
# Or explicitly:
pip install opentelemetry-api>=1.26.0 opentelemetry-sdk>=1.26.0
```

---

## pyproject.toml Structure

```toml
[project]
name = "agenlang"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "cryptography>=44.0.0",
    "rfc8785>=0.1.4",
    "pydantic>=2.12.0",
    "pydantic-settings>=2.7.0",
    "pyyaml>=6.0.2",
    "httpx>=0.28.0",
    "fastapi>=0.134.0",
    "websockets>=16.0",
    "aiosqlite>=0.22.0",
    "tiktoken>=0.4.0",
    "keyring>=25.0.0",
    "structlog>=25.0.0",
    "mcp>=1.26.0",
    "zeroconf>=0.147.0",
]

[project.optional-dependencies]
brokers = [
    "nats-py>=0.24.0",
    "redis>=5.2.0",
]
observability = [
    "opentelemetry-api>=1.26.0",
    "opentelemetry-sdk>=1.26.0",
]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.25.0",
    "ruff>=0.9.0",
    "mypy>=1.14.0",
]
```

---

## Version Constraints Rationale

| Library | Minimum | Rationale |
|---------|---------|-----------|
| Python | 3.10 | FastAPI requires >=3.10. Enables modern syntax throughout. |
| cryptography | 44.0.0 | Recent stable with full Ed25519 support |
| pydantic | 2.12.0 | v2 is required. v2.12+ has Python 3.14 support |
| fastapi | 0.134.0 | Current stable, requires Python >=3.10 |
| httpx | 0.28.0 | HTTP/2 support, unified sync/async API |
| websockets | 16.0 | Current stable, asyncio-native |
| aiosqlite | 0.22.0 | Recent async improvements |
| structlog | 25.0.0 | Modern async/contextvar support |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| HTTP Client | httpx | aiohttp | httpx provides unified sync/async API, better FastAPI integration |
| Crypto | cryptography | pynacl | cryptography has broader ecosystem, more maintained |
| JSON Canonicalization | rfc8785 | jsoncanon | rfc8785 is more complete, better maintained |
| Web Framework | FastAPI | Starlette (raw) | FastAPI adds validation, docs, dependency injection |
| Tokenizer | tiktoken | transformers | tiktoken is 3-6x faster, lighter weight |
| Logging | structlog | loguru | structlog has better observability integrations |
| mDNS | python-zeroconf | pyzeroconf | python-zeroconf is the maintained fork |

---

## Sources

- **cryptography**: https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519.html
- **rfc8785 (PyPI)**: https://pypi.org/project/rfc8785/
- **pydantic**: https://pypi.org/project/pydantic/
- **httpx**: https://www.python-httpx.org/
- **fastapi**: https://fastapi.tiangolo.com/
- **websockets**: https://websockets.readthedocs.io/
- **aiosqlite**: https://aiosqlite.omnilib.dev/
- **tiktoken**: https://github.com/openai/tiktoken
- **keyring**: https://pypi.org/project/keyring/
- **structlog**: https://structlog.org/
- **MCP SDK**: https://pypi.org/project/mcp/
- **python-zeroconf**: https://pypi.org/project/zeroconf/
