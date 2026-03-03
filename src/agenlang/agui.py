"""AG-UI (Agent User Interface) adapter.

Converts AgenLang SER (Structured Execution Record) to AG-UI lifecycle
events and SSE (Server-Sent Events) format for streaming UI updates.
"""

import json
from typing import Any, Dict, Iterator, List

import structlog

log = structlog.get_logger()

EVENT_RUN_STARTED = "RunStarted"
EVENT_STEP_STARTED = "StepStarted"
EVENT_STEP_FINISHED = "StepFinished"
EVENT_RUN_FINISHED = "RunFinished"
EVENT_RUN_ERROR = "RunError"


def ser_to_agui_events(ser: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert a SER dict to a list of AG-UI lifecycle events.

    Generates RunStarted, per-step StepStarted/StepFinished (from
    decision_points), and RunFinished or RunError.

    Args:
        ser: Structured Execution Record dict.

    Returns:
        Ordered list of AG-UI event dicts.
    """
    events: List[Dict[str, Any]] = []
    timestamps = ser.get("timestamps", {})

    events.append(
        {
            "type": EVENT_RUN_STARTED,
            "threadId": ser.get("execution_id", ""),
            "runId": ser.get("execution_id", ""),
            "timestamp": timestamps.get("start", ""),
        }
    )

    for idx, dp in enumerate(ser.get("decision_points", [])):
        step_id = dp.get("location", f"step_{idx}")
        events.append(
            {
                "type": EVENT_STEP_STARTED,
                "stepId": step_id,
                "stepType": dp.get("type", "unknown"),
                "timestamp": timestamps.get("start", ""),
            }
        )
        events.append(
            {
                "type": EVENT_STEP_FINISHED,
                "stepId": step_id,
                "chosen": dp.get("chosen", True),
                "rationale": dp.get("rationale", ""),
                "timestamp": timestamps.get("end", timestamps.get("start", "")),
            }
        )

    resource = ser.get("resource_usage", {})
    status = ser.get("status", "completed")

    if status == "error":
        events.append(
            {
                "type": EVENT_RUN_ERROR,
                "runId": ser.get("execution_id", ""),
                "error": ser.get("error", "Unknown error"),
                "timestamp": timestamps.get("end", ""),
            }
        )
    else:
        events.append(
            {
                "type": EVENT_RUN_FINISHED,
                "runId": ser.get("execution_id", ""),
                "joulesUsed": resource.get("joules_used", 0),
                "reputationScore": ser.get("reputation_score", 0),
                "timestamp": timestamps.get("end", ""),
            }
        )

    return events


def agui_event_to_sse(event: Dict[str, Any]) -> str:
    """Format a single AG-UI event as an SSE string.

    Args:
        event: AG-UI event dict with 'type' key.

    Returns:
        SSE-formatted string (event: type\\ndata: json\\n\\n).
    """
    event_type = event.get("type", "message")
    data = json.dumps(event, separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n"


def stream_ser_events(ser: Dict[str, Any]) -> Iterator[str]:
    """Yield SSE-formatted AG-UI events from a SER dict.

    Args:
        ser: Structured Execution Record dict.

    Yields:
        SSE-formatted strings for each lifecycle event.
    """
    for event in ser_to_agui_events(ser):
        yield agui_event_to_sse(event)
