"""Pytest fixtures - register mock tools and temp key dirs for tests."""

from pathlib import Path

import pytest

from agenlang import tools as tools_mod


@pytest.fixture(autouse=True)
def _tmp_key_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use tmp dir for KeyManager so tests don't touch ~/.agenlang."""
    monkeypatch.setenv("AGENLANG_KEY_DIR", str(tmp_path))


@pytest.fixture(autouse=True)
def _mock_tools() -> None:
    """Replace real tools with mocks so tests run without API keys."""

    def _mock_web_search(args):
        return f"[mock] Search results for: {args.get('query', '')}"

    def _mock_summarize(args):
        text = args.get("text", "")
        return f"[mock] Summary of {text[:80]}..."

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
