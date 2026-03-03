"""W3C DID (Decentralized Identifier) adapter.

Supports did:web and did:key methods. Generates DID Documents from
KeyManager ECDSA P-256 keys, resolves did:web documents, and
verifies signatures using DID Document public keys.
"""

import base64
from typing import Any, Dict

import requests  # type: ignore[import-untyped]
import structlog
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from .keys import KeyManager
from .utils import retry_with_backoff

log = structlog.get_logger()


def generate_did_web(domain: str, path: str = "") -> str:
    """Generate a did:web identifier.

    Args:
        domain: Domain name (e.g., 'example.com').
        path: Optional path (e.g., 'agents/alice'). Colons replace slashes.

    Returns:
        DID string like 'did:web:example.com:agents:alice'.
    """
    did = f"did:web:{domain}"
    if path:
        did += ":" + path.replace("/", ":")
    return did


def create_did_document(did: str, km: KeyManager) -> Dict[str, Any]:
    """Build a W3C DID Document with ECDSA P-256 verification method.

    Args:
        did: The DID identifier (did:web or did:key).
        km: KeyManager to extract the public key from.

    Returns:
        W3C DID Document dict conforming to DID Core spec.
    """
    pub_pem = km.get_public_key_pem()
    pub_key = load_pem_public_key(pub_pem)
    assert isinstance(pub_key, ec.EllipticCurvePublicKey)

    pub_jwk = _ec_public_key_to_jwk(pub_key)
    verification_id = f"{did}#key-1"

    return {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/jws-2020/v1",
        ],
        "id": did,
        "verificationMethod": [
            {
                "id": verification_id,
                "type": "JsonWebKey2020",
                "controller": did,
                "publicKeyJwk": pub_jwk,
            }
        ],
        "authentication": [verification_id],
        "assertionMethod": [verification_id],
        "service": [
            {
                "id": f"{did}#agenlang",
                "type": "AgenLangEndpoint",
                "serviceEndpoint": f"https://{_did_to_domain(did)}/agenlang",
            }
        ],
    }


def _ec_public_key_to_jwk(pub_key: ec.EllipticCurvePublicKey) -> Dict[str, str]:
    """Convert an EC public key to JWK format."""
    numbers = pub_key.public_numbers()
    x_bytes = numbers.x.to_bytes(32, "big")
    y_bytes = numbers.y.to_bytes(32, "big")
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": base64.urlsafe_b64encode(x_bytes).rstrip(b"=").decode(),
        "y": base64.urlsafe_b64encode(y_bytes).rstrip(b"=").decode(),
    }


def _did_to_domain(did: str) -> str:
    """Extract domain from a DID string."""
    parts = did.split(":")
    if len(parts) >= 3:
        return parts[2]
    return "localhost"


@retry_with_backoff(max_retries=3, base_delay=0.5, timeout=10.0)
def resolve_did_web(did: str, timeout: int = 10) -> Dict[str, Any]:
    """Fetch and parse a DID Document from a did:web URL.

    Resolves did:web:example.com to https://example.com/.well-known/did.json
    and did:web:example.com:path:to to https://example.com/path/to/did.json.

    Args:
        did: A did:web identifier.
        timeout: HTTP timeout in seconds.

    Returns:
        Parsed DID Document dict.

    Raises:
        ValueError: If the DID is not a valid did:web.
    """
    if not did.startswith("did:web:"):
        raise ValueError(f"Not a did:web identifier: {did}")

    parts = did.replace("did:web:", "").split(":")
    domain = parts[0]
    if len(parts) > 1:
        path = "/".join(parts[1:])
        url = f"https://{domain}/{path}/did.json"
    else:
        url = f"https://{domain}/.well-known/did.json"

    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    log.info("did_web_resolved", did=did, url=url)
    return resp.json()


def verify_with_did(
    did_doc: Dict[str, Any],
    data: bytes,
    signature: bytes,
) -> bool:
    """Verify a signature using the public key from a DID Document.

    Extracts the first verificationMethod's publicKeyJwk and verifies
    the ECDSA-SHA256 signature.

    Args:
        did_doc: W3C DID Document dict.
        data: The signed data bytes.
        signature: The DER-encoded ECDSA signature.

    Returns:
        True if signature is valid, False otherwise.
    """
    methods = did_doc.get("verificationMethod", [])
    if not methods:
        return False

    jwk = methods[0].get("publicKeyJwk", {})
    if not jwk or jwk.get("kty") != "EC":
        return False

    try:
        pub_key = _jwk_to_ec_public_key(jwk)
        from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
        from cryptography.hazmat.primitives.hashes import SHA256

        pub_key.verify(signature, data, ECDSA(SHA256()))
        return True
    except Exception:
        return False


def _jwk_to_ec_public_key(jwk: Dict[str, str]) -> ec.EllipticCurvePublicKey:
    """Convert JWK to EC public key."""
    x_bytes = base64.urlsafe_b64decode(jwk["x"] + "==")
    y_bytes = base64.urlsafe_b64decode(jwk["y"] + "==")
    x = int.from_bytes(x_bytes, "big")
    y = int.from_bytes(y_bytes, "big")
    pub_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
    return pub_numbers.public_key()
