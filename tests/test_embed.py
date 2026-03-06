# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for embedding functionality — unit and integration tests."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agenlang.contract import Contract
from agenlang.keys import KeyManager
from agenlang.runtime import Runtime
from agenlang.utils import EmbeddingClient, EmbeddingConfig

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


class TestEmbeddingConfig:
    """Unit tests for EmbeddingConfig."""

    def test_from_env_defaults(self, monkeypatch):
        """Config reads defaults from environment."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
        
        config = EmbeddingConfig.from_env()
        
        assert config.provider == "openai"
        assert config.api_key == "test-key"
        assert config.model == "text-embedding-ada-002"
        assert config.base_url == "https://api.openai.com/v1"
        assert config.timeout == 30.0
        assert config.max_retries == 3

    def test_from_env_custom_values(self, monkeypatch):
        """Config reads custom values from environment."""
        monkeypatch.setenv("EMBEDDING_API_KEY", "custom-key")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
        monkeypatch.setenv("EMBEDDING_BASE_URL", "https://custom.openai.com/v1")
        monkeypatch.setenv("EMBEDDING_TIMEOUT", "60")
        monkeypatch.setenv("EMBEDDING_MAX_RETRIES", "5")
        
        config = EmbeddingConfig.from_env()
        
        assert config.api_key == "custom-key"
        assert config.model == "text-embedding-3-small"
        assert config.base_url == "https://custom.openai.com/v1"
        assert config.timeout == 60.0
        assert config.max_retries == 5

    def test_from_env_missing_api_key(self, monkeypatch):
        """Config raises if no API key available."""
        monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
            EmbeddingConfig.from_env()


class TestEmbeddingClient:
    """Unit tests for EmbeddingClient."""

    def test_init_with_config(self):
        """Client initializes with provided config."""
        config = EmbeddingConfig(api_key="test-key", model="text-embedding-ada-002")
        client = EmbeddingClient(config)
        
        assert client.config.api_key == "test-key"
        assert client.config.model == "text-embedding-ada-002"

    def test_embed_empty_text(self):
        """Empty text returns zero vector."""
        config = EmbeddingConfig(api_key="test-key", model="text-embedding-ada-002")
        client = EmbeddingClient(config)
        
        result = client.embed("")
        
        assert len(result) == 1536
        assert all(v == 0.0 for v in result)

    def test_embed_whitespace_only(self):
        """Whitespace-only text returns zero vector."""
        config = EmbeddingConfig(api_key="test-key", model="text-embedding-ada-002")
        client = EmbeddingClient(config)
        
        result = client.embed("   \n\t  ")
        
        assert len(result) == 1536
        assert all(v == 0.0 for v in result)

    @patch("requests.Session.post")
    def test_embed_success(self, mock_post):
        """Successful API call returns embedding vector."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1] * 1536, "index": 0}],
            "model": "text-embedding-ada-002",
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        config = EmbeddingConfig(api_key="test-key")
        client = EmbeddingClient(config)
        result = client.embed("Hello world")
        
        assert len(result) == 1536
        assert result[0] == 0.1
        mock_post.assert_called_once()

    @patch("requests.Session.post")
    def test_embed_api_error(self, mock_post):
        """API error raises ValueError."""
        mock_post.side_effect = Exception("API Error")
        
        config = EmbeddingConfig(api_key="test-key")
        client = EmbeddingClient(config)
        
        with pytest.raises(ValueError, match="Failed to generate embedding"):
            client.embed("Hello world")

    @patch("requests.Session.post")
    def test_embed_batch_success(self, mock_post):
        """Batch embedding returns multiple vectors."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1] * 1536, "index": 0},
                {"embedding": [0.2] * 1536, "index": 1},
            ],
            "model": "text-embedding-ada-002",
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        config = EmbeddingConfig(api_key="test-key")
        client = EmbeddingClient(config)
        result = client.embed_batch(["Hello", "World"])
        
        assert len(result) == 2
        assert len(result[0]) == 1536
        assert len(result[1]) == 1536

    def test_embed_batch_empty_list(self):
        """Empty batch returns empty list."""
        config = EmbeddingConfig(api_key="test-key")
        client = EmbeddingClient(config)
        
        result = client.embed_batch([])
        
        assert result == []

    def test_embed_batch_with_empty_texts(self):
        """Batch with empty texts returns zero vectors for empty items."""
        config = EmbeddingConfig(api_key="test-key")
        client = EmbeddingClient(config)
        
        # Mock the _get_session to avoid actual API calls
        mock_session = MagicMock()
        mock_response = MagicMock()
        # Return 2 embeddings for the 2 valid texts (indices 0 and 1 in valid_texts)
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1] * 1536, "index": 0},
                {"embedding": [0.2] * 1536, "index": 1},
            ],
        }
        mock_response.raise_for_status.return_value = None
        mock_session.post.return_value = mock_response
        client._session = mock_session
        
        result = client.embed_batch(["", "Hello", "", "World", ""])
        
        # Should have 5 results, with zero vectors at positions 0, 2, 4
        assert len(result) == 5
        assert all(v == 0.0 for v in result[0])
        assert all(v == 0.1 for v in result[1])
        assert all(v == 0.0 for v in result[2])
        assert all(v == 0.2 for v in result[3])
        assert all(v == 0.0 for v in result[4])

    @patch("requests.Session.post")
    def test_embed_batch_with_empty_texts_mocked(self, mock_post):
        """Batch with empty texts returns zero vectors for empty items (fully mocked)."""
        mock_response = MagicMock()
        # Return 2 embeddings for the 2 valid texts
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1] * 1536, "index": 0},
                {"embedding": [0.2] * 1536, "index": 1},
            ],
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        config = EmbeddingConfig(api_key="test-key")
        client = EmbeddingClient(config)
        
        result = client.embed_batch(["", "Hello", "", "World", ""])
        
        # Should have 5 results, with zero vectors at positions 0, 2, 4
        assert len(result) == 5
        assert all(v == 0.0 for v in result[0])
        assert all(v == 0.1 for v in result[1])
        assert all(v == 0.0 for v in result[2])
        assert all(v == 0.2 for v in result[3])
        assert all(v == 0.0 for v in result[4])

    def test_embed_to_json(self):
        """embed_to_json returns JSON string."""
        config = EmbeddingConfig(api_key="test-key")
        client = EmbeddingClient(config)
        
        # Mock the embed method
        client.embed = MagicMock(return_value=[0.1, 0.2, 0.3])
        
        result = client.embed_to_json("Hello")
        
        parsed = json.loads(result)
        assert parsed == [0.1, 0.2, 0.3]


class TestRuntimeEmbedAction:
    """Integration tests for embed action in Runtime."""

    def test_runtime_embed_action_mock(self, tmp_path: Path, monkeypatch):
        """Embed action uses mock when no API key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        km = KeyManager(key_path=tmp_path / "keys.pem")
        km.generate()
        contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
        contract.workflow.steps = [
            {
                "action": "embed",
                "target": "embedding",
                "args": {"text": "test embedding text", "model": "test-model"},
            }
        ]
        runtime = Runtime(contract, key_manager=km)
        result, ser = runtime.execute()
        
        assert result["status"] == "success"
        assert result["steps_completed"] == 1
        # Check that mock format was used
        step_output = runtime.replay_data[0]["output"]
        assert step_output.startswith("embedding:test-model:")

    @patch("agenlang.utils.EmbeddingClient.embed")
    def test_runtime_embed_action_real(self, mock_embed, tmp_path: Path, monkeypatch):
        """Embed action uses real API when key available."""
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key-for-test")
        
        mock_embed.return_value = [0.1] * 1536
        
        km = KeyManager(key_path=tmp_path / "keys.pem")
        km.generate()
        contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
        contract.workflow.steps = [
            {
                "action": "embed",
                "target": "embedding",
                "args": {"text": "test embedding text", "model": "text-embedding-ada-002"},
            }
        ]
        runtime = Runtime(contract, key_manager=km)
        result, ser = runtime.execute()
        
        assert result["status"] == "success"
        mock_embed.assert_called_once_with("test embedding text")
        
        # Check output is JSON format
        step_output = runtime.replay_data[0]["output"]
        parsed = json.loads(step_output)
        assert "model" in parsed
        assert "dimensions" in parsed
        assert "embedding" in parsed
        assert parsed["dimensions"] == 1536

    @patch("agenlang.utils.EmbeddingClient.embed")
    def test_runtime_embed_action_hash_format(self, mock_embed, tmp_path: Path, monkeypatch):
        """Embed action supports hash format for backward compatibility."""
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key-for-test")
        
        mock_embed.return_value = [0.1] * 1536
        
        km = KeyManager(key_path=tmp_path / "keys.pem")
        km.generate()
        contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
        contract.workflow.steps = [
            {
                "action": "embed",
                "target": "embedding",
                "args": {
                    "text": "test embedding text",
                    "format": "hash",
                },
            }
        ]
        runtime = Runtime(contract, key_manager=km)
        result, ser = runtime.execute()
        
        assert result["status"] == "success"
        # Check output is hash format
        step_output = runtime.replay_data[0]["output"]
        assert step_output.startswith("embedding:text-embedding-ada-002:")

    def test_runtime_embed_action_explicit_mock(self, tmp_path: Path, monkeypatch):
        """Embed action uses mock when explicitly requested."""
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
        
        km = KeyManager(key_path=tmp_path / "keys.pem")
        km.generate()
        contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
        contract.workflow.steps = [
            {
                "action": "embed",
                "target": "embedding",
                "args": {"text": "test", "mock": True},
            }
        ]
        runtime = Runtime(contract, key_manager=km)
        result, ser = runtime.execute()
        
        assert result["status"] == "success"
        step_output = runtime.replay_data[0]["output"]
        assert step_output.startswith("embedding:")

    @patch("agenlang.utils.EmbeddingClient.embed")
    def test_runtime_embed_action_api_failure(self, mock_embed, tmp_path: Path, monkeypatch):
        """Embed action raises on API failure."""
        monkeypatch.setenv("OPENAI_API_KEY", "fake-key-for-test")
        
        mock_embed.side_effect = ValueError("API Error")
        
        km = KeyManager(key_path=tmp_path / "keys.pem")
        km.generate()
        contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
        contract.workflow.steps = [
            {
                "action": "embed",
                "target": "embedding",
                "args": {"text": "test embedding text"},
            }
        ]
        runtime = Runtime(contract, key_manager=km)
        
        with pytest.raises(ValueError, match="Embedding generation failed"):
            runtime.execute()


@pytest.mark.integration
class TestEmbeddingIntegration:
    """Integration tests with real API (optional, requires OPENAI_API_KEY)."""

    def test_real_embedding_generation(self):
        """Test with real OpenAI API (only if OPENAI_API_KEY set)."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key or api_key == "fake-key-for-test":
            pytest.skip("OPENAI_API_KEY not set or is fake test key")
        
        config = EmbeddingConfig.from_env()
        client = EmbeddingClient(config)
        
        result = client.embed("Hello, world!")
        
        assert len(result) == 1536
        # Verify it's a valid embedding (not all zeros, reasonable magnitude)
        assert any(v != 0.0 for v in result)
        magnitude = sum(x**2 for x in result) ** 0.5
        assert 0.1 < magnitude < 10.0  # Reasonable range for normalized embeddings
