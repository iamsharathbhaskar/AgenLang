"""Tests for settlement backends."""

from agenlang.settlement import HeliumStubBackend, StubSettlementBackend


def test_stub_settlement() -> None:
    """Stub settlement returns receipt."""
    backend = StubSettlementBackend()
    receipt = backend.settle("recipient", 100.0, 2.0)
    assert receipt["status"] == "stub"
    assert receipt["amount_owed"] == 200.0


def test_helium_stub() -> None:
    """Helium stub returns receipt."""
    backend = HeliumStubBackend()
    receipt = backend.settle("recipient", 50.0, 10.0, "helium:addr")
    assert receipt["status"] == "helium_stub"
    assert receipt["amount"] == 500.0
