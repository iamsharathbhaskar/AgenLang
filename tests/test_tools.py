"""Tests for tools (mock API calls)."""

import os

import pytest

from agenlang.tools import TOOLS, _summarize_grok, _web_search_tavily, register_tool


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
    """summarize raises when XAI_API_KEY missing."""
    had = os.environ.pop("XAI_API_KEY", None)
    try:
        with pytest.raises(ValueError, match="XAI_API_KEY"):
            _summarize_grok({"text": "test"})
    finally:
        if had:
            os.environ["XAI_API_KEY"] = had


def test_register_tool() -> None:
    """register_tool adds custom tool."""

    def _custom(args):
        return str(args.get("x", 0))

    register_tool("custom", ["compute:read"], _custom, "Custom", joule_cost=50.0)
    assert "custom" in TOOLS
    assert TOOLS["custom"]["joule_cost"] == 50.0
    assert TOOLS["custom"]["function"]({"x": 42}) == "42"
