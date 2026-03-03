"""ANP (Agent Network Protocol) P2P contract exchange adapter.

Provides DID derivation from KeyManager ECDSA keys, envelope signing,
verification, and peer-to-peer contract exchange over HTTP and WebSocket.
"""

import base64
import hashlib
import json
from typing import Any, Dict

import requests  # type: ignore[import-untyped]
import structlog

from .contract import Contract
from .keys import KeyManager
from .utils import retry_with_backoff

log = structlog.get_logger()

# Multicodec prefix for P-256 public key (0x1200)
_P256_MULTICODEC_PREFIX = b"\x12\x00"


def derive_did_from_key_manager(km: KeyManager) -> str:
    """Derive a did:key identifier from KeyManager's ECDSA P-256 public key.

    Uses multicodec (0x1200 for P-256) + base58btc (z-prefix) encoding
    per the did:key spec.

    Args:
        km: KeyManager with an existing or generated key pair.

    Returns:
        DID string like 'did:key:z...'.
    """
    pub_pem = km.get_public_key_pem()
    pub_bytes = _pem_to_raw_public_key(pub_pem)
    mc_bytes = _P256_MULTICODEC_PREFIX + pub_bytes
    encoded = _base58btc_encode(mc_bytes)
    return f"did:key:z{encoded}"


