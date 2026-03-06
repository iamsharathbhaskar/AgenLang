"""Shared utilities for AgenLang adapters and runtime."""

import functools
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Type

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

# Embedding models by provider
_EMBEDDING_MODELS = {
    "openai": "text-embedding-ada-002",
    "openai-small": "text-embedding-3-small",
    "openai-large": "text-embedding-3-large",
}


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


@dataclass
class EmbeddingConfig:
    """Provider-agnostic embedding configuration.

    Reads from env vars: EMBEDDING_PROVIDER, EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL, EMBEDDING_MODEL.
    Falls back to OPENAI_API_KEY for OpenAI provider.
    """

    provider: str = "openai"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "text-embedding-ada-002"
    timeout: float = 30.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """Build config from environment variables."""
        provider = os.environ.get("EMBEDDING_PROVIDER", "openai")

        # API key: try EMBEDDING_API_KEY first, then provider-specific
        api_key = os.environ.get("EMBEDDING_API_KEY", "")
        if not api_key and provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")

        if not api_key:
            raise ValueError(
                f"EMBEDDING_API_KEY (or OPENAI_API_KEY for OpenAI) "
                f"required for embedding operations"
            )

        # Base URL
        base_url = os.environ.get(
            "EMBEDDING_BASE_URL",
            _PROVIDER_URLS.get(provider, "https://api.openai.com/v1")
        )

        # Model selection
        model = os.environ.get(
            "EMBEDDING_MODEL",
            _EMBEDDING_MODELS.get(provider, "text-embedding-ada-002")
        )

        # Timeout and retries
        timeout = float(os.environ.get("EMBEDDING_TIMEOUT", "30.0"))
        max_retries = int(os.environ.get("EMBEDDING_MAX_RETRIES", "3"))

        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout=timeout,
            max_retries=max_retries,
        )


class EmbeddingClient:
    """Client for generating text embeddings via OpenAI API."""

    def __init__(self, config: Optional[EmbeddingConfig] = None) -> None:
        """Initialize embedding client.

        Args:
            config: Embedding configuration. If None, reads from env.
        """
        self.config = config or EmbeddingConfig.from_env()
        self._session = None

    def _get_session(self):
        """Get or create requests session."""
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    @retry_with_backoff(max_retries=3, base_delay=1.0, timeout=30.0)
    def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            ValueError: If API call fails or returns invalid response.
            TimeoutError: If request times out.
        """
        import requests

        if not text or not text.strip():
            # Return zero vector for empty text (dimension depends on model)
            # Ada-002 and text-embedding-3 models use 1536 dimensions
            return [0.0] * 1536

        session = self._get_session()

        try:
            resp = session.post(
                f"{self.config.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": text,
                    "model": self.config.model,
                },
                timeout=self.config.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            embedding = data.get("data", [{}])[0].get("embedding", [])
            if not embedding:
                raise ValueError("Empty embedding returned from API")

            return embedding

        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"Embedding request timed out: {e}")
        except requests.exceptions.HTTPError as e:
            raise ValueError(f"Embedding API error: {e}")
        except Exception as e:
            raise ValueError(f"Failed to generate embedding: {e}")

    @retry_with_backoff(max_retries=3, base_delay=1.0, timeout=60.0)
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed.
            
        Returns:
            List of embedding vectors.
        """
        import requests
        
        if not texts:
            return []
        
        # Filter out empty texts and track their positions
        valid_texts = []
        empty_indices = set()
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
            else:
                empty_indices.add(i)
        
        if not valid_texts:
            return [[0.0] * 1536] * len(texts)
        
        session = self._get_session()
        
        try:
            resp = session.post(
                f"{self.config.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": valid_texts,
                    "model": self.config.model,
                },
                timeout=self.config.timeout * 2,  # Longer timeout for batch
            )
            resp.raise_for_status()
            data = resp.json()
            
            # Extract embeddings and map by index
            embeddings_data = data.get("data", [])
            # Create a map from original valid text index to embedding
            embedding_map = {}
            for item in embeddings_data:
                idx = item.get("index", 0)
                embedding_map[idx] = item.get("embedding", [])
            
            # Reconstruct with zero vectors for empty inputs
            result = []
            valid_idx = 0
            for i in range(len(texts)):
                if i in empty_indices:
                    result.append([0.0] * 1536)
                else:
                    # Get embedding from the map using valid_idx
                    embedding = embedding_map.get(valid_idx, [0.0] * 1536)
                    result.append(embedding)
                    valid_idx += 1
            
            return result
            
        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"Batch embedding request timed out: {e}")
        except requests.exceptions.HTTPError as e:
            raise ValueError(f"Embedding API error: {e}")
        except Exception as e:
            raise ValueError(f"Failed to generate embeddings: {e}")

    def embed_to_json(self, text: str) -> str:
        """Generate embedding and return as JSON string.

        Args:
            text: Text to embed.

        Returns:
            JSON string containing the embedding vector.
        """
        embedding = self.embed(text)
        return json.dumps(embedding)


def sha256_hash(data: bytes) -> str:
    """Compute SHA-256 hash of data.

    Args:
        data: Bytes to hash.

    Returns:
        Hexadecimal hash string.
    """
    return hashlib.sha256(data).hexdigest()


def current_timestamp() -> str:
    """Get current UTC timestamp in ISO format.

    Returns:
        ISO 8601 formatted timestamp string.
    """
    return datetime.now(timezone.utc).isoformat()


def canonical_json(data: Dict[str, Any]) -> str:
    """Convert data to canonical JSON string for signing.

    Produces a deterministic JSON representation by sorting keys
    and removing whitespace.

    Args:
        data: Dictionary to serialize.

    Returns:
        Canonical JSON string.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"))
