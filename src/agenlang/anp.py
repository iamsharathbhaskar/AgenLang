"""ANP (Agent Network Protocol) P2P contract exchange adapter.

Provides DID derivation from KeyManager ECDSA keys, envelope signing,
verification, and peer-to-peer contract exchange over HTTP.
"""

import base64
import hashlib
import json
from typing import Any, Dict

import requests  # type: ignore[import-untyped]
import structlog

from .contract import Contract
from .keys import KeyManager

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
