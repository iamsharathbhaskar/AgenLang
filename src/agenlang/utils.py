"""Shared utilities for AgenLang adapters and runtime."""

import functools
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Type

import structlog

log = structlog.get_logger()

_PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "xai": "https://api.x.ai/v1",
}

_PROVIDER_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-haiku-20240307",
    "xai": "grok-3-mini",
}


@dataclass
class LLMConfig:
    """Provider-agnostic LLM configuration.

    Reads from env vars: LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL.
    Falls back to legacy XAI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY.
    """

    provider: str
    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Build config from environment variables."""
        provider = os.environ.get("LLM_PROVIDER", "xai")
        api_key = os.environ.get("LLM_API_KEY", "")
        if not api_key:
            for legacy_var in ("XAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                api_key = os.environ.get(legacy_var, "")
                if api_key:
                    break
        if not api_key:
            raise ValueError(
                "LLM_API_KEY (or XAI_API_KEY / OPENAI_API_KEY / "
                "ANTHROPIC_API_KEY) required for summarize tool"
            )
        base_url = os.environ.get("LLM_BASE_URL", _PROVIDER_URLS.get(provider, ""))
        if not base_url:
            raise ValueError(
                f"LLM_BASE_URL required for provider '{provider}' "
                "(or use openai/anthropic/xai)"
            )
        model = os.environ.get(
            "LLM_MODEL", _PROVIDER_MODELS.get(provider, "gpt-4o-mini")
        )
        return cls(provider=provider, api_key=api_key, base_url=base_url, model=model)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    timeout: float = 30.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator: exponential backoff retry with cumulative timeout.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay between retries.
        timeout: Total cumulative timeout in seconds.
        exceptions: Exception types to catch and retry on.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                elapsed = time.monotonic() - start
                if attempt > 0 and elapsed >= timeout:
                    raise TimeoutError(
                        f"{func.__name__} timed out after {elapsed:.1f}s "
                        f"({attempt} attempts)"
                    )
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2**attempt), max_delay)
                        remaining = timeout - (time.monotonic() - start)
                        if remaining <= 0:
                            raise TimeoutError(
                                f"{func.__name__} timed out after "
                                f"{time.monotonic() - start:.1f}s"
                            ) from e
                        actual_delay = min(delay, remaining)
                        log.warning(
                            "retry_backoff",
                            func=func.__name__,
                            attempt=attempt + 1,
                            delay=actual_delay,
                            error=str(e),
                        )
                        time.sleep(actual_delay)
            if last_exc:
                raise last_exc
            return None  # unreachable

        return wrapper

    return decorator
