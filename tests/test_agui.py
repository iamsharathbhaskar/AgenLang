"""Tests for AG-UI (Agent User Interface) adapter."""

from agenlang.agui import agui_event_to_sse, ser_to_agui_events, stream_ser_events


def _sample_ser() -> dict:
    return {
        "execution_id": "urn:agenlang:exec:test123",
        "timestamps": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T00:01:00Z"},
        "decision_points": [
            {
                "type": "probabilistic_choice",
                "location": "step_0",
                "rationale": "weight=0.7",
                "chosen": True,
            },
            {
                "type": "probabilistic_choice",
                "location": "step_1",
                "rationale": "weight=0.3",
                "chosen": False,
            },
        ],
        "resource_usage": {"joules_used": 150.0, "usd_cost": 0.015},
        "reputation_score": 0.9,
    }


def test_ser_to_agui_events_lifecycle() -> None:
    """SER produces RunStarted, StepStarted/Finished, RunFinished."""
    events = ser_to_agui_events(_sample_ser())
    types = [e["type"] for e in events]
    assert types[0] == "RunStarted"
    assert types[-1] == "RunFinished"
    assert types.count("StepStarted") == 2
    assert types.count("StepFinished") == 2


def test_ser_to_agui_events_run_id() -> None:
    """RunStarted and RunFinished carry the execution_id."""
    events = ser_to_agui_events(_sample_ser())
    assert events[0]["runId"] == "urn:agenlang:exec:test123"
    assert events[-1]["runId"] == "urn:agenlang:exec:test123"


def test_ser_error_event() -> None:
    """Error SER produces RunError event."""
    ser = _sample_ser()
    ser["status"] = "error"
    ser["error"] = "budget exceeded"
    events = ser_to_agui_events(ser)
    assert events[-1]["type"] == "RunError"
    assert events[-1]["error"] == "budget exceeded"


def test_agui_event_to_sse_format() -> None:
    """SSE format has event: and data: lines."""
    event = {"type": "RunStarted", "runId": "test"}
    sse = agui_event_to_sse(event)
    assert sse.startswith("event: RunStarted\n")
    assert "data: " in sse
    assert sse.endswith("\n\n")


def test_stream_ser_events() -> None:
    """stream_ser_events yields SSE strings."""
    events = list(stream_ser_events(_sample_ser()))
    assert len(events) > 0
    assert all(e.startswith("event: ") for e in events)
