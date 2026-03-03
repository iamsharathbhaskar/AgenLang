# How to Register AgenLang as a Skill/Tool

AgenLang contracts can be executed from any agent framework.
The core API is: load a contract JSON, run `Runtime.execute()`, get back a result and a Structured Execution Record (SER).

## LangChain

```python
from langchain.tools import tool
from agenlang.contract import Contract
from agenlang.runtime import Runtime
from agenlang.keys import KeyManager

@tool
def run_agenlang_contract(contract_path: str) -> str:
    """Execute an AgenLang contract and return the SER."""
    km = KeyManager()
    km.generate()
    contract = Contract.from_file(contract_path)
    result, ser = Runtime(contract, key_manager=km).execute()
    return f"Status: {result['status']}, Joules: {ser['resource_usage']['joules_used']}"
```

## CrewAI

```python
from crewai.tools import tool
from agenlang.contract import Contract
from agenlang.runtime import Runtime
from agenlang.keys import KeyManager

@tool("AgenLang Executor")
def agenlang_execute(contract_json: str) -> str:
    """Run an AgenLang contract from JSON string."""
    import json
    km = KeyManager()
    km.generate()
    data = json.loads(contract_json)
    contract = Contract.from_dict(data)
    result, ser = Runtime(contract, key_manager=km).execute()
    return json.dumps({"result": result, "ser": ser}, indent=2)
```

## OpenClaw / Amazo

### CLI

```bash
export TAVILY_API_KEY="your-tavily-key"
export LLM_PROVIDER="openai"          # or anthropic, xai, generic
export LLM_API_KEY="your-api-key"
agenlang run examples/amazo-flight-booking.json
```

### Programmatic

```python
from agenlang.contract import Contract
from agenlang.runtime import Runtime
from agenlang.keys import KeyManager

km = KeyManager()
km.generate()
contract = Contract.from_file("examples/amazo-flight-booking.json")
result, ser = Runtime(contract, key_manager=km).execute()
print(result["status"])
print(ser["resource_usage"]["joules_used"])
```

## Custom Tool Registration

Register new tools for use in contract workflows:

```python
from agenlang.tools import register_tool

def my_custom_tool(args: dict) -> str:
    return f"Processed: {args.get('input', '')}"

register_tool(
    name="my_tool",
    capabilities=["compute:read"],
    function=my_custom_tool,
    joule_cost=50.0,
)
```

Then reference `my_tool` in any contract workflow step:

```json
{
  "action": "tool",
  "target": "my_tool",
  "args": {"input": "hello"}
}
```
