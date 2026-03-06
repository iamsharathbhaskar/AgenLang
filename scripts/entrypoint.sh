#!/bin/sh
# AgenLang Server Entrypoint Script
# Handles signal forwarding and graceful shutdown

set -e

# Handle signals for graceful shutdown
cleanup() {
    echo "[entrypoint] Received shutdown signal, stopping..."
    kill -TERM "$child" 2>/dev/null || true
    wait "$child"
    exit 0
}

trap cleanup TERM INT

# Set default command
if [ "$#" -eq 0 ]; then
    set -- server
fi

# Validate required directories
if [ ! -d "$AGENLANG_DATA_DIR" ]; then
    echo "[entrypoint] Creating data directory: $AGENLANG_DATA_DIR"
    mkdir -p "$AGENLANG_DATA_DIR"
fi

# Ensure key directory exists
key_dir=$(dirname "$AGENLANG_KEY_PATH")
if [ ! -d "$key_dir" ]; then
    echo "[entrypoint] Creating key directory: $key_dir"
    mkdir -p "$key_dir"
fi

# Generate keys if they don't exist
if [ ! -f "$AGENLANG_KEY_PATH" ]; then
    echo "[entrypoint] No key file found at $AGENLANG_KEY_PATH"
    echo "[entrypoint] Keys will be generated on first server start"
fi

# Export environment for Python
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Run based on command
case "$1" in
    server)
        echo "[entrypoint] Starting AgenLang A2A Server..."
        echo "[entrypoint] Host: ${AGENLANG_HOST:-0.0.0.0}"
        echo "[entrypoint] Port: ${AGENLANG_PORT:-8000}"
        echo "[entrypoint] Data Directory: ${AGENLANG_DATA_DIR}"
        echo "[entrypoint] Key Path: ${AGENLANG_KEY_PATH}"
        
        # Start uvicorn in background for signal handling
        python -m uvicorn agenlang.server:app \
            --host "${AGENLANG_HOST:-0.0.0.0}" \
            --port "${AGENLANG_PORT:-8000}" \
            --workers "${UVICORN_WORKERS:-1}" \
            --log-level "${UVICORN_LOG_LEVEL:-info}" \
            --access-log \
            --proxy-headers &
        
        child=$!
        wait "$child"
        ;;
    
    server-no-uvicorn)
        # Direct server execution (for production mode with custom server implementation)
        echo "[entrypoint] Starting AgenLang server (production mode)..."
        python -c "
from agenlang.server import run_server
run_server(
    host='${AGENLANG_HOST:-0.0.0.0}',
    port=${AGENLANG_PORT:-8000},
    key_path='${AGENLANG_KEY_PATH}'
)
        " &
        
        child=$!
        wait "$child"
        ;;
    
    cli)
        # Run CLI commands
        shift
        exec python -m agenlang.cli "$@"
        ;;
    
    shell|sh|bash)
        # Interactive shell
        exec /bin/sh
        ;;
    
    *)
        # Run whatever command was passed
        exec "$@"
        ;;
esac