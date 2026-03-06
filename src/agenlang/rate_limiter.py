"""
Rate Limiting: Token bucket and sliding window rate limiters
for AgenLang agent communication
"""

import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Any
from collections import deque
from abc import ABC, abstractmethod


class RateLimitStrategy(Enum):
    """Rate limiting strategies."""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_second: float = 10.0
    burst_size: int = 20
    window_size_seconds: float = 60.0
    strategy: RateLimitStrategy = RateLimitStrategy.TOKEN_BUCKET
    key_prefix: str = ""


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, key: str, retry_after: float, limit: float, remaining: int = 0):
        self.key = key
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        super().__init__(
            f"Rate limit exceeded for '{key}'. "
            f"Retry after {retry_after:.2f}s. "
            f"Limit: {limit}/s"
        )


class RateLimiter(ABC):
    """Abstract base class for rate limiters."""

    @abstractmethod
    def allow(self, key: str) -> bool:
        """Check if request is allowed. Returns True if allowed."""
        pass

    @abstractmethod
    def get_status(self, key: str) -> Dict[str, Any]:
        """Get rate limit status for a key."""
        pass

    @abstractmethod
    def reset(self, key: str):
        """Reset rate limit for a key."""
        pass


class TokenBucketRateLimiter(RateLimiter):
    """Token bucket rate limiter."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._buckets: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Check if request is allowed under token bucket."""
        full_key = f"{self.config.key_prefix}:{key}"
        now = time.time()

        with self._lock:
            bucket = self._buckets.get(full_key)

            if bucket is None:
                # Initialize new bucket
                self._buckets[full_key] = {
                    "tokens": self.config.burst_size - 1,  # Use one token
                    "last_update": now,
                }
                return True

            # Add tokens based on time elapsed
            elapsed = now - bucket["last_update"]
            tokens_to_add = elapsed * self.config.requests_per_second
            bucket["tokens"] = min(
                self.config.burst_size,
                bucket["tokens"] + tokens_to_add
            )
            bucket["last_update"] = now

            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return True
            else:
                return False

    def check_or_raise(self, key: str):
        """Check rate limit and raise if exceeded."""
        if not self.allow(key):
            status = self.get_status(key)
            retry_after = (1 - status["tokens"]) / self.config.requests_per_second
            raise RateLimitExceeded(
                key=key,
                retry_after=max(0.1, retry_after),
                limit=self.config.requests_per_second,
                remaining=0,
            )

    def get_status(self, key: str) -> Dict[str, Any]:
        """Get bucket status."""
        full_key = f"{self.config.key_prefix}:{key}"
        now = time.time()

        with self._lock:
            bucket = self._buckets.get(full_key)
            if bucket is None:
                return {
                    "limit": self.config.requests_per_second,
                    "remaining": self.config.burst_size,
                    "tokens": float(self.config.burst_size),
                    "reset_time": now,
                }

            # Calculate current tokens
            elapsed = now - bucket["last_update"]
            current_tokens = min(
                self.config.burst_size,
                bucket["tokens"] + elapsed * self.config.requests_per_second
            )

            return {
                "limit": self.config.requests_per_second,
                "remaining": int(current_tokens),
                "tokens": current_tokens,
                "reset_time": now + (self.config.burst_size - current_tokens) / self.config.requests_per_second,
            }

    def reset(self, key: str):
        """Reset bucket for key."""
        full_key = f"{self.config.key_prefix}:{key}"
        with self._lock:
            self._buckets.pop(full_key, None)

    def cleanup_old_buckets(self, max_age_seconds: float = 3600):
        """Remove buckets older than max_age."""
        now = time.time()
        with self._lock:
            old_keys = [
                k for k, v in self._buckets.items()
                if now - v["last_update"] > max_age_seconds
            ]
            for k in old_keys:
                del self._buckets[k]


