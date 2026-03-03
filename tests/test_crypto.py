"""Tests for crypto: ECDSA signing, KeyManager, SER verification, tampering, replay."""

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from agenlang.contract import Contract
from agenlang.keys import KeyManager

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def test_key_manager_generate_and_load(tmp_path: Path) -> None:
    km = KeyManager(key_path=tmp_path / "keys.pem")
    key1 = km.generate()
    assert key1 is not None
    key2 = km.load()
    assert key2 is not None


def test_key_manager_sign_verify(tmp_path: Path) -> None:
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    data = b"test payload"
    sig = km.sign(data)
    pubkey = km.get_public_key_pem()
    assert km.verify(data, sig, pubkey) is True


def test_key_manager_verify_tampering_fails(tmp_path: Path) -> None:
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    data = b"original"
    sig = km.sign(data)
    pubkey = km.get_public_key_pem()
    assert km.verify(b"tampered", sig, pubkey) is False


def test_contract_sign_verify(tmp_path: Path) -> None:
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.sign(km)
    assert contract.issuer.proof is not None
    assert contract.verify_signature() is True


def test_contract_verify_tampering_fails(tmp_path: Path) -> None:
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.sign(km)
    contract.goal = "tampered goal"
    assert contract.verify_signature() is False


def test_ser_key_persistent(tmp_path: Path) -> None:
    km1 = KeyManager(key_path=tmp_path / "keys.pem")
    key1 = km1.get_ser_key()
    km2 = KeyManager(key_path=tmp_path / "keys.pem")
    key2 = km2.get_ser_key()
    assert key1 == key2
    assert len(key1) == 32


def test_key_rotation(tmp_path: Path) -> None:
    """Key rotation: new key invalidates old signatures."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    contract = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract.sign(km)
    assert contract.verify_signature() is True
    km.generate()  # rotate key
    contract2 = Contract.from_file(str(EXAMPLES_DIR / "amazo-flight-booking.json"))
    contract2.sign(km)
    assert contract2.verify_signature() is True


def test_verify_replay_hmac() -> None:
    import secrets

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hmac as hmac_mod
    from cryptography.hazmat.primitives.hashes import SHA256

    key = secrets.token_bytes(32)
    content = b"replay content"
    h = hmac_mod.HMAC(key, SHA256(), backend=default_backend())
    h.update(content)
    hmac_val = h.finalize()
    assert KeyManager.verify_replay_hmac(content, hmac_val, key) is True
    assert KeyManager.verify_replay_hmac(content, b"x" * 32, key) is False


@given(data=st.binary(min_size=1, max_size=500))
def test_sign_verify_hypothesis(data: bytes, tmp_path_factory) -> None:
    """Hypothesis: sign/verify roundtrip for arbitrary data."""
    tmp = tmp_path_factory.mktemp("keys")
    km = KeyManager(key_path=tmp / "keys.pem")
    km.generate()
    sig = km.sign(data)
    pubkey = km.get_public_key_pem()
    assert km.verify(data, sig, pubkey) is True


@given(tamper=st.binary(min_size=1, max_size=100))
def test_tampered_data_fails_hypothesis(tamper: bytes, tmp_path_factory) -> None:
    """Hypothesis: tampered data always fails verification."""
    tmp = tmp_path_factory.mktemp("keys")
    km = KeyManager(key_path=tmp / "keys.pem")
    km.generate()
    original = b"original data for signing"
    sig = km.sign(original)
    pubkey = km.get_public_key_pem()
    if tamper != original:
        assert km.verify(tamper, sig, pubkey) is False
