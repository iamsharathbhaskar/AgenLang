# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for retry_with_backoff decorator and LLMConfig."""

import pytest

from agenlang.utils import LLMConfig, retry_with_backoff


def test_retry_succeeds_on_second_attempt() -> None:
    """Retry decorator succeeds after first failure."""
    call_count = 0

    @retry_with_backoff(max_retries=3, base_delay=0.01, timeout=5.0)
    def flaky() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("transient error")
        return "ok"

    assert flaky() == "ok"
    assert call_count == 2


def test_retry_max_retries_exceeded() -> None:
    """Retry decorator raises after exhausting retries."""

    @retry_with_backoff(max_retries=2, base_delay=0.01, timeout=5.0)
    def always_fail() -> str:
        raise ValueError("persistent error")

    with pytest.raises(ValueError, match="persistent error"):
        always_fail()


def test_retry_timeout() -> None:
    """Retry decorator raises TimeoutError when cumulative time exceeds timeout."""
    import time

    @retry_with_backoff(max_retries=10, base_delay=0.5, timeout=0.1)
    def slow_fail() -> str:
        time.sleep(0.05)
        raise ValueError("slow")

    with pytest.raises((TimeoutError, ValueError)):
        slow_fail()


def test_retry_no_retries_needed() -> None:
    """Retry decorator passes through on first success."""

    @retry_with_backoff(max_retries=3, base_delay=0.01, timeout=5.0)
    def succeeds() -> int:
        return 42

    assert succeeds() == 42


def test_retry_specific_exceptions() -> None:
    """Retry decorator only catches specified exception types."""

    @retry_with_backoff(
        max_retries=3,
        base_delay=0.01,
        timeout=5.0,
        exceptions=(ValueError,),
    )
    def raises_type_error() -> str:
        raise TypeError("wrong type")

    with pytest.raises(TypeError, match="wrong type"):
        raises_type_error()


def test_llm_config_xai(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMConfig defaults to xai provider."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "xai")
    config = LLMConfig.from_env()
    assert config.provider == "xai"
    assert config.api_key == "test-key"
    assert "x.ai" in config.base_url
    assert config.model == "grok-3-mini"


def test_llm_config_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMConfig with openai provider."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "oai-key")
    config = LLMConfig.from_env()
    assert config.provider == "openai"
    assert "openai.com" in config.base_url
    assert config.model == "gpt-4o-mini"


def test_llm_config_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMConfig with anthropic provider."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "ant-key")
    config = LLMConfig.from_env()
    assert config.provider == "anthropic"
    assert "anthropic.com" in config.base_url
    assert "claude" in config.model


def test_llm_config_fallback_xai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMConfig falls back to XAI_API_KEY when LLM_API_KEY not set."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "legacy-xai")
    config = LLMConfig.from_env()
    assert config.api_key == "legacy-xai"


def test_llm_config_no_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMConfig raises ValueError when no API key is available."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        LLMConfig.from_env()


def test_llm_config_generic_needs_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMConfig with generic provider requires LLM_BASE_URL."""
    monkeypatch.setenv("LLM_PROVIDER", "generic")
    monkeypatch.setenv("LLM_API_KEY", "my-key")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        LLMConfig.from_env()


def test_llm_config_generic_with_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMConfig with generic provider and custom base URL."""
    monkeypatch.setenv("LLM_PROVIDER", "generic")
    monkeypatch.setenv("LLM_API_KEY", "my-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://my-llm.example.com/v1")
    config = LLMConfig.from_env()
    assert config.base_url == "https://my-llm.example.com/v1"
