"""Tests for W3C DID adapter."""

from pathlib import Path
from unittest.mock import patch

from agenlang.keys import KeyManager
from agenlang.w3c import (
    create_did_document,
    generate_did_web,
    resolve_did_web,
    verify_with_did,
)


def test_generate_did_web_simple() -> None:
    """did:web with domain only."""
    did = generate_did_web("example.com")
    assert did == "did:web:example.com"


def test_generate_did_web_with_path() -> None:
    """did:web with path uses colons."""
    did = generate_did_web("example.com", "agents/alice")
    assert did == "did:web:example.com:agents:alice"


def test_create_did_document(tmp_path: Path) -> None:
    """DID Document has required W3C fields."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    did = "did:web:example.com"
    doc = create_did_document(did, km)
    assert doc["id"] == did
    assert "@context" in doc
    assert len(doc["verificationMethod"]) == 1
    vm = doc["verificationMethod"][0]
    assert vm["type"] == "JsonWebKey2020"
    assert vm["publicKeyJwk"]["kty"] == "EC"
    assert vm["publicKeyJwk"]["crv"] == "P-256"
    assert did + "#key-1" in doc["authentication"]
    assert did + "#key-1" in doc["assertionMethod"]


def test_verify_with_did_document(tmp_path: Path) -> None:
    """Signature verifies against DID Document public key."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    did = "did:web:example.com"
    doc = create_did_document(did, km)
    data = b"test data to sign"
    signature = km.sign(data)
    assert verify_with_did(doc, data, signature) is True


def test_verify_with_did_document_tampering(tmp_path: Path) -> None:
    """Tampered data fails verification."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    doc = create_did_document("did:web:example.com", km)
    signature = km.sign(b"original data")
    assert verify_with_did(doc, b"tampered data", signature) is False


def test_verify_with_empty_methods() -> None:
    """Empty verificationMethod returns False."""
    assert verify_with_did({"verificationMethod": []}, b"data", b"sig") is False


def test_resolve_did_web_invalid() -> None:
    """Non-did:web raises ValueError."""
    import pytest

    with pytest.raises(ValueError, match="Not a did:web"):
        resolve_did_web("did:key:z123")


def test_resolve_did_web_success() -> None:
    """resolve_did_web fetches from well-known URL."""
    with patch("agenlang.w3c.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {"id": "did:web:example.com"}
        doc = resolve_did_web("did:web:example.com")
    assert doc["id"] == "did:web:example.com"
    mock_get.assert_called_once()
    url = mock_get.call_args[0][0]
    assert url == "https://example.com/.well-known/did.json"


def test_resolve_did_web_with_path() -> None:
    """resolve_did_web with path resolves to correct URL."""
    with patch("agenlang.w3c.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {
            "id": "did:web:example.com:users:bob"
        }
        resolve_did_web("did:web:example.com:users:bob")
    url = mock_get.call_args[0][0]
    assert url == "https://example.com/users/bob/did.json"
