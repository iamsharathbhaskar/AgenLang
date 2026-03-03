"""Pluggable SettlementBackend for JouleWork settlement."""

import os
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
    """Helium network backend with authenticated API.

    Requires HELIUM_API_KEY env var for real transactions.
    Use api_url="stub:" for testing without network.
    """

    def __init__(
        self,
        api_url: str = "https://api.helium.io/v1/pending_transactions",
    ) -> None:
        self.api_url = api_url
        self._stub_mode = api_url.startswith("stub:")
        if not self._stub_mode:
            self.api_key = os.environ.get("HELIUM_API_KEY", "")
            if not self.api_key:
                raise ValueError(
                    "HELIUM_API_KEY env var required for real Helium settlement"
                )
        else:
            self.api_key = ""

    def settle(
        self,
        joule_recipient: str,
        joules: float,
        rate: float,
        micro_payment_address: str | None = None,
    ) -> Dict[str, Any]:
        """Execute settlement via Helium API or return stub receipt."""
        amount = joules * rate
        if self._stub_mode:
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
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            resp = requests.post(
                self.api_url, json=payload, headers=headers, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            tx_id = data.get("hash", data.get("tx_id", ""))
            log.info(
                "helium_settlement_submitted",
                recipient=joule_recipient,
                tx_id=tx_id,
            )
            return {
                "status": "submitted",
                "recipient": joule_recipient,
                "amount": amount,
                "tx_id": tx_id,
                "block_height": data.get("height", None),
                "type": data.get("type", "payment_v2"),
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
