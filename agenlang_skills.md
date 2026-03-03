# How to Register AgenLang as a Skill/Tool

AgenLang contracts can be executed from any agent framework. This guide shows how to register AgenLang as a callable tool in LangChain, CrewAI, OpenClaw, and custom pipelines.

## LangChain

Use the `@tool` decorator to wrap contract execution:

```python
from langchain_core.tools import tool
from agenlang.contract import Contract
from agenlang.runtime import Runtime
from agenlang.keys import KeyManager

@tool
def agenlang_execute(contract_path: str) -> str:
    """Execute an AgenLang contract and return the SER audit trail."""
    contract = Contract.from_file(contract_path)
    km = KeyManager()
    contract.sign(km)
    runtime = Runtime(contract, key_manager=km)
    result, ser = runtime.execute()
    return f"Status: {result['status']}, Joules: {ser['resource_usage']['joules_used']}"

# Use in a LangChain agent
from langchain.agents import AgentExecutor, create_tool_calling_agent
agent = create_tool_calling_agent(llm, [agenlang_execute], prompt)
executor = AgentExecutor(agent=agent, tools=[agenlang_execute])
executor.invoke({"input": "Run the flight booking contract"})
```

## CrewAI

Register as a CrewAI tool by wrapping the execution function:

```python
from crewai.tools import tool
from agenlang.contract import Contract
from agenlang.runtime import Runtime
from agenlang.keys import KeyManager

@tool("AgenLang Contract Runner")
def run_agenlang_contract(contract_json: str) -> str:
    """Execute an AgenLang contract from JSON string."""
    import json
    data = json.loads(contract_json)
    contract = Contract.from_dict(data)
    km = KeyManager()
    contract.sign(km)
    runtime = Runtime(contract, key_manager=km)
    result, ser = runtime.execute()
    return json.dumps({"result": result, "ser": ser}, indent=2)

# Assign to a CrewAI agent
from crewai import Agent
agent = Agent(
    role="Contract Executor",
    goal="Execute AgenLang contracts securely",
    tools=[run_agenlang_contract],
)
```

## OpenClaw / Amazo

Pass contracts via the CLI or the programmatic API:

```bash
# CLI usage
export LLM_PROVIDER=openai
export LLM_API_KEY=your-key
export TAVILY_API_KEY=your-tavily-key
agenlang run examples/amazo-flight-booking.json
```

```python
# Programmatic usage in an OpenClaw pipeline
from agenlang.contract import Contract
from agenlang.runtime import Runtime
from agenlang.keys import KeyManager

contract = Contract.from_file("examples/amazo-flight-booking.json")
km = KeyManager()
contract.sign(km)
assert contract.verify_signature()

runtime = Runtime(contract, key_manager=km)
result, ser = runtime.execute()
print(result["output"])
print(runtime.to_ser_json(ser))
```

## MCP Server (Model Context Protocol)

Start AgenLang as an MCP-compatible tool server:

```bash
python -m agenlang.mcp
# Server runs on 0.0.0.0:8716
# Endpoints: GET /health, GET /tools, GET /info, POST /jsonrpc
```

```python
# Or start programmatically
from agenlang.mcp import start_mcp_server
start_mcp_server(host="127.0.0.1", port=8716)
```

## Custom Tool Registration

Add your own tools to the AgenLang registry:

```python
from agenlang.tools import register_tool

def my_custom_tool(args: dict) -> str:
    """Custom tool that does something useful."""
    query = args.get("query", "")
    return f"Processed: {query}"

register_tool(
    name="my_tool",
    capabilities=["compute:read"],
    func=my_custom_tool,
    description="A custom processing tool",
    joule_cost=50.0,
)
```

Then reference it in a contract workflow step:

```json
{"action": "tool", "target": "my_tool", "args": {"query": "hello"}}
```

## Protocol Adapters

AgenLang integrates with multiple agent protocols. Use protocol prefixes in workflow steps for auto-dispatch:

```json
{"action": "subcontract", "target": "acp:https://remote-agent.example.com/acp"}
{"action": "tool", "target": "mcp:agenlang_execute"}
{"action": "subcontract", "target": "anp:https://peer.example.com/anp"}
```

See [README.md](README.md) for the full protocol compatibility table and adapter examples.
