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


def test_gossip_node_broadcast(tmp_path: Path) -> None:
    """GossipNode broadcasts to all peers."""
    from agenlang.anp import GossipNode

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()
    node = GossipNode(km, ["https://peer1.example.com", "https://peer2.example.com"])

    with patch("agenlang.anp.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"status": "accepted"}
        results = node.broadcast_contract(contract)

    assert len(results) == 2
    assert all(r["status"] == "ok" for r in results)


def test_gossip_node_broadcast_with_error(tmp_path: Path) -> None:
    """GossipNode handles peer errors gracefully."""
    from agenlang.anp import GossipNode

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()
    node = GossipNode(km, ["https://bad-peer.example.com"])

    with patch("agenlang.anp.requests.post", side_effect=Exception("down")):
        results = node.broadcast_contract(contract)

    assert len(results) == 1
    assert results[0]["status"] == "error"


def test_simulate_gossip(tmp_path: Path) -> None:
    """simulate_gossip runs multiple rounds and discovers new peers."""
    from agenlang.anp import GossipNode

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()
    node = GossipNode(km, ["https://peer1.example.com"])

    with patch("agenlang.anp.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {
            "status": "accepted",
            "peers": ["https://new-peer.example.com"],
        }
        results = node.simulate_gossip(contract, rounds=2)

    assert len(results) >= 2
    assert "https://new-peer.example.com" in node.peers


def test_ws_exchange_contract_sync_fallback(tmp_path: Path) -> None:
    """ws_exchange_contract_sync falls back to HTTP when websocket-client not available."""
    from agenlang.anp import ws_exchange_contract_sync

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()

    with (
        patch.dict("sys.modules", {"websocket": None}),
        patch("agenlang.anp.requests.post") as mock_post,
    ):
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"status": "accepted"}
        result = ws_exchange_contract_sync("ws://peer.example.com/anp", contract, km)
    assert result["status"] == "accepted"


def test_ws_exchange_contract_sync_success(tmp_path: Path) -> None:
    """ws_exchange_contract_sync sends via WebSocket when available."""
    from unittest.mock import MagicMock

    from agenlang.anp import ws_exchange_contract_sync

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()

    mock_ws_module = MagicMock()
    mock_conn = MagicMock()
    mock_ws_module.create_connection.return_value = mock_conn
    mock_conn.recv.return_value = json.dumps({"status": "ws_accepted"})

    with patch.dict("sys.modules", {"websocket": mock_ws_module}):
        result = ws_exchange_contract_sync("ws://peer.example.com/anp", contract, km)
    assert result["status"] == "ws_accepted"
    mock_conn.send.assert_called_once()
    mock_conn.close.assert_called_once()


def test_gossip_node_ws_routing(tmp_path: Path) -> None:
    """GossipNode routes ws:// URLs to WebSocket exchange."""
    from unittest.mock import MagicMock

    from agenlang.anp import GossipNode

    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = _load_contract()

    mock_ws_module = MagicMock()
    mock_conn = MagicMock()
    mock_ws_module.create_connection.return_value = mock_conn
    mock_conn.recv.return_value = json.dumps({"status": "ws_ok"})

    node = GossipNode(
        km, ["ws://peer1.example.com/anp", "https://peer2.example.com/anp"]
    )

    with (
        patch.dict("sys.modules", {"websocket": mock_ws_module}),
        patch("agenlang.anp.requests.post") as mock_http,
    ):
        mock_http.return_value.raise_for_status = lambda: None
        mock_http.return_value.json.return_value = {"status": "http_ok"}
        results = node.broadcast_contract(contract)

    assert len(results) == 2
    ws_result = next(r for r in results if r["peer"].startswith("ws://"))
    http_result = next(r for r in results if r["peer"].startswith("https://"))
    assert ws_result["status"] == "ok"
    assert http_result["status"] == "ok"
