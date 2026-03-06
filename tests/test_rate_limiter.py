"""Tests for rate limiter module."""

import time
import pytest
from agenlang.rate_limiter import (
    TokenBucketRateLimiter,
    SlidingWindowRateLimiter,
    FixedWindowRateLimiter,
    MultiRateLimiter,
    RateLimitConfig,
    RateLimitStrategy,
    RateLimitExceeded,
    RateLimiterFactory,
    create_default_limiters,
)


class TestTokenBucketRateLimiter:
    """Test TokenBucketRateLimiter."""

    def test_allow_initial_burst(self):
        """Test initial burst is allowed."""
        config = RateLimitConfig(
            requests_per_second=10,
            burst_size=5,
        )
        limiter = TokenBucketRateLimiter(config)

        # Should allow burst_size requests
        for _ in range(5):
            assert limiter.allow("key1") is True

        # 6th should fail
        assert limiter.allow("key1") is False

    def test_allow_refill(self):
        """Test token refill over time."""
        config = RateLimitConfig(
            requests_per_second=10,  # 1 token per 100ms
            burst_size=2,
        )
        limiter = TokenBucketRateLimiter(config)

        # Use up tokens
        limiter.allow("key1")
        limiter.allow("key1")
        assert limiter.allow("key1") is False

        # Wait for refill
        time.sleep(0.15)
        assert limiter.allow("key1") is True

    def test_different_keys_independent(self):
        """Test different keys have independent buckets."""
        config = RateLimitConfig(
            requests_per_second=10,
            burst_size=2,
        )
        limiter = TokenBucketRateLimiter(config)

        # Exhaust key1
        limiter.allow("key1")
        limiter.allow("key1")
        assert limiter.allow("key1") is False

        # key2 should still work
        assert limiter.allow("key2") is True

    def test_check_or_raise_allows(self):
        """Test check_or_raise when allowed."""
        config = RateLimitConfig(
            requests_per_second=10,
            burst_size=5,
        )
        limiter = TokenBucketRateLimiter(config)

        # Should not raise
        limiter.check_or_raise("key1")

    def test_check_or_raise_raises(self):
        """Test check_or_raise when exceeded."""
        config = RateLimitConfig(
            requests_per_second=10,
            burst_size=1,
        )
        limiter = TokenBucketRateLimiter(config)

        limiter.allow("key1")  # Use the one token

        with pytest.raises(RateLimitExceeded) as exc_info:
            limiter.check_or_raise("key1")

        assert exc_info.value.key == "key1"
        assert exc_info.value.retry_after > 0

    def test_get_status(self):
        """Test getting bucket status."""
        config = RateLimitConfig(
            requests_per_second=10,
            burst_size=5,
        )
        limiter = TokenBucketRateLimiter(config)

        status = limiter.get_status("key1")

        assert status["limit"] == 10
        assert status["remaining"] == 5
        assert status["tokens"] == 5.0

    def test_reset(self):
        """Test resetting a bucket."""
        config = RateLimitConfig(
            requests_per_second=10,
            burst_size=2,
        )
        limiter = TokenBucketRateLimiter(config)

        # Exhaust bucket
        limiter.allow("key1")
        limiter.allow("key1")
        assert limiter.allow("key1") is False

        # Reset
        limiter.reset("key1")
        assert limiter.allow("key1") is True


class TestSlidingWindowRateLimiter:
    """Test SlidingWindowRateLimiter."""

    def test_allow_within_window(self):
        """Test allowing requests within window."""
        config = RateLimitConfig(
            requests_per_second=10,
            window_size_seconds=1,
        )
        limiter = SlidingWindowRateLimiter(config)

        # Should allow up to 10 requests
        for _ in range(10):
            assert limiter.allow("key1") is True

        # 11th should fail
        assert limiter.allow("key1") is False

    def test_window_slides(self):
        """Test window slides over time."""
        config = RateLimitConfig(
            requests_per_second=5,  # 5 per second
            window_size_seconds=0.5,  # 500ms window = ~2.5 requests
        )
        limiter = SlidingWindowRateLimiter(config)

        # Use up window
        limiter.allow("key1")
        limiter.allow("key1")
        assert limiter.allow("key1") is False

        # Wait for window to slide
        time.sleep(0.6)
        assert limiter.allow("key1") is True

    def test_get_status_includes_retry_after(self):
        """Test status includes retry_after when limited."""
        config = RateLimitConfig(
            requests_per_second=2,
            window_size_seconds=1,
        )
        limiter = SlidingWindowRateLimiter(config)

        # Exhaust limit
        limiter.allow("key1")
        limiter.allow("key1")

        status = limiter.get_status("key1")
        assert status["remaining"] == 0
        assert status["retry_after"] > 0


