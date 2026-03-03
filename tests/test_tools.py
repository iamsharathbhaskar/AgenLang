"""Tests for tools (mock API calls)."""

import os

import pytest

from agenlang.tools import TOOLS, _summarize_llm, _web_search_tavily, register_tool


def test_web_search_requires_api_key() -> None:
    """web_search raises when TAVILY_API_KEY missing."""
    had = os.environ.pop("TAVILY_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="TAVILY_API_KEY"):
            _web_search_tavily({"query": "test"})
    finally:
        if had:
            os.environ["TAVILY_API_KEY"] = had


def test_summarize_requires_api_key() -> None:
    """summarize raises when no LLM API key available."""
    saved = {}
    for key in ("LLM_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        saved[key] = os.environ.pop(key, None)
    try:
        with pytest.raises(ValueError, match="LLM_API_KEY"):
            _summarize_llm({"text": "test"})
    finally:
        for key, val in saved.items():
            if val:
                os.environ[key] = val


def test_register_tool() -> None:
    """register_tool adds custom tool."""

    def _custom(args):
        return str(args.get("x", 0))

    register_tool("custom", ["compute:read"], _custom, "Custom", joule_cost=50.0)
    assert "custom" in TOOLS
    assert TOOLS["custom"]["joule_cost"] == 50.0
    assert TOOLS["custom"]["function"]({"x": 42}) == "42"


def test_summarize_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """summarize with openai provider uses chat completions."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Summarized text"}}]
    }

    mock_requests = MagicMock()
    mock_requests.post.return_value = mock_resp
    with patch.dict("sys.modules", {"requests": mock_requests}):
        result = _summarize_llm({"text": "Some long text to summarize"})
    assert result == "Summarized text"


def test_summarize_anthropic_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """summarize with anthropic provider uses messages API."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"content": [{"text": "Anthropic summary"}]}

    mock_requests = MagicMock()
    mock_requests.post.return_value = mock_resp
    with patch.dict("sys.modules", {"requests": mock_requests}):
        result = _summarize_llm({"text": "Some text"})
    assert result == "Anthropic summary"


def test_summarize_anthropic_empty_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """summarize handles empty Anthropic content gracefully."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"content": []}

    mock_requests = MagicMock()
    mock_requests.post.return_value = mock_resp
    with patch.dict("sys.modules", {"requests": mock_requests}):
        result = _summarize_llm({"text": "text"})
    assert result == "No summary generated."


def test_web_search_tavily_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """web_search returns results from Tavily API."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.search.return_value = {
        "results": [
            {"title": "Result 1", "content": "Content about flights"},
            {"title": "Result 2", "content": "More flight info"},
        ]
    }

    mock_tavily = MagicMock()
    mock_tavily.TavilyClient = mock_client_cls
    with patch.dict("sys.modules", {"tavily": mock_tavily}):
        result = _web_search_tavily({"query": "flights"})
    assert "Result 1" in result
    assert "Result 2" in result


def test_web_search_tavily_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """web_search returns 'No results found' when empty."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    mock_client_cls = MagicMock()
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.search.return_value = {"results": []}

    mock_tavily = MagicMock()
    mock_tavily.TavilyClient = mock_client_cls
    with patch.dict("sys.modules", {"tavily": mock_tavily}):
        result = _web_search_tavily({"query": "nonexistent"})
    assert result == "No results found."
