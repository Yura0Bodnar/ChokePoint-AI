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

#: A complete fenced block tagged ``json`` — what the v2 prompt asks the model to emit.
#: Matches anywhere in the reply (after prose, inline, CRLF), lazily up to the first closing fence.
_JSON_FENCED_BLOCK = re.compile(r"```[ \t]*json[ \t]*\r?\n?(.*?)```", re.DOTALL | re.IGNORECASE)
#: Any complete fenced block (untagged, or another language tag) — a lenient second choice.
_ANY_FENCED_BLOCK = re.compile(r"```[ \t]*[\w+-]*[ \t]*\r?\n?(.*?)```", re.DOTALL)
#: Stray fence lines left over when a block is never closed (e.g. output cut off at max_tokens).
_STRAY_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def _fenced_payload(raw: str) -> str | None:
    """The text inside the first markdown code block that holds a JSON object, if any."""
    match = _JSON_FENCED_BLOCK.search(raw)
    if match:
        return match.group(1)
    for match in _ANY_FENCED_BLOCK.finditer(raw):
        if "{" in match.group(1):
            return match.group(1)
    return None


def extract_json_blob(raw: str) -> str:
    """Pull the JSON text out of a model reply; keep the outermost object.

    1. A markdown block (```` ```json … ``` ````, or any fence holding a ``{``) is matched with
       a regex and only its contents are kept, so prose before/after — even prose that itself
       contains braces — cannot leak into the JSON.
    2. Otherwise stray fence markers are stripped (covers an unclosed, truncated block).
    3. Either way the result is trimmed to the outermost ``{ … }``.
    """
    fenced = _fenced_payload(raw)
    s = (fenced if fenced is not None else _STRAY_FENCE.sub("", raw)).strip()
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