class SlidingWindowRateLimiter(RateLimiter):
    """Sliding window rate limiter."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._windows: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Check if request is allowed under sliding window."""
        full_key = f"{self.config.key_prefix}:{key}"
        now = time.time()
        window_start = now - self.config.window_size_seconds

        with self._lock:
            window = self._windows.get(full_key)
            if window is None:
                self._windows[full_key] = deque([now])
                return True

            # Remove old timestamps
            while window and window[0] < window_start:
                window.popleft()

            # Check if under limit
            max_requests = int(self.config.requests_per_second * self.config.window_size_seconds)
            if len(window) < max_requests:
                window.append(now)
                return True
            else:
                return False

    def check_or_raise(self, key: str):
        """Check rate limit and raise if exceeded."""
        if not self.allow(key):
            status = self.get_status(key)
            raise RateLimitExceeded(
                key=key,
                retry_after=status["retry_after"],
                limit=self.config.requests_per_second * self.config.window_size_seconds,
                remaining=0,
            )

    def get_status(self, key: str) -> Dict[str, Any]:
        """Get window status."""
        full_key = f"{self.config.key_prefix}:{key}"
        now = time.time()
        window_start = now - self.config.window_size_seconds

        with self._lock:
            window = self._windows.get(full_key, deque())

            # Count requests in current window
            count = sum(1 for t in window if t > window_start)
            max_requests = int(self.config.requests_per_second * self.config.window_size_seconds)

            # Calculate retry after
            retry_after = 0.0
            if count >= max_requests and window:
                oldest = window[0]
                retry_after = (oldest + self.config.window_size_seconds) - now

            return {
                "limit": max_requests,
                "remaining": max(0, max_requests - count),
                "window_size": self.config.window_size_seconds,
                "retry_after": max(0, retry_after),
                "reset_time": now + retry_after,
            }

    def reset(self, key: str):
        """Reset window for key."""
        full_key = f"{self.config.key_prefix}:{key}"
        with self._lock:
            self._windows.pop(full_key, None)

    def cleanup_old_windows(self, max_age_seconds: float = 3600):
        """Remove windows older than max_age."""
        now = time.time()
        with self._lock:
            old_keys = [
                k for k, w in self._windows.items()
                if w and now - w[-1] > max_age_seconds
            ]
            for k in old_keys:
                del self._windows[k]


