"""Pytest fixtures - register mock tools for tests (no API keys needed)."""


import pytest


@pytest.fixture(autouse=True)
def mock_tools(monkeypatch) -> None:
    """Replace real tools with mocks so tests run without API keys."""
    def _mock_web_search(args):
        return f"[mock] Search results for: {args.get('query', '')}"

    def _mock_summarize(args):
        text = args.get("text", "")
        return f"[mock] Summary of {text[:80]}..."

    # Reset to ensure clean state, then register mocks
    from agenlang import tools as tools_mod
    tools_mod.TOOLS["web_search"] = {
        "capabilities": ["net:read"],
        "function": _mock_web_search,
        "description": "Mock web search",
        "joule_cost": 150.0,
    }
    tools_mod.TOOLS["summarize"] = {
        "capabilities": ["compute:read"],
        "function": _mock_summarize,
        "description": "Mock summarize",
        "joule_cost": 80.0,
    }
