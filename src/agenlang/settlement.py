# Copyright 2024 AgenLang Contributors
# SPDX-License-Identifier: Apache-2.0

"""Signed double-entry ledger for JouleWork settlement."""

from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog
from pydantic import BaseModel

from .keys import KeyManager

log = structlog.get_logger()


class LedgerEntry(BaseModel):
    """A single debit or credit in the settlement ledger."""

    entry_type: str  # "debit" or "credit"
    amount_joules: float
    recipient: str
    timestamp: str
    signature: str = ""


class SignedLedger:
    """Append-only ledger of signed settlement entries."""

    def __init__(self) -> None:
        self._entries: List[LedgerEntry] = []

    def append_entry(
        self,
        entry_type: str,
        amount_joules: float,
        recipient: str,
        km: KeyManager,
    ) -> LedgerEntry:
        """Create a signed ledger entry and append it.

        Args:
            entry_type: "debit" or "credit".
            amount_joules: Joule cost of the step.
            recipient: Who receives the joules.
            km: KeyManager used to sign the entry.

        Returns:
            The signed LedgerEntry.
        """
        ts = datetime.now(timezone.utc).isoformat() + "Z"
        payload = f"{entry_type}|{amount_joules}|{recipient}|{ts}"
        signature = km.sign(payload.encode("utf-8")).hex()
        entry = LedgerEntry(
            entry_type=entry_type,
            amount_joules=amount_joules,
            recipient=recipient,
            timestamp=ts,
            signature=signature,
        )
        self._entries.append(entry)
        log.debug(
            "ledger_entry_appended",
            entry_type=entry_type,
            amount=amount_joules,
            recipient=recipient,
        )
        return entry

    def verify_all(self, km: KeyManager) -> bool:
        """Verify every entry signature.

        Returns:
            True if all signatures are valid.
        """
        pub_pem = km.get_public_key_pem()
        for entry in self._entries:
            payload = (
                f"{entry.entry_type}|{entry.amount_joules}"
                f"|{entry.recipient}|{entry.timestamp}"
            )
            if not km.verify(
                payload.encode("utf-8"),
                bytes.fromhex(entry.signature),
                pub_pem,
            ):
                log.warning("ledger_verify_failed", entry=entry.model_dump())
                return False
        return True

    def to_dict(self) -> List[Dict[str, Any]]:
        """Serialize ledger for SER embedding."""
        return [e.model_dump() for e in self._entries]

    @property
    def entries(self) -> List[LedgerEntry]:
        """Read-only access to entries."""
        return list(self._entries)