class FixedWindowRateLimiter(RateLimiter):
    """Fixed window rate limiter."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._windows: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _get_current_window(self) -> int:
        """Get current window identifier."""
        return int(time.time() / self.config.window_size_seconds)

    def allow(self, key: str) -> bool:
        """Check if request is allowed under fixed window."""
        full_key = f"{self.config.key_prefix}:{key}"
        current_window = self._get_current_window()

        with self._lock:
            window = self._windows.get(full_key)

            if window is None or window["window"] != current_window:
                # New window
                self._windows[full_key] = {
                    "window": current_window,
                    "count": 1,
                }
                return True

            max_requests = int(self.config.requests_per_second * self.config.window_size_seconds)
            if window["count"] < max_requests:
                window["count"] += 1
                return True
            else:
                return False

    def check_or_raise(self, key: str):
        """Check rate limit and raise if exceeded."""
        if not self.allow(key):
            status = self.get_status(key)
            raise RateLimitExceeded(
                key=key,
                retry_after=status["retry_after"],
                limit=self.config.requests_per_second * self.config.window_size_seconds,
                remaining=0,
            )

    def get_status(self, key: str) -> Dict[str, Any]:
        """Get window status."""
        full_key = f"{self.config.key_prefix}:{key}"
        current_window = self._get_current_window()

        with self._lock:
            window = self._windows.get(full_key)
            max_requests = int(self.config.requests_per_second * self.config.window_size_seconds)

            if window is None or window["window"] != current_window:
                return {
                    "limit": max_requests,
                    "remaining": max_requests,
                    "window": current_window,
                    "retry_after": 0.0,
                    "reset_time": (current_window + 1) * self.config.window_size_seconds,
                }

            remaining = max(0, max_requests - window["count"])
            retry_after = ((current_window + 1) * self.config.window_size_seconds) - time.time()

            return {
                "limit": max_requests,
                "remaining": remaining,
                "window": current_window,
                "retry_after": max(0, retry_after),
                "reset_time": (current_window + 1) * self.config.window_size_seconds,
            }

    def reset(self, key: str):
        """Reset window for key."""
        full_key = f"{self.config.key_prefix}:{key}"
        with self._lock:
            self._windows.pop(full_key, None)


class RateLimiterFactory:
    """Factory for creating rate limiters."""

    @staticmethod
    def create(config: RateLimitConfig) -> RateLimiter:
        """Create rate limiter based on config."""
        if config.strategy == RateLimitStrategy.TOKEN_BUCKET:
            return TokenBucketRateLimiter(config)
        elif config.strategy == RateLimitStrategy.SLIDING_WINDOW:
            return SlidingWindowRateLimiter(config)
        elif config.strategy == RateLimitStrategy.FIXED_WINDOW:
            return FixedWindowRateLimiter(config)
        else:
            raise ValueError(f"Unknown strategy: {config.strategy}")


class MultiRateLimiter:
    """Multiple rate limiters for different categories."""

    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
        self._configs: Dict[str, RateLimitConfig] = {}

    def add_limiter(self, name: str, config: RateLimitConfig):
        """Add a named rate limiter."""
        self._configs[name] = config
        self._limiters[name] = RateLimiterFactory.create(config)

    def allow(self, limiter_name: str, key: str) -> bool:
        """Check if request is allowed for a limiter."""
        limiter = self._limiters.get(limiter_name)
        if limiter is None:
            return True  # No limiter = no limit
        return limiter.allow(key)

    def check_or_raise(self, limiter_name: str, key: str):
        """Check rate limit and raise if exceeded."""
        limiter = self._limiters.get(limiter_name)
        if limiter:
            limiter.check_or_raise(key)

    def get_status(self, limiter_name: str, key: str) -> Optional[Dict[str, Any]]:
        """Get status for a limiter."""
        limiter = self._limiters.get(limiter_name)
        if limiter:
            return limiter.get_status(key)
        return None

    def reset(self, limiter_name: str, key: str):
        """Reset a limiter for a key."""
        limiter = self._limiters.get(limiter_name)
        if limiter:
            limiter.reset(key)

    def reset_all(self, key: str):
        """Reset all limiters for a key."""
        for limiter in self._limiters.values():
            limiter.reset(key)

    def get_all_statuses(self, key: str) -> Dict[str, Dict[str, Any]]:
        """Get status for all limiters."""
        return {
            name: limiter.get_status(key)
            for name, limiter in self._limiters.items()
        }


def create_default_limiters() -> MultiRateLimiter:
    """Create default multi-rate limiter configuration."""
    multi = MultiRateLimiter()

    # Per-agent rate limit: 100 req/min with burst of 20
    multi.add_limiter("agent", RateLimitConfig(
        requests_per_second=100/60,
        burst_size=20,
        window_size_seconds=60,
        strategy=RateLimitStrategy.TOKEN_BUCKET,
        key_prefix="agent",
    ))

    # Global rate limit: 1000 req/min
    multi.add_limiter("global", RateLimitConfig(
        requests_per_second=1000/60,
        burst_size=100,
        window_size_seconds=60,
        strategy=RateLimitStrategy.TOKEN_BUCKET,
        key_prefix="global",
    ))

    # Per-IP rate limit: 60 req/min
    multi.add_limiter("ip", RateLimitConfig(
        requests_per_second=60/60,
        burst_size=10,
        window_size_seconds=60,
        strategy=RateLimitStrategy.SLIDING_WINDOW,
        key_prefix="ip",
    ))

    # Contract execution rate limit: 30 req/min
    multi.add_limiter("contract", RateLimitConfig(
        requests_per_second=30/60,
        burst_size=5,
        window_size_seconds=60,
        strategy=RateLimitStrategy.TOKEN_BUCKET,
        key_prefix="contract",
    ))

    return multi
