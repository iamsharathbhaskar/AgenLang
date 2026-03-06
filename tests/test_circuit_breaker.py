"""Tests for circuit breaker module."""

import time
import pytest
from agenlang.circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitState,
    CircuitBreakerOpenError, CircuitBreakerExecutionError,
    CircuitBreakerRegistry,
    RetryPolicy, TimeoutPolicy,
    circuit_breaker, with_retry, with_timeout,
    get_registry as get_cb_registry,
)


class TestCircuitBreaker:
    """Test CircuitBreaker."""

    def test_initial_state_is_closed(self):
        """Test initial state is CLOSED."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("test", config)

        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_record_success_does_not_change_state(self):
        """Test recording success doesn't change state."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("test", config)

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_record_failure_opens_after_threshold(self):
        """Test circuit opens after failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # Still closed

        cb.record_failure()
        assert cb.state == CircuitState.OPEN  # Now open
        assert cb.can_execute() is False

    def test_half_open_after_timeout(self):
        """Test circuit enters half-open after timeout."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=0.1,
        )
        cb = CircuitBreaker("test", config)

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.can_execute() is True  # Should allow in half-open
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_after_success_threshold(self):
        """Test circuit closes after success threshold."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=0.1,
            success_threshold=2,
        )
        cb = CircuitBreaker("test", config)

        # Open the circuit
        cb.record_failure()
        time.sleep(0.15)

        # Enter half-open and succeed twice
        cb.can_execute()  # Enter half-open
        cb.record_success()
        cb.can_execute()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens(self):
        """Test failure in half-open reopens circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            timeout_seconds=0.1,
        )
        cb = CircuitBreaker("test", config)

        cb.record_failure()
        time.sleep(0.15)
        cb.can_execute()

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_execute_success(self):
        """Test execute with successful function."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("test", config)

        def success_func():
            return "success"

        result = cb.execute(success_func)
        assert result == "success"

    def test_execute_records_success(self):
        """Test execute records success."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("test", config)

        cb.execute(lambda: "ok")

        status = cb.get_status()
        assert status["failure_count"] == 0

    def test_execute_records_failure(self):
        """Test execute records failure."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("test", config)

        with pytest.raises(CircuitBreakerExecutionError):
            cb.execute(lambda: 1/0)

        status = cb.get_status()
        assert status["failure_count"] == 1

    def test_execute_raises_when_open(self):
        """Test execute raises when circuit is open."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", config)

        cb.record_failure()

        with pytest.raises(CircuitBreakerOpenError):
            cb.execute(lambda: "ok")

    def test_get_status(self):
        """Test getting circuit breaker status."""
        config = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker("test", config)

        status = cb.get_status()

        assert status["name"] == "test"
        assert status["state"] == "CLOSED"
        assert status["failure_threshold"] == 5
        assert status["failure_count"] == 0

    def test_decorator(self):
        """Test circuit breaker as decorator."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("test", config)

        @cb
        def my_function():
            return "decorated"

        assert my_function() == "decorated"


class TestCircuitBreakerRegistry:
    """Test CircuitBreakerRegistry."""

    def test_get_or_create_creates_new(self):
        """Test get_or_create creates new breaker."""
        registry = CircuitBreakerRegistry()
        config = CircuitBreakerConfig()

        cb = registry.get_or_create("test", config)

        assert cb.name == "test"
        assert cb.state == CircuitState.CLOSED

    def test_get_or_create_returns_existing(self):
        """Test get_or_create returns existing breaker."""
        registry = CircuitBreakerRegistry()
        config = CircuitBreakerConfig()

        cb1 = registry.get_or_create("test", config)
        cb1.record_failure()

        cb2 = registry.get_or_create("test", config)
        assert cb1 is cb2
        assert cb2.get_status()["failure_count"] == 1

    def test_get_returns_none_for_missing(self):
        """Test get returns None for missing breaker."""
        registry = CircuitBreakerRegistry()

        assert registry.get("missing") is None

    def test_remove(self):
        """Test removing breaker."""
        registry = CircuitBreakerRegistry()
        registry.get_or_create("test", CircuitBreakerConfig())

        registry.remove("test")

        assert registry.get("test") is None

    def test_all_statuses(self):
        """Test getting all statuses."""
        registry = CircuitBreakerRegistry()
        registry.get_or_create("cb1", CircuitBreakerConfig())
        registry.get_or_create("cb2", CircuitBreakerConfig())

        statuses = registry.all_statuses()

        assert "cb1" in statuses
        assert "cb2" in statuses

    def test_reset_all(self):
        """Test resetting all breakers."""
        registry = CircuitBreakerRegistry()
        cb = registry.get_or_create("test", CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure()

        registry.reset_all()

        assert cb.state == CircuitState.CLOSED


class TestRetryPolicy:
    """Test RetryPolicy."""

    def test_success_on_first_attempt(self):
        """Test success on first attempt."""
        policy = RetryPolicy(max_attempts=3)

        call_count = 0
        def success():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = policy.execute(success)

        assert result == "ok"
        assert call_count == 1

    def test_retry_on_failure(self):
        """Test retry on failure."""
        policy = RetryPolicy(max_attempts=3, base_delay=0.01)

        call_count = 0
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("fail")
            return "ok"

        result = policy.execute(flaky)

        assert result == "ok"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        """Test raises after max attempts."""
        policy = RetryPolicy(max_attempts=3, base_delay=0.01)

        def always_fail():
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            policy.execute(always_fail)

    def test_calculate_delay_with_jitter(self):
        """Test delay calculation includes jitter."""
        policy = RetryPolicy(
            max_attempts=3,
            base_delay=1.0,
            exponential_base=2.0,
        )

        delay = policy.calculate_delay(0)
        assert 0.75 <= delay <= 1.25  # 1.0 ± 25%

        delay = policy.calculate_delay(1)
        assert 1.5 <= delay <= 2.5  # 2.0 ± 25%

    def test_calculate_delay_respects_max(self):
        """Test delay calculation respects max_delay."""
        policy = RetryPolicy(
            max_attempts=10,
            base_delay=1.0,
            exponential_base=2.0,
            max_delay=5.0,
        )

        delay = policy.calculate_delay(10)  # Would be 1024 without max
        assert delay <= 6.25  # 5.0 + 25% jitter


class TestTimeoutPolicy:
    """Test TimeoutPolicy."""

    def test_success_within_timeout(self):
        """Test success within timeout."""
        policy = TimeoutPolicy(timeout_seconds=1.0)

        def quick():
            return "ok"

        result = policy.execute(quick)
        assert result == "ok"

    def test_timeout_exceeded(self):
        """Test timeout exceeded raises."""
        policy = TimeoutPolicy(timeout_seconds=0.1)

        def slow():
            time.sleep(0.5)
            return "ok"

        with pytest.raises(TimeoutError):
            policy.execute(slow)


class TestWithRetryDecorator:
    """Test with_retry decorator."""

    def test_success_on_first_try(self):
        """Test success on first try."""
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        def success():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert success() == "ok"
        assert call_count == 1

    def test_retry_then_success(self):
        """Test retry then success."""
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "ok"

        assert flaky() == "ok"
        assert call_count == 2


class TestWithTimeoutDecorator:
    """Test with_timeout decorator."""

    def test_success_within_timeout(self):
        """Test success within timeout."""
        @with_timeout(timeout_seconds=1.0)
        def quick():
            return "ok"

        assert quick() == "ok"

    def test_timeout_raises(self):
        """Test timeout raises."""
        @with_timeout(timeout_seconds=0.1)
        def slow():
            time.sleep(0.5)
            return "ok"

        with pytest.raises(TimeoutError):
            slow()


class TestCircuitBreakerDecorator:
    """Test circuit_breaker decorator factory."""

    def test_creates_decorator(self):
        """Test creates working decorator."""
        decorator = circuit_breaker("test_cb")

        @decorator
        def success():
            return "ok"

        assert success() == "ok"

    def test_shares_state_via_registry(self):
        """Test shared state through global registry."""
        cb1 = circuit_breaker("shared")
        cb2 = circuit_breaker("shared")  # Same name

        @cb1
        def fail():
            raise ValueError("fail")

        # Open the circuit
        for _ in range(6):
            try:
                fail()
            except:
                pass

        @cb2
        def success():
            return "ok"

        # Circuit should be open for both
        with pytest.raises(CircuitBreakerOpenError):
            success()


class TestGlobalRegistry:
    """Test global registry."""

    def test_get_registry_returns_singleton(self):
        """Test get_registry returns singleton."""
        r1 = get_cb_registry()
        r2 = get_cb_registry()
        assert r1 is r2
