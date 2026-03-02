"""Pluggable SettlementBackend for JouleWork settlement."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class SettlementBackend(ABC):
    """Abstract settlement backend."""

    @abstractmethod
    def settle(
        self,
        joule_recipient: str,
        joules: float,
        rate: float,
        micro_payment_address: str | None = None,
    ) -> Dict[str, Any]:
        """Execute settlement.

        Returns:
            Receipt dict with status, tx_id, etc.
        """
        ...


class StubSettlementBackend(SettlementBackend):
    """Stub for testing; no real settlement."""

    def settle(
        self,
        joule_recipient: str,
        joules: float,
        rate: float,
        micro_payment_address: str | None = None,
    ) -> Dict[str, Any]:
        """Return stub receipt."""
        return {
            "status": "stub",
            "joule_recipient": joule_recipient,
            "total_joules": joules,
            "rate": rate,
            "amount_owed": joules * rate,
        }


class HeliumStubBackend(SettlementBackend):
    """Helium network stub (placeholder for Phase 6)."""

    def settle(
        self,
        joule_recipient: str,
        joules: float,
        rate: float,
        micro_payment_address: str | None = None,
    ) -> Dict[str, Any]:
        """Return Helium-style stub receipt."""
        return {
            "status": "helium_stub",
            "recipient": joule_recipient,
            "amount": joules * rate,
            "address": micro_payment_address or "helium:stub",
        }
