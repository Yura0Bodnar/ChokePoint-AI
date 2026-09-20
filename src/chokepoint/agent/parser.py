"""Ladder layers ③ (hygiene) and ④ (json-repair) + Pydantic validation.

``parse_event`` either returns a valid ``DisruptionEvent`` or raises
``pydantic.ValidationError`` / ``json.JSONDecodeError``. It never returns a
wrong-shaped object, and it never retries — the caller
(``ExtractionAgent``) owns the retry policy. See ARCHITECTURE_AND_PLAN.md §7.4.
"""

from __future__ import annotations

import json
import re
from typing import Any

from json_repair import repair_json

from chokepoint.contracts import DisruptionEvent

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def extract_json_blob(raw: str) -> str:
    """Strip fences and any surrounding prose; keep the outermost object."""
    s = _FENCE.sub("", raw).strip()
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


def load_json_lenient(blob: str) -> Any:
    """``json.loads`` first; on failure, ``json_repair`` then ``json.loads`` again.

    Raises ``json.JSONDecodeError`` if even the repaired text is not JSON
    (json_repair returns ``""`` for hopeless input, which ``json.loads``
    rejects — exactly the signal we want).
    """
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        repaired = repair_json(blob)
        return json.loads(repaired)


def parse_event(raw: str) -> DisruptionEvent:
    """Raises ValidationError/JSONDecodeError — caller owns the retry policy."""
    blob = extract_json_blob(raw)
    data = load_json_lenient(blob)
    return DisruptionEvent.model_validate(data)


__all__ = ["extract_json_blob", "load_json_lenient", "parse_event"]
