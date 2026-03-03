"""AgenLang Tool Registry - verified tools with capability declarations.

Real implementations: Tavily Search API (web_search), Grok API (summarize).
No dummy string returns; requires API keys when invoking.
"""

import os
from typing import Any, Callable, Dict

import structlog

log = structlog.get_logger()


def _web_search_tavily(args: Dict[str, Any]) -> str:
    """Perform web search via Tavily API."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise ValueError(
            "TAVILY_API_KEY required for web_search. " "Get one at https://tavily.com"
        )
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    query = args.get("query", "")
    response = client.search(query=query, max_results=5)
    results = response.get("results", [])
    if not results:
        return "No results found."
    return "\n".join(
        f"- {r.get('title', '')}: {r.get('content', '')[:200]}..." for r in results[:5]
    )


def _summarize_grok(args: Dict[str, Any]) -> str:
    """Summarize text via Grok API (xAI)."""
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        raise ValueError(
            "XAI_API_KEY required for summarize. " "Get one at https://console.x.ai"
        )
    import requests  # type: ignore[import-untyped]

    text = args.get("text", "")
    resp = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "grok-3-mini",
            "messages": [
                {"role": "user", "content": f"Summarize concisely:\n\n{text}"},
            ],
            "max_tokens": 500,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    choice = data.get("choices", [{}])[0]
    return choice.get("message", {}).get("content", "No summary generated.")


# Joule cost per tool (real metering)
WEB_SEARCH_JOULES = 150.0
SUMMARIZE_JOULES = 80.0
SKILL_JOULES = 50.0
SUBCONTRACT_JOULES = 200.0
EMBED_JOULES = 100.0


def _make_pluggable_registry() -> Dict[str, Dict[str, Any]]:
    """Build tool registry with real implementations."""
    return {
        "web_search": {
            "capabilities": ["net:read"],
            "function": _web_search_tavily,
            "description": "Perform a web search via Tavily API.",
            "joule_cost": WEB_SEARCH_JOULES,
        },
        "summarize": {
            "capabilities": ["compute:read"],
            "function": _summarize_grok,
            "description": "Summarize text via Grok API.",
            "joule_cost": SUMMARIZE_JOULES,
        },
    }


TOOLS: Dict[str, Dict[str, Any]] = _make_pluggable_registry()


def register_tool(
    name: str,
    capabilities: list[str],
    func: Callable[[Dict[str, Any]], str],
    description: str = "",
    joule_cost: float = 100.0,
) -> None:
    """Register a tool in the registry.

    Args:
        name: Tool identifier.
        capabilities: Required capability attestations.
        func: Callable(args) -> str.
        description: Human-readable description.
        joule_cost: Joule cost per invocation.
    """
    TOOLS[name] = {
        "capabilities": capabilities,
        "function": func,
        "description": description or name,
        "joule_cost": joule_cost,
    }
