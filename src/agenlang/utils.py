"""Shared utilities for AgenLang adapters and runtime."""

import functools
import time
from typing import Any, Callable, Type

import structlog

log = structlog.get_logger()


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
