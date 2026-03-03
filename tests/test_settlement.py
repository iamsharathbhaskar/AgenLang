# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for signed ledger settlement."""

from pathlib import Path

from agenlang.keys import KeyManager
from agenlang.settlement import LedgerEntry, SignedLedger


def test_ledger_entry_model() -> None:
    """LedgerEntry stores all required fields."""
    entry = LedgerEntry(
        entry_type="debit",
        amount_joules=150.0,
        recipient="agent-001",
        timestamp="2026-01-01T00:00:00Z",
        signature="abcd",
    )
    assert entry.entry_type == "debit"
    assert entry.amount_joules == 150.0
    assert entry.recipient == "agent-001"


def test_signed_ledger_append_and_verify(tmp_path: Path) -> None:
    """Appending entries signs them and verify_all succeeds."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    ledger = SignedLedger()
    ledger.append_entry("debit", 100.0, "recipient-a", km)
    ledger.append_entry("credit", 50.0, "recipient-b", km)

    assert len(ledger.entries) == 2
    assert ledger.entries[0].entry_type == "debit"
    assert ledger.entries[1].entry_type == "credit"
    assert ledger.entries[0].signature != ""
    assert ledger.verify_all(km)


def test_signed_ledger_tamper_detection(tmp_path: Path) -> None:
    """Tampered entry fails verification."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    ledger = SignedLedger()
    ledger.append_entry("debit", 100.0, "recipient-a", km)
    ledger._entries[0].amount_joules = 9999.0
    assert not ledger.verify_all(km)


def test_signed_ledger_to_dict(tmp_path: Path) -> None:
    """to_dict returns serializable list."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    ledger = SignedLedger()
    ledger.append_entry("debit", 200.0, "recipient-x", km)
    data = ledger.to_dict()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["entry_type"] == "debit"
    assert data[0]["amount_joules"] == 200.0
    assert data[0]["signature"] != ""


def test_signed_ledger_empty_verify(tmp_path: Path) -> None:
    """Empty ledger verifies successfully."""
    km = KeyManager(key_path=tmp_path / "keys.pem")
    km.generate()
    ledger = SignedLedger()
    assert ledger.verify_all(km)
    assert ledger.to_dict() == []