class TestFixedWindowRateLimiter:
    """Test FixedWindowRateLimiter."""

    def test_allow_within_window(self):
        """Test allowing requests within fixed window."""
        config = RateLimitConfig(
            requests_per_second=10,
            window_size_seconds=1,
        )
        limiter = FixedWindowRateLimiter(config)

        for _ in range(10):
            assert limiter.allow("key1") is True

        assert limiter.allow("key1") is False

    def test_window_resets(self):
        """Test window resets after duration."""
        config = RateLimitConfig(
            requests_per_second=2,
            window_size_seconds=0.1,  # 100ms window
        )
        limiter = FixedWindowRateLimiter(config)

        limiter.allow("key1")
        limiter.allow("key1")
        assert limiter.allow("key1") is False

        time.sleep(0.15)
        assert limiter.allow("key1") is True


class TestMultiRateLimiter:
    """Test MultiRateLimiter."""

    def test_add_limiter(self):
        """Test adding named limiters."""
        multi = MultiRateLimiter()

        config = RateLimitConfig(requests_per_second=10, burst_size=5)
        multi.add_limiter("api", config)

        assert "api" in multi._limiters

    def test_allow_checks_all(self):
        """Test allow checks specific limiter."""
        multi = MultiRateLimiter()

        config = RateLimitConfig(requests_per_second=10, burst_size=1)
        multi.add_limiter("api", config)

        assert multi.allow("api", "key1") is True
        assert multi.allow("api", "key1") is False

    def test_missing_limiter_allows(self):
        """Test missing limiter allows all."""
        multi = MultiRateLimiter()

        # No limiter added
        assert multi.allow("api", "key1") is True

    def test_check_or_raise(self):
        """Test check_or_raise raises when exceeded."""
        multi = MultiRateLimiter()

        config = RateLimitConfig(requests_per_second=10, burst_size=1)
        multi.add_limiter("api", config)

        multi.allow("api", "key1")  # Use token

        with pytest.raises(RateLimitExceeded):
            multi.check_or_raise("api", "key1")

    def test_get_all_statuses(self):
        """Test getting all limiter statuses."""
        multi = MultiRateLimiter()

        multi.add_limiter("api", RateLimitConfig(requests_per_second=10, burst_size=5))
        multi.add_limiter("web", RateLimitConfig(requests_per_second=20, burst_size=10))

        statuses = multi.get_all_statuses("key1")

        assert "api" in statuses
        assert "web" in statuses
        assert statuses["api"]["remaining"] == 5
        assert statuses["web"]["remaining"] == 10


class TestRateLimiterFactory:
    """Test RateLimiterFactory."""

    def test_create_token_bucket(self):
        """Test creating token bucket limiter."""
        config = RateLimitConfig(strategy=RateLimitStrategy.TOKEN_BUCKET)
        limiter = RateLimiterFactory.create(config)

        assert isinstance(limiter, TokenBucketRateLimiter)

    def test_create_sliding_window(self):
        """Test creating sliding window limiter."""
        config = RateLimitConfig(strategy=RateLimitStrategy.SLIDING_WINDOW)
        limiter = RateLimiterFactory.create(config)

        assert isinstance(limiter, SlidingWindowRateLimiter)

    def test_create_fixed_window(self):
        """Test creating fixed window limiter."""
        config = RateLimitConfig(strategy=RateLimitStrategy.FIXED_WINDOW)
        limiter = RateLimiterFactory.create(config)

        assert isinstance(limiter, FixedWindowRateLimiter)


class TestCreateDefaultLimiters:
    """Test create_default_limiters."""

    def test_creates_expected_limiters(self):
        """Test creates expected default limiters."""
        multi = create_default_limiters()

        assert "agent" in multi._limiters
        assert "global" in multi._limiters
        assert "ip" in multi._limiters
        assert "contract" in multi._limiters

    def test_global_limiter_config(self):
        """Test global limiter has correct config."""
        multi = create_default_limiters()

        config = multi._configs["global"]
        assert config.requests_per_second == 1000/60  # 1000 per minute
        assert config.burst_size == 100

    def test_contract_limiter_config(self):
        """Test contract limiter has correct config."""
        multi = create_default_limiters()

        config = multi._configs["contract"]
        assert config.requests_per_second == 30/60  # 30 per minute
        assert config.burst_size == 5
