"""
Circuit Breaker: Fault tolerance for agent communication
Prevents cascading failures and provides graceful degradation
"""

import time
import inspect
import threading
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Callable, Any, Type, Tuple
from functools import wraps


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = auto()      # Normal operation
    OPEN = auto()        # Failing, rejecting requests
    HALF_OPEN = auto()   # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5           # Failures before opening
    success_threshold: int = 3           # Successes before closing
    timeout_seconds: float = 30.0        # Time before half-open
    half_open_max_calls: int = 3         # Max calls in half-open
    expected_exception: Tuple[Type[Exception], ...] = (Exception,)


class CircuitBreaker:
    """Circuit breaker for fault tolerance."""

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        """Get current state."""
        with self._lock:
            return self._state

    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if timeout elapsed
                if self._last_failure_time and \
                   (time.time() - self._last_failure_time) >= self.config.timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    return True
                return False

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            return False

    def record_success(self):
        """Record successful execution."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._reset()
            else:
                self._failure_count = 0

    def record_failure(self):
        """Record failed execution."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._success_count = 0
            elif self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN

    def _reset(self):
        """Reset circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0

    def get_status(self) -> dict:
        """Get circuit breaker status."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.name,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds,
                "last_failure_time": self._last_failure_time,
                "time_until_half_open": max(0, self.config.timeout_seconds - (time.time() - self._last_failure_time)) if self._last_failure_time and self._state == CircuitState.OPEN else 0,
            }

    def __call__(self, func: Callable) -> Callable:
        """Decorator to wrap function with circuit breaker."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            return self.execute(func, *args, **kwargs)
        return wrapper

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        if not self.can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN",
                breaker=self,
            )

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except self.config.expected_exception as e:
            self.record_failure()
            raise CircuitBreakerExecutionError(
                f"Execution failed in circuit breaker '{self.name}': {e}",
                original_error=e,
                breaker=self,
            ) from e

    async def execute_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function with circuit breaker protection."""
        import asyncio

        if not self.can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is OPEN",
                breaker=self,
            )

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self.record_success()
            return result
        except self.config.expected_exception as e:
            self.record_failure()
            raise CircuitBreakerExecutionError(
                f"Execution failed in circuit breaker '{self.name}': {e}",
                original_error=e,
                breaker=self,
            ) from e


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, message: str, breaker: CircuitBreaker):
        super().__init__(message)
        self.breaker = breaker
        self.retry_after = breaker.config.timeout_seconds


class CircuitBreakerExecutionError(Exception):
    """Raised when execution fails within circuit breaker."""

    def __init__(self, message: str, original_error: Exception, breaker: CircuitBreaker):
        super().__init__(message)
        self.original_error = original_error
        self.breaker = breaker


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker."""
        with self._lock:
            if name not in self._breakers:
                cfg = config or CircuitBreakerConfig()
                self._breakers[name] = CircuitBreaker(name, cfg)
            return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        with self._lock:
            return self._breakers.get(name)

    def remove(self, name: str):
        """Remove circuit breaker."""
        with self._lock:
            self._breakers.pop(name, None)

    def all_statuses(self) -> dict:
        """Get status of all circuit breakers."""
        with self._lock:
            return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    def reset_all(self):
        """Reset all circuit breakers."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker._reset()


# Global registry
_global_registry = CircuitBreakerRegistry()


def get_registry() -> CircuitBreakerRegistry:
    """Get global circuit breaker registry."""
    return _global_registry


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    success_threshold: int = 3,
    timeout_seconds: float = 30.0,
    expected_exception: Tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator factory for circuit breaker pattern."""
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout_seconds=timeout_seconds,
        expected_exception=expected_exception,
    )
    breaker = _global_registry.get_or_create(name, config)
    return breaker


class RetryPolicy:
    """Retry policy for resilient operations."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        on_retry: Optional[Callable[[int, Exception], None]] = None,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retryable_exceptions = retryable_exceptions
        self.on_retry = on_retry

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for attempt (with jitter)."""
        import random
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay,
        )
        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        return delay + jitter

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute with retry logic."""
        last_exception = None

        for attempt in range(self.max_attempts):
            try:
                return func(*args, **kwargs)
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt < self.max_attempts - 1:
                    if self.on_retry:
                        self.on_retry(attempt + 1, e)
                    delay = self.calculate_delay(attempt)
                    time.sleep(delay)
                else:
                    break

        raise last_exception

    async def execute_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async with retry logic."""
        import asyncio

        last_exception = None

        for attempt in range(self.max_attempts):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt < self.max_attempts - 1:
                    if self.on_retry:
                        self.on_retry(attempt + 1, e)
                    delay = self.calculate_delay(attempt)
                    await asyncio.sleep(delay)
                else:
                    break

        raise last_exception


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator for retry logic."""
    policy = RetryPolicy(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        retryable_exceptions=retryable_exceptions,
    )

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return policy.execute(func, *args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await policy.execute_async(func, *args, **kwargs)

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


class TimeoutPolicy:
    """Timeout policy for operations."""

    def __init__(self, timeout_seconds: float):
        self.timeout_seconds = timeout_seconds

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute with timeout."""
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            try:
                return future.result(timeout=self.timeout_seconds)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(f"Operation timed out after {self.timeout_seconds}s")

    async def execute_async(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async with timeout."""
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.timeout_seconds,
            )
        else:
            # Run sync function in thread pool with timeout
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, func, *args, **kwargs),
                timeout=self.timeout_seconds,
            )


def with_timeout(timeout_seconds: float):
    """Decorator for timeout."""
    policy = TimeoutPolicy(timeout_seconds)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return policy.execute(func, *args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await policy.execute_async(func, *args, **kwargs)

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator
