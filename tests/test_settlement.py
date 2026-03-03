"""Tests for settlement backends."""

from unittest.mock import patch

from agenlang.settlement import HeliumBackend, HeliumStubBackend, StubSettlementBackend


def test_stub_settlement() -> None:
    """Stub settlement returns receipt."""
    backend = StubSettlementBackend()
    receipt = backend.settle("recipient", 100.0, 2.0)
    assert receipt["status"] == "stub"
    assert receipt["amount_owed"] == 200.0


def test_helium_stub() -> None:
    """Helium stub returns receipt."""
    backend = HeliumStubBackend()
    receipt = backend.settle("recipient", 50.0, 10.0, "helium:addr")
    assert receipt["status"] == "helium_stub"
    assert receipt["amount"] == 500.0


def test_helium_backend_stub_mode() -> None:
    """HeliumBackend with stub api_url returns stub receipt."""
    backend = HeliumBackend(api_url="stub:")
    receipt = backend.settle("recipient", 50.0, 10.0, "helium:addr")
    assert receipt["status"] == "helium_stub"
    assert receipt["amount"] == 500.0
    assert receipt["address"] == "helium:addr"


def test_helium_backend_error_path() -> None:
    """HeliumBackend returns error status when HTTP fails."""
    backend = HeliumBackend(api_url="https://api.helium.io/v1/pending_transactions")

    with patch("requests.post") as mock_post:
        mock_post.side_effect = Exception("Connection refused")
        receipt = backend.settle("recipient", 50.0, 10.0)

    assert receipt["status"] == "error"
    assert receipt["amount"] == 500.0
    assert "error" in receipt


def test_helium_backend_success_path() -> None:
    """HeliumBackend returns submitted status when HTTP succeeds."""
    backend = HeliumBackend(api_url="https://api.helium.io/v1/pending_transactions")

    with patch("requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"tx_id": "abc123"}
        receipt = backend.settle("recipient", 50.0, 10.0)

    assert receipt["status"] == "submitted"
    assert receipt["amount"] == 500.0
    assert receipt["tx_id"] == "abc123"
