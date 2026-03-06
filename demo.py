#!/usr/bin/env python3
"""
AgenLang Demo: Two agents communicating via A2A protocol.

This demo shows:
1. Creating agent identities
2. Creating a contract
3. Starting an A2A server
4. Sending a contract between agents
"""

import json
import tempfile
import time
from pathlib import Path

from agenlang.contract import Contract
from agenlang.keys import KeyManager
from agenlang.a2a import dispatch, contract_to_a2a_payload


def create_sample_contract(issuer_did: str, receiver_did: str) -> Contract:
    """Create a sample flight booking contract."""
    contract_data = {
        "agenlang_version": "1.0",
        "contract_id": "urn:agenlang:exec:" + "a" * 32,
        "issuer": {"agent_id": issuer_did, "pubkey": "test-pubkey"},
        "receiver": {"agent_id": receiver_did},
        "goal": "Demo: Web search for AI news",
        "intent_anchor": {"hash": "sha256:demo-intent"},
        "constraints": {"joule_budget": 1000},
        "workflow": {
            "type": "sequence",
            "steps": [
                {"action": "tool", "target": "web_search", "args": {"query": "latest AI news 2025"}},
            ]
        },
        "memory_contract": {"handoff_keys": [], "ttl": "1h", "purge_on_complete": True},
        "settlement": {"joule_recipient": "demo-agent", "rate": 1.0},
        "capability_attestations": [
            {"capability": "net:read", "proof": "demo-proof"},
        ],
    }
    return Contract.from_dict(contract_data)


def main():
    print("=" * 60)
    print("AgenLang A2A Communication Demo")
    print("=" * 60)

    # Create temporary directories for two agents
    with tempfile.TemporaryDirectory() as agent1_dir, tempfile.TemporaryDirectory() as agent2_dir:
        # Agent 1: The requester
        print("\n1. Creating Agent 1 (Requester)...")
        km1 = KeyManager(key_path=Path(agent1_dir) / "keys.pem")
        km1.generate()
        did1 = km1.derive_did_key()
        print(f"   DID: {did1}")

        # Agent 2: The executor (receiver)
        print("\n2. Creating Agent 2 (Executor)...")
        km2 = KeyManager(key_path=Path(agent2_dir) / "keys.pem")
        km2.generate()
        did2 = km2.derive_did_key()
        print(f"   DID: {did2}")

        # Create contract from Agent 1 to Agent 2
        print("\n3. Creating contract...")
        contract = create_sample_contract(did1, did2)
        print(f"   Goal: {contract.goal}")
        print(f"   Budget: {contract.constraints.joule_budget} Joules")

        # Sign the contract
        print("\n4. Signing contract with Agent 1's key...")
        contract.sign(km1)
        print(f"   Signature verified: {contract.verify_signature()}")

        # Show A2A payload
        print("\n5. A2A Payload (what gets sent over the wire):")
        payload = contract_to_a2a_payload(contract)
        print(json.dumps(payload, indent=2)[:500] + "...")

        print("\n" + "=" * 60)
        print("To test actual communication:")
        print("=" * 60)
        print("\nTerminal 1 - Start the A2A server:")
        print("  agenlang server --port 8000")
        print("\nTerminal 2 - Send a contract:")
        print("  agenlang send examples/amazo-flight-booking.json --endpoint http://localhost:8000/a2a")
        print("\nOr programmatically:")
        print("  from agenlang.a2a import dispatch")
        print("  result = dispatch(contract, 'tool', 'execute', {}, endpoint_url='http://localhost:8000/a2a')")
        print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
