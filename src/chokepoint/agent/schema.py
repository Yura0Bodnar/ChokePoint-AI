"""JSON Schema handed to the model via ``response_format`` (ladder layer ①).

Derived from the frozen contract at import time — one source of truth, zero
schema drift. Never hand-write a parallel schema here.
"""

from __future__ import annotations

from typing import Any

from chokepoint.contracts import DisruptionEvent

DISRUPTION_EVENT_JSON_SCHEMA: dict[str, Any] = {
    "name": "disruption_event",
    "schema": DisruptionEvent.model_json_schema(),
    "strict": True,
}

__all__ = ["DISRUPTION_EVENT_JSON_SCHEMA"]
