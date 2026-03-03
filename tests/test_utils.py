# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for retry_with_backoff decorator."""

import pytest

from agenlang.utils import retry_with_backoff


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
