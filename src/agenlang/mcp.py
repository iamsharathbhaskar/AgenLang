"""MCP (Model Context Protocol) adapter.

Registers AgenLang contract execution as an MCP-compatible tool using
JSON-RPC 2.0 format. No mcp SDK dependency required.

Run as standalone server: python -m agenlang.mcp
"""

import json
import os
from typing import Any, Dict

import structlog

from .utils import retry_with_backoff

log = structlog.get_logger()


def agenlang_tool_definition() -> Dict[str, Any]:
    """Return MCP-compatible JSON tool definition for agenlang_execute.

    This follows the MCP tool schema spec: name, description, and
    inputSchema using JSON Schema format.
    """
    return {
        "name": "agenlang_execute",
        "description": (
            "Execute an AgenLang contract. Accepts a full contract JSON "
            "and runs it through the AgenLang runtime with cryptographic "
            "signing, Joule metering, and SER audit trail."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "contract": {
                    "type": "object",
                    "description": "Full AgenLang v1.0 contract JSON",
                },
                "sign": {
                    "type": "boolean",
                    "description": "Whether to sign the contract before execution",
                    "default": True,
                },
            },
            "required": ["contract"],
        },
    }


@retry_with_backoff(max_retries=2, base_delay=0.5, timeout=30.0)
def handle_mcp_call(params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle an MCP tool call for agenlang_execute.

    Loads the contract from params, optionally signs it, executes via
    Runtime, and returns the result + SER.

    Args:
        params: MCP call params with 'contract' key.

    Returns:
        Dict with 'result' and 'ser' keys.
    """
    from .contract import Contract
    from .keys import KeyManager
    from .runtime import Runtime

    contract_data = params.get("contract", params)
    contract = Contract.model_validate(contract_data)

    km = KeyManager()
    if params.get("sign", True):
        contract.sign(km)

    runtime = Runtime(contract, key_manager=km)
    result, ser = runtime.execute()

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"result": result, "ser": ser}, indent=2),
            }
        ],
        "isError": False,
    }


def mcp_server_info() -> Dict[str, Any]:
    """Return MCP server metadata for AgenLang."""
    from . import __version__

    return {
        "name": "agenlang",
        "version": __version__,
        "description": (
            "AgenLang contract execution server — secure, auditable, "
            "economically fair inter-agent communication"
        ),
        "tools": [agenlang_tool_definition()],
        "capabilities": {
            "tools": {"listChanged": False},
        },
    }


def create_jsonrpc_response(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap result in JSON-RPC 2.0 response envelope."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def handle_jsonrpc_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Process an MCP JSON-RPC 2.0 request.

    Supports methods: tools/list, tools/call, initialize.

    Args:
        request: JSON-RPC 2.0 request dict.

    Returns:
        JSON-RPC 2.0 response dict.
    """
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    result: Dict[str, Any]
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "serverInfo": mcp_server_info(),
            "capabilities": {"tools": {"listChanged": False}},
        }
    elif method == "tools/list":
        result = {"tools": [agenlang_tool_definition()]}
    elif method == "tools/call":
        tool_name = params.get("name", "")
        if tool_name == "agenlang_execute":
            arguments = params.get("arguments", {})
            result = handle_mcp_call(arguments)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}",
                },
            }
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
        }

    return create_jsonrpc_response(req_id, result)


def create_mcp_app() -> Any:
    """Create a FastAPI app exposing MCP JSON-RPC, health, info, and tools endpoints.

    Returns a FastAPI application. Falls back gracefully if FastAPI is not installed.
    """
    try:
        from contextlib import asynccontextmanager

        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
    except ImportError:
        raise ImportError(
            "FastAPI required for MCP HTTP server. "
            "Install with: pip install fastapi uvicorn"
        )

    @asynccontextmanager
    async def lifespan(app: Any) -> Any:
        log.info("mcp_server_starting")
        yield
        log.info("mcp_server_shutdown")

    app = FastAPI(title="AgenLang MCP Server", version="1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/info")
    async def info() -> Dict[str, Any]:
        return mcp_server_info()

    @app.get("/tools")
    async def tools() -> Dict[str, Any]:
        return {"tools": [agenlang_tool_definition()]}

    @app.post("/jsonrpc")
    async def jsonrpc(request: Request) -> JSONResponse:
        body = await request.json()
        response = handle_jsonrpc_request(body)
        return JSONResponse(content=response)

    return app


def start_mcp_server(host: str | None = None, port: int | None = None) -> None:
    """Start the MCP HTTP server via uvicorn.

    Host and port can be set via MCP_HOST / MCP_PORT env vars,
    function arguments, or defaults (0.0.0.0:8716).
    """
    try:
        import uvicorn  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "uvicorn required for MCP HTTP server. " "Install with: pip install uvicorn"
        )

    resolved_host = host or os.environ.get("MCP_HOST", "0.0.0.0")
    resolved_port = port or int(os.environ.get("MCP_PORT", "8716"))
    app = create_mcp_app()
    log.info(
        "mcp_server_starting",
        host=resolved_host,
        port=resolved_port,
    )
    uvicorn.run(app, host=resolved_host, port=resolved_port)


def dispatch(
    contract: Any,
    action: str,
    target: str,
    args: Dict[str, Any],
) -> str:
    """Runtime dispatch hook: execute via MCP tool call.

    Args:
        contract: The executing contract.
        action: Step action type.
        target: Tool name (part after 'mcp:').
        args: Step arguments.

    Returns:
        JSON string of MCP response.
    """
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": target,
            "arguments": args,
        },
    }
    result = handle_jsonrpc_request(request)
    return json.dumps(result)


if __name__ == "__main__":
    start_mcp_server()
