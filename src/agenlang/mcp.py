"""MCP (Model Context Protocol) adapter.

Registers AgenLang contract execution as an MCP-compatible tool using
JSON-RPC 2.0 format. No mcp SDK dependency required.
"""

import json
from typing import Any, Dict

import structlog

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
