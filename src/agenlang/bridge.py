"""Bridge module - MCP Client adapter for consuming external MCP servers."""

import asyncio
import uuid
from typing import Any, Optional

from agenlang.economy import JouleMeter, SignedExecutionRecord, compute_hash
from agenlang.identity import Identity
from agenlang.schema import Performative


class MCPBridge:
    """MCP Client adapter to wrap external MCP servers as AgenLang agents.

    Note: AgenLang only consumes MCP servers, never exposes itself as an MCP server.
    """

    def __init__(
        self,
        mcp_server_url: str,
        identity: Optional[Identity] = None,
    ):
        self.mcp_server_url = mcp_server_url
        self.identity = identity
        self._client: Optional[Any] = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to MCP server."""
        try:
            self._client = MCPClient(self.mcp_server_url)
            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from MCP server."""
        self._client = None
        self._connected = False

    async def is_connected(self) -> bool:
        """Check if connected to MCP server."""
        return self._connected

    async def list_tools(self) -> list[dict]:
        """List available tools from MCP server."""
        if not self._connected or not self._client:
            return []

        try:
            return await self._client.list_tools()
        except Exception:
            return []

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call a tool on the MCP server."""
        if not self._connected or not self._client:
            raise RuntimeError("Not connected to MCP server")

        return await self._client.call_tool(tool_name, arguments)

    async def as_agent(self, agent_did: str) -> "WrappedMCPAgent":
        """Wrap MCP server as a stateless AgenLang agent."""
        return WrappedMCPAgent(
            bridge=self,
            agent_did=agent_did,
            identity=self.identity,
        )


class MCPClient:
    """Mock MCP client for testing. In production, use the official mcp package."""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self._tools: dict[str, dict] = {}

    async def list_tools(self) -> list[dict]:
        """List available tools."""
        return list(self._tools.values())

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call a tool."""
        if tool_name not in self._tools:
            raise ValueError(f"Tool {tool_name} not found")

        tool = self._tools[tool_name]
        return {"result": f"Executed {tool_name} with {arguments}"}

    def add_tool(self, name: str, description: str, input_schema: dict) -> None:
        """Add a tool to the client."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }


class WrappedMCPAgent:
    """Stateless AgenLang agent wrapping an MCP server.

    This agent translates between AgenLang messages and MCP tool calls,
    meters Joules, and produces Signed Execution Records.
    """

    def __init__(
        self,
        bridge: MCPBridge,
        agent_did: str,
        identity: Optional[Identity] = None,
    ):
        self.bridge = bridge
        self.agent_did = agent_did
        self.identity = identity
        self._capabilities: list[dict] = []
        self._tools_map: dict[str, str] = {}

    async def initialize(self) -> None:
        """Initialize and discover capabilities from MCP server."""
        tools = await self.bridge.list_tools()

        self._capabilities = []
        self._tools_map = {}

        for tool in tools:
            task_name = tool.get("name", "")
            self._capabilities.append(
                {
                    "task": task_name,
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("inputSchema", {}),
                    "output_schema": {"type": "object"},
                }
            )
            self._tools_map[task_name] = task_name

    def get_capabilities(self) -> list[dict]:
        """Get agent capabilities."""
        return self._capabilities

    async def handle_request(self, request: dict) -> dict:
        """Handle AgenLang REQUEST as MCP tool call with Joule metering."""
        content = request.get("content", {})
        payload = content.get("payload", {})

        task = payload.get("task")
        arguments = payload.get("arguments", {})

        if not task:
            return {
                "error": "No task specified",
                "error_code": "ERR_CAPABILITY_MISMATCH",
            }

        if task not in self._tools_map:
            return {
                "error": f"Task {task} not supported",
                "error_code": "ERR_CAPABILITY_MISMATCH",
            }

        meter = JouleMeter()

        with meter.measure():
            prompt_text = f"Task: {task}, Args: {arguments}"
            meter.count_prompt_tokens(prompt_text)

            try:
                result = await self.bridge.call_tool(task, arguments)
                result_text = str(result)
            except Exception as e:
                return {
                    "error": str(e),
                    "error_code": "ERR_TASK_FAILED",
                }

            meter.count_completion_tokens(result_text)

        joules = meter.calculate_joules()
        breakdown = meter.get_breakdown()

        return {
            "task": task,
            "result": result,
            "joules": joules,
            "breakdown": breakdown,
        }

    async def meter_joules(
        self,
        task: str,
        arguments: dict,
    ) -> tuple[Any, float, dict]:
        """Meter Joules for tool execution. Returns (result, joules, breakdown)."""
        meter = JouleMeter()

        with meter.measure():
            prompt_text = f"Task: {task}, Args: {arguments}"
            meter.count_prompt_tokens(prompt_text)

            result = await self.bridge.call_tool(task, arguments)
            result_text = str(result)

            meter.count_completion_tokens(result_text)

        joules = meter.calculate_joules()
        breakdown = meter.get_breakdown()

        return result, joules, breakdown

    async def produce_ser(
        self,
        contract_id: str,
        consumer_did: str,
        task: str,
        arguments: dict,
        result: Any,
        joules: float,
        breakdown: dict,
    ) -> SignedExecutionRecord:
        """Produce Signed Execution Record for completed execution."""
        if not self.identity:
            raise RuntimeError("Identity not set for signing SER")

        prompt_text = f"Task: {task}, Args: {arguments}"
        completion_text = str(result)

        pricing = {
            "base_joules": 0.0,
            "per_1k_tokens": 0.0,
            "weights": breakdown.get("weights", {}),
        }

        ser = SignedExecutionRecord.create(
            contract_id=contract_id,
            provider_did=self.agent_did,
            consumer_did=consumer_did,
            joules=joules,
            pricing=pricing,
            breakdown=breakdown,
            prompt_text=prompt_text,
            completion_text=completion_text,
        )

        ser.signature = self._sign_ser(ser)

        return ser

    def _sign_ser(self, ser: SignedExecutionRecord) -> str:
        """Sign the SER with the agent's identity."""
        if not self.identity:
            return ""

        ser_dict = ser.model_dump(exclude={"signature"})
        canonical_bytes = f"ser:{ser.ser_id}:{ser.joules}".encode("utf-8")

        from cryptography.hazmat.primitives import hashes
        import base64

        digest = hashes.Hash(hashes.SHA256())
        digest.update(canonical_bytes)
        message_hash = digest.finalize()

        signature = self.identity.private_key.sign(message_hash)
        return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


class MCPToolAdapter:
    """Adapter to expose MCP tools as AgenLang capabilities."""

    def __init__(self, wrapped_agent: WrappedMCPAgent):
        self.wrapped_agent = wrapped_agent

    def to_agent_card_capabilities(self) -> list[dict]:
        """Convert MCP tools to Agent Card capabilities format."""
        return [
            {
                "task": cap["task"],
                "input_schema": cap.get("input_schema", {}),
                "output_schema": cap.get("output_schema", {"type": "object"}),
            }
            for cap in self.wrapped_agent.get_capabilities()
        ]
