"""Pluggable SettlementBackend for JouleWork settlement."""

from abc import ABC, abstractmethod
from typing import Any, Dict

import structlog

log = structlog.get_logger()


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
        log.debug("stub_settlement", joule_recipient=joule_recipient, joules=joules)
        return {
            "status": "stub",
            "joule_recipient": joule_recipient,
            "total_joules": joules,
            "rate": rate,
            "amount_owed": joules * rate,
        }


class HeliumBackend(SettlementBackend):
    """Helium network backend with HTTP API skeleton."""

    def __init__(
        self,
        api_url: str = "https://api.helium.io/v1/pending_transactions",
    ) -> None:
        """Initialize Helium backend.

        Args:
            api_url: Helium API endpoint. Use "stub:..." to return stub receipt.
        """
        self.api_url = api_url

    def settle(
        self,
        joule_recipient: str,
        joules: float,
        rate: float,
        micro_payment_address: str | None = None,
    ) -> Dict[str, Any]:
        """Execute settlement via Helium API or return stub receipt."""
        amount = joules * rate
        if self.api_url.startswith("stub:"):
            log.debug("helium_stub", recipient=joule_recipient, amount=amount)
            return {
                "status": "helium_stub",
                "recipient": joule_recipient,
                "amount": amount,
                "address": micro_payment_address or "helium:stub",
            }
        try:
            import requests  # type: ignore[import-untyped]

            payload = {
                "recipient": joule_recipient,
                "amount": amount,
                "address": micro_payment_address or "",
            }
            resp = requests.post(self.api_url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            log.info("helium_settlement_submitted", recipient=joule_recipient)
            return {
                "status": "submitted",
                "recipient": joule_recipient,
                "amount": amount,
                "tx_id": data.get("tx_id", ""),
            }
        except Exception as e:
            log.warning("helium_settlement_error", error=str(e))
            return {
                "status": "error",
                "recipient": joule_recipient,
                "amount": amount,
                "error": str(e),
            }


class HeliumStubBackend(HeliumBackend):
    """Backward compatibility: HeliumBackend that always returns stub receipt."""

    def __init__(self) -> None:
        super().__init__(api_url="stub:")