def _pem_to_raw_public_key(pem: bytes) -> bytes:
    """Extract raw uncompressed public key bytes from PEM."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        load_pem_public_key,
    )

    pub = load_pem_public_key(pem)
    assert isinstance(pub, ec.EllipticCurvePublicKey)
    return pub.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)


def _base58btc_encode(data: bytes) -> str:
    """Base58btc encode (Bitcoin alphabet)."""
    alphabet = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    num = int.from_bytes(data, "big")
    result = bytearray()
    while num > 0:
        num, rem = divmod(num, 58)
        result.append(alphabet[rem])
    for byte in data:
        if byte == 0:
            result.append(alphabet[0])
        else:
            break
    return bytes(reversed(result)).decode("ascii")


def create_anp_envelope(
    contract: Contract,
    km: KeyManager,
    recipient_did: str = "",
) -> Dict[str, Any]:
    """Wrap contract in an ANP P2P envelope with DID and signature.

    Args:
        contract: AgenLang contract to send.
        km: KeyManager for sender DID derivation and signing.
        recipient_did: Recipient's DID (optional).

    Returns:
        ANP envelope dict with sender_did, recipient_did, payload,
        payload_hash, and signature.
    """
    sender_did = derive_did_from_key_manager(km)
    payload = json.dumps(contract.model_dump(), sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload.encode()).hexdigest()
    signature = base64.b64encode(km.sign(payload.encode())).decode()

    return {
        "protocol": "anp",
        "version": "1.0",
        "sender_did": sender_did,
        "recipient_did": recipient_did,
        "payload": contract.model_dump(),
        "payload_hash": f"sha256:{payload_hash}",
        "signature": signature,
    }


def verify_anp_envelope(envelope: Dict[str, Any], km: KeyManager) -> bool:
    """Verify an ANP envelope's signature using the sender's public key.

    Args:
        envelope: ANP envelope dict with payload and signature.
        km: KeyManager that can verify with the sender's public key.

    Returns:
        True if signature is valid, False otherwise.
    """
    payload = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":"))
    sig_bytes = base64.b64decode(envelope["signature"])
    pub_pem = km.get_public_key_pem()
    return km.verify(payload.encode(), sig_bytes, pub_pem)


@retry_with_backoff(max_retries=3, base_delay=0.5, timeout=30.0)
def exchange_contract(
    url: str, contract: Contract, km: KeyManager, timeout: int = 30
) -> Dict[str, Any]:
    """POST an ANP envelope to a peer and return the response.

    Args:
        url: Peer's ANP endpoint URL.
        contract: AgenLang contract to exchange.
        km: KeyManager for signing.
        timeout: HTTP timeout in seconds.

    Returns:
        Response dict from the peer.
    """
    envelope = create_anp_envelope(contract, km)
    resp = requests.post(
        url,
        json=envelope,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    log.info("anp_exchange_complete", url=url, sender=envelope["sender_did"])
    return resp.json()


def ws_exchange_contract_sync(
    ws_url: str, contract: Contract, km: KeyManager, timeout: int = 30
) -> Dict[str, Any]:
    """Exchange contract over WebSocket (synchronous, websocket-client).

    Args:
        ws_url: Peer's WebSocket URL (ws:// or wss://).
        contract: Contract to exchange.
        km: KeyManager for signing.
        timeout: Connection timeout.

    Returns:
        Response dict from the peer.
    """
    try:
        import websocket as ws_client  # type: ignore[import-untyped]
    except ImportError:
        log.warning("websocket_client_unavailable", fallback="http")
        http_url = ws_url.replace("ws://", "http://").replace("wss://", "https://")
        return exchange_contract(http_url, contract, km, timeout=timeout)

    envelope = create_anp_envelope(contract, km)
    payload = json.dumps(envelope)
    ws = ws_client.create_connection(ws_url, timeout=timeout)
    try:
        ws.send(payload)
        response = ws.recv()
        log.info("anp_ws_exchange_complete", url=ws_url)
        return json.loads(response)
    finally:
        ws.close()


async def ws_exchange_contract_async(
    ws_url: str, contract: Contract, km: KeyManager, timeout: int = 30
) -> Dict[str, Any]:
    """Exchange contract over WebSocket (async, websockets library).

    Args:
        ws_url: Peer's WebSocket URL (ws:// or wss://).
        contract: Contract to exchange.
        km: KeyManager for signing.
        timeout: Connection timeout.

    Returns:
        Response dict from the peer.
    """
    try:
        import asyncio

        import websockets  # type: ignore[import-untyped]
    except ImportError:
        log.warning("websockets_unavailable", fallback="sync")
        return ws_exchange_contract_sync(ws_url, contract, km, timeout)

    envelope = create_anp_envelope(contract, km)
    payload = json.dumps(envelope)
    async with websockets.connect(ws_url, close_timeout=timeout) as ws:
        await ws.send(payload)
        response = await asyncio.wait_for(ws.recv(), timeout=timeout)
        log.info("anp_ws_async_exchange_complete", url=ws_url)
        return json.loads(response)


def _is_ws_url(url: str) -> bool:
    return url.startswith("ws://") or url.startswith("wss://")


class GossipNode:
    """ANP gossip node for P2P contract broadcasting over HTTP or WebSocket.

    Automatically routes to WebSocket for ws:// URLs and HTTP for http:// URLs.
    """

    def __init__(self, km: KeyManager, peers: list[str]) -> None:
        self.km = km
        self.peers = list(peers)

    def _exchange(self, peer_url: str, contract: Contract) -> Dict[str, Any]:
        """Route to WebSocket or HTTP based on URL scheme."""
        if _is_ws_url(peer_url):
            return ws_exchange_contract_sync(peer_url, contract, self.km)
        return exchange_contract(peer_url, contract, self.km)

    def broadcast_contract(self, contract: Contract) -> list[Dict[str, Any]]:
        """Send ANP envelope to all known peers (HTTP or WebSocket).

        Returns:
            List of response dicts from each peer.
        """
        results: list[Dict[str, Any]] = []
        for peer_url in self.peers:
            try:
                resp = self._exchange(peer_url, contract)
                results.append({"peer": peer_url, "status": "ok", "response": resp})
            except Exception as e:
                log.warning("gossip_broadcast_error", peer=peer_url, error=str(e))
                results.append({"peer": peer_url, "status": "error", "error": str(e)})
        return results

    def simulate_gossip(
        self, contract: Contract, rounds: int = 3
    ) -> list[Dict[str, Any]]:
        """Simulate multi-round gossip propagation.

        Each round broadcasts to known peers, then discovers new peers
        from responses and adds them for subsequent rounds.

        Returns:
            Aggregated list of all round results.
        """
        all_results: list[Dict[str, Any]] = []
        seen_peers = set(self.peers)
        for round_num in range(rounds):
            round_results = self.broadcast_contract(contract)
            all_results.extend(round_results)
            new_peers: list[str] = []
            for r in round_results:
                resp = r.get("response", {})
                if isinstance(resp, dict):
                    for p in resp.get("peers", []):
                        if p not in seen_peers:
                            new_peers.append(p)
                            seen_peers.add(p)
            self.peers.extend(new_peers)
            log.info(
                "gossip_round_complete",
                round=round_num + 1,
                responses=len(round_results),
                new_peers=len(new_peers),
            )
        return all_results


def dispatch(
    contract: Any,
    action: str,
    target: str,
    args: Dict[str, Any],
) -> str:
    """Runtime dispatch hook: exchange contract via ANP.

    Args:
        contract: The executing contract.
        action: Step action type.
        target: Peer endpoint URL (part after 'anp:').
        args: Step arguments.

    Returns:
        JSON string of the ANP response.
    """
    km = KeyManager()
    url = target if target.startswith("http") else f"https://{target}"
    try:
        result = exchange_contract(url, contract, km)
        return json.dumps(result)
    except Exception as e:
        log.error("anp_dispatch_error", target=target, error=str(e))
        return json.dumps({"status": "error", "error": str(e)})
