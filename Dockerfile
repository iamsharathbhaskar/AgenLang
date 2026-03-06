# AgenLang Server - Production Dockerfile
# Multi-stage build for security and efficiency

# Stage 1: Builder
FROM python:3.12-slim-bookworm AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    cargo \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install dependencies
WORKDIR /build
COPY pyproject.toml .
RUN pip install --upgrade pip wheel setuptools && \
    pip install --no-cache-dir \
    pydantic>=2.0 \
    jsonschema>=4.0 \
    cryptography>=42.0 \
    click>=8.0 \
    requests>=2.0 \
    structlog>=24.0 \
    tavily-python>=0.5 \
    fastapi>=0.110 \
    uvicorn>=0.27 \
    sse-starlette>=2.0 \
    websockets>=12.0 \
    jinja2>=3.1 \
    redis>=5.0 \
    psycopg2-binary>=2.9

# Stage 2: Production
FROM python:3.12-slim-bookworm AS production

# Security: Create non-root user
RUN groupadd --gid 1000 agenlang && \
    useradd --uid 1000 --gid agenlang --shell /bin/false --create-home agenlang

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 \
    libssl3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY src/agenlang ./agenlang
COPY schema ./schema
COPY templates ./templates

# Create data directories
RUN mkdir -p /data/agenlang && \
    chown -R agenlang:agenlang /app /data

# Create entrypoint script
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    chown agenlang:agenlang /entrypoint.sh

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    AGENLANG_DATA_DIR=/data/agenlang \
    AGENLANG_KEY_PATH=/data/agenlang/keys.pem \
    AGENLANG_HOST=0.0.0.0 \
    AGENLANG_PORT=8000 \
    AGENLANG_LOG_LEVEL=INFO \
    AGENLANG_JSON_LOGS=true

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER agenlang

# Use entrypoint for proper signal handling
ENTRYPOINT ["/entrypoint.sh"]
CMD ["server"]

# Labels
LABEL org.opencontainers.image.title="AgenLang Server" \
      org.opencontainers.image.description="A2A server for AgenLang contract execution" \
      org.opencontainers.image.version="0.4.2" \
      org.opencontainers.image.vendor="AgenLang" \
      org.opencontainers.image.source="https://github.com/agenlang/agenlang"
