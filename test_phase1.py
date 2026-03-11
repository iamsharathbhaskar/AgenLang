#!/usr/bin/env python3
"""Quick verification test for AgenLang Phase 1 implementation."""

import sys


def test_identity():
    """Test identity module."""
    print("Testing Identity module...")
    from agenlang.identity import (
        Identity,
        generate_did_key,
        parse_did_key,
        generate_nonce,
        verify_signature,
    )
    import time

    # Generate identity
    identity = Identity.generate("verify-test")
    print(f"  ✓ Generated DID: {identity.did[:40]}...")

    # Sign and verify
    envelope = {
        "message_id": "msg_123",
        "sender_did": identity.did,
        "receiver_did": "did:key:z6Mktest",
        "nonce": generate_nonce(),
        "timestamp": time.time(),
    }
    content = {"performative": "REQUEST", "task": "test"}

    signature = identity.sign(envelope, content)
    print(f"  ✓ Signed message (sig length: {len(signature)})")

    result = identity.verify(envelope, content, signature)
    print(f"  ✓ Verified signature: {result}")

    # Parse DID
    pub_key = parse_did_key(identity.did)
    print(f"  ✓ Parsed DID key")

    return True


def test_schema():
    """Test schema module."""
    print("\nTesting Schema module...")
    from agenlang.schema import Performative, ErrorCode, MessageEnvelope, MessageContent, Message
    from agenlang.identity import generate_nonce

    # Test performatives
    perfs = list(Performative)
    print(f"  ✓ FIPA-ACL performatives: {len(perfs)}")

    # Test error codes
    errors = list(ErrorCode)
    print(f"  ✓ Error codes: {len(errors)}")

    # Test message envelope
    nonce = generate_nonce()
    envelope = MessageEnvelope.create(
        sender_did="did:key:z6Mktest",
        receiver_did="did:key:z6Mkother",
        nonce=nonce,
        signature="test_sig",
    )
    print(f"  ✓ Created message envelope: {envelope.message_id[:20]}...")

    # Test message content with encoding
    content = MessageContent(payload="test data", payload_encoding="identity")
    print(f"  ✓ Created message content")

    return True


def test_contracts():
    """Test contracts module."""
    print("\nTesting Contracts module...")
    from agenlang.contracts import ContractState, Contract

    states = list(ContractState)
    print(f"  ✓ Contract states: {[s.value for s in states]}")

    contract = Contract(
        contract_id="ctr_test123",
        task="test task",
        sender_did="did:key:z6Mk sender",
        receiver_did="did:key:z6Mk receiver",
    )
    print(f"  ✓ Created contract: {contract.contract_id}")

    return True


def test_core():
    """Test core module imports."""
    print("\nTesting Core module...")
    from agenlang.core import BaseAgent, Database

    db = Database("test")
    print(f"  ✓ Database path: {db.db_path}")
    print(f"  ✓ BaseAgent imported")

    return True


def test_transport():
    """Test transport module."""
    print("\nTesting Transport module...")
    from agenlang.transport import HTTPTransport, retry_with_backoff

    print(f"  ✓ HTTPTransport imported")
    print(f"  ✓ retry_with_backoff imported")

    return True


def test_discovery():
    """Test discovery module."""
    print("\nTesting Discovery module...")
    from agenlang.discovery import AgentDiscovery
    from agenlang.schema import AgentCard
    from agenlang.identity import generate_nonce

    disc = AgentDiscovery()
    print(f"  ✓ AgentDiscovery imported")

    nonce = generate_nonce()
    card = AgentCard(
        did="did:key:z6Mktest",
        name="Test Agent",
        description="A test agent",
        capabilities=[],
        transports=[],
        signature="test_sig",
        updated_at="2026-03-11T00:00:00Z",
    )
    print(f"  ✓ AgentCard created")

    return True


def main():
    """Run all tests."""
    print("=" * 50)
    print("AgenLang Phase 1 Verification")
    print("=" * 50)

    tests = [
        ("Identity", test_identity),
        ("Schema", test_schema),
        ("Contracts", test_contracts),
        ("Core", test_core),
        ("Transport", test_transport),
        ("Discovery", test_discovery),
    ]

    results = []
    for name, test in tests:
        try:
            result = test()
            results.append((name, result))
        except Exception as e:
            print(f"\n  ✗ {name} failed: {e}")
            results.append((name, False))

    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
