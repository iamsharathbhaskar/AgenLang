"""Tests for ANP (Agent Network Protocol) P2P adapter."""

import json
from pathlib import Path
from unittest.mock import patch

from agenlang.anp import (
    create_anp_envelope,
    derive_did_from_key_manager,
    dispatch,
    exchange_contract,
    verify_anp_envelope,
)
from agenlang.contract import Contract
from agenlang.keys import KeyManager

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def _load_contract() -> Contract:
    return Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))


def test_derive_did_from_key_manager(tmp_path: Path) -> None:
    """DID is derived from KeyManager's ECDSA key."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    did = derive_did_from_key_manager(km)
    assert did.startswith("did:key:z")
    assert len(did) > 20


def test_create_anp_envelope(tmp_path: Path) -> None:
    """ANP envelope has sender_did, payload, signature."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()
    envelope = create_anp_envelope(contract, km, recipient_did="did:key:zRemote")
    assert envelope["protocol"] == "anp"
    assert envelope["sender_did"].startswith("did:key:z")
    assert envelope["recipient_did"] == "did:key:zRemote"
    assert envelope["payload"]["contract_id"] == contract.contract_id
    assert envelope["payload_hash"].startswith("sha256:")
    assert len(envelope["signature"]) > 0


def test_verify_anp_envelope(tmp_path: Path) -> None:
    """ANP envelope signature verifies correctly."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()
    envelope = create_anp_envelope(contract, km)
    assert verify_anp_envelope(envelope, km) is True


def test_verify_anp_envelope_tampering(tmp_path: Path) -> None:
    """Tampered ANP envelope fails verification."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()
    envelope = create_anp_envelope(contract, km)
    envelope["payload"]["goal"] = "TAMPERED"
    assert verify_anp_envelope(envelope, km) is False


def test_exchange_contract_success(tmp_path: Path) -> None:
    """exchange_contract POSTs envelope to peer."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()
    with patch("agenlang.anp.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"status": "accepted"}
        result = exchange_contract("https://peer.example.com/anp", contract, km)
    assert result["status"] == "accepted"


def test_dispatch_error_handling(tmp_path: Path) -> None:
    """dispatch returns error JSON on failure."""
    contract = _load_contract()
    with patch("agenlang.anp.requests.post", side_effect=Exception("refused")):
        result = dispatch(contract, "subcontract", "peer.example.com", {})
    parsed = json.loads(result)
    assert parsed["status"] == "error"
