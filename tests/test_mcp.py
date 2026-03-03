"""Tests for MCP (Model Context Protocol) adapter."""

import json
from pathlib import Path

from agenlang.contract import Contract
from agenlang.mcp import (
    agenlang_tool_definition,
    create_jsonrpc_response,
    dispatch,
    handle_jsonrpc_request,
    handle_mcp_call,
    mcp_server_info,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def test_tool_definition_schema() -> None:
    """Tool definition has name, description, inputSchema."""
    defn = agenlang_tool_definition()
    assert defn["name"] == "agenlang_execute"
    assert "inputSchema" in defn
    assert defn["inputSchema"]["type"] == "object"
    assert "contract" in defn["inputSchema"]["properties"]


def test_mcp_server_info() -> None:
    """Server info has name, version, tools."""
    info = mcp_server_info()
    assert info["name"] == "agenlang"
    assert "version" in info
    assert len(info["tools"]) == 1
    assert info["tools"][0]["name"] == "agenlang_execute"


def test_handle_mcp_call() -> None:
    """handle_mcp_call executes contract and returns result."""
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    params = {"contract": contract.model_dump(), "sign": True}
    result = handle_mcp_call(params)
    assert result["isError"] is False
    assert len(result["content"]) == 1
    parsed = json.loads(result["content"][0]["text"])
    assert parsed["result"]["status"] == "success"


def test_jsonrpc_initialize() -> None:
    """initialize method returns server info."""
    resp = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp["id"] == 1
    assert "serverInfo" in resp["result"]


def test_jsonrpc_tools_list() -> None:
    """tools/list returns tool definitions."""
    resp = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(resp["result"]["tools"]) == 1


def test_jsonrpc_unknown_method() -> None:
    """Unknown method returns error."""
    resp = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 3, "method": "foo/bar"})
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_jsonrpc_unknown_tool() -> None:
    """Unknown tool name returns error."""
    resp = handle_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "nonexistent", "arguments": {}},
        }
    )
    assert "error" in resp


def test_dispatch_via_mcp() -> None:
    """dispatch calls handle_jsonrpc_request."""
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    result = dispatch(
        contract,
        "tool",
        "agenlang_execute",
        {"contract": contract.model_dump()},
    )
    parsed = json.loads(result)
    assert "result" in parsed


def test_create_jsonrpc_response() -> None:
    """JSON-RPC response has correct structure."""
    resp = create_jsonrpc_response(42, {"ok": True})
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 42
    assert resp["result"]["ok"] is True


def test_start_mcp_server_calls_uvicorn() -> None:
    """start_mcp_server creates app and calls uvicorn.run."""
    from unittest.mock import MagicMock, patch

    mock_uvicorn = MagicMock()
    with patch.dict("sys.modules", {"uvicorn": mock_uvicorn}):
        from agenlang.mcp import start_mcp_server

        start_mcp_server(host="127.0.0.1", port=9999)
    mock_uvicorn.run.assert_called_once()
    call_kwargs = mock_uvicorn.run.call_args
    assert call_kwargs.kwargs["host"] == "127.0.0.1"
    assert call_kwargs.kwargs["port"] == 9999


def test_mcp_fastapi_app_routes() -> None:
    """FastAPI MCP app exposes /health, /tools, /jsonrpc routes."""
    from agenlang.mcp import create_mcp_app

    try:
        from httpx import ASGITransport, AsyncClient
    except ImportError:
        import pytest

        pytest.skip("httpx not available")
        return

    import asyncio

    app = create_mcp_app()

    async def _test() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            tools = await client.get("/tools")
            assert tools.status_code == 200
            assert len(tools.json()["tools"]) == 1

            rpc = await client.post(
                "/jsonrpc",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                },
            )
            assert rpc.status_code == 200
            assert "result" in rpc.json()

    asyncio.run(_test())


def test_mcp_info_route() -> None:
    """FastAPI MCP app exposes GET /info with server metadata."""
    from agenlang.mcp import create_mcp_app

    try:
        from httpx import ASGITransport, AsyncClient
    except ImportError:
        import pytest

        pytest.skip("httpx not available")
        return

    import asyncio

    app = create_mcp_app()

    async def _test() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/info")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "agenlang"
            assert "version" in data
            assert len(data["tools"]) >= 1

    asyncio.run(_test())
