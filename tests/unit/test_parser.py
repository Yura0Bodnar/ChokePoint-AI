"""The ugly-JSON torture suite for ladder layers ③ + ④ (§7.4).

Every case must either parse into a valid ``DisruptionEvent`` or raise
``ValidationError`` / ``JSONDecodeError`` — never silently return a
wrong-shaped object.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from chokepoint.agent.parser import extract_json_blob, parse_event
from chokepoint.contracts import EventType

GOOD = (
    '{"event_type": "strike", "locations": [{"raw": "Port of Hamburg"}], '
    '"affected_goods": ["auto parts"], "severity": 3, "confidence": 0.9, '
    '"summary": "Dockworker strike at the Port of Hamburg."}'
)


def _assert_good(raw: str) -> None:
    event = parse_event(raw)
    assert event.event_type is EventType.STRIKE
    assert event.locations[0].raw == "Port of Hamburg"
    assert event.severity == 3
    assert event.affected_goods == ["auto parts"]


# ── should parse ──────────────────────────────────────────────────────
def test_clean_json() -> None:
    _assert_good(GOOD)


def test_markdown_fences() -> None:
    _assert_good(f"```json\n{GOOD}\n```")


def test_fences_without_language_tag() -> None:
    _assert_good(f"```\n{GOOD}\n```")


def test_prose_preamble_and_postamble() -> None:
    _assert_good(f"Sure, here's the JSON:\n{GOOD}\nLet me know if you need anything else.")


def test_trailing_commas() -> None:
    raw = (
        '{"event_type": "strike", "locations": [{"raw": "Port of Hamburg",},], '
        '"affected_goods": ["auto parts",], "severity": 3, "confidence": 0.9, '
        '"summary": "Dockworker strike at the Port of Hamburg.",}'
    )
    _assert_good(raw)


def test_single_quoted_keys_and_values() -> None:
    raw = (
        "{'event_type': 'strike', 'locations': [{'raw': 'Port of Hamburg'}], "
        "'affected_goods': ['auto parts'], 'severity': 3, 'confidence': 0.9, "
        "'summary': 'Dockworker strike at the Port of Hamburg.'}"
    )
    _assert_good(raw)


def test_python_none_literal() -> None:
    raw = GOOD.replace('{"raw": "Port of Hamburg"}', '{"raw": "Port of Hamburg", "node_id": None}')
    event = parse_event(raw)
    assert event.locations[0].node_id is None


def test_leading_whitespace_and_newlines() -> None:
    _assert_good("\n\n   " + GOOD + "\n\n")


def test_extract_json_blob_keeps_outermost_object() -> None:
    raw = 'prefix {"a": {"b": 1}} suffix }'
    assert extract_json_blob(raw) == '{"a": {"b": 1}} suffix }'


def test_extract_json_blob_no_braces_returns_stripped_input() -> None:
    assert extract_json_blob("  nothing here  ") == "nothing here"


# ── must raise ValidationError ────────────────────────────────────────
def test_out_of_range_severity_raises() -> None:
    with pytest.raises(ValidationError) as info:
        parse_event(GOOD.replace('"severity": 3', '"severity": 8'))
    assert info.value.errors()[0]["loc"] == ("severity",)


def test_null_event_type_raises() -> None:
    with pytest.raises(ValidationError) as info:
        parse_event(GOOD.replace('"event_type": "strike"', '"event_type": null'))
    assert info.value.errors()[0]["loc"] == ("event_type",)


def test_unknown_event_type_raises() -> None:
    with pytest.raises(ValidationError):
        parse_event(GOOD.replace('"event_type": "strike"', '"event_type": "riot"'))


def test_empty_locations_raises() -> None:
    with pytest.raises(ValidationError):
        parse_event(GOOD.replace('[{"raw": "Port of Hamburg"}]', "[]"))


def test_confidence_above_one_raises() -> None:
    with pytest.raises(ValidationError):
        parse_event(GOOD.replace('"confidence": 0.9', '"confidence": 1.7'))


def test_json_array_instead_of_object_raises() -> None:
    with pytest.raises(ValidationError):
        parse_event("[1, 2, 3]")


def test_truncated_output_raises() -> None:
    # json_repair closes the braces, but required fields are then missing.
    with pytest.raises(ValidationError):
        parse_event(GOOD[:60])


# ── must raise JSONDecodeError ────────────────────────────────────────
@pytest.mark.parametrize("raw", ["", "   ", "I cannot help with that.", "Sure! Here it is:"])
def test_no_json_at_all_raises_decode_error(raw: str) -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_event(raw)


# ── markdown code blocks: the regex path (the v2 prompt asks for exactly one ```json block) ──
def test_extract_json_blob_returns_only_the_fenced_object() -> None:
    assert extract_json_blob(f"```json\n{GOOD}\n```") == GOOD


def test_fenced_block_after_prose_that_contains_braces() -> None:
    # Old behaviour (first "{" .. last "}") would swallow the prose braces and corrupt the JSON.
    _assert_good(
        f"Here is the {{event}} you asked for:\n```json\n{GOOD}\n```\nHope {{this}} helps!"
    )


def test_inline_fence_on_one_line() -> None:
    _assert_good(f"Result: ```json {GOOD}``` done.")


def test_uppercase_language_tag() -> None:
    _assert_good(f"```JSON\n{GOOD}\n```")


def test_crlf_line_endings() -> None:
    _assert_good(f"```json\r\n{GOOD}\r\n```\r\n")


def test_fence_with_another_language_tag_still_yields_the_object() -> None:
    _assert_good(f"```javascript\n{GOOD}\n```")


def test_json_tagged_block_beats_an_earlier_untagged_block() -> None:
    _assert_good(f"```\n{{not: 'the answer'}}\n```\n```json\n{GOOD}\n```")


def test_first_json_block_wins_when_the_model_emits_two() -> None:
    other = GOOD.replace("Port of Hamburg", "Port of Rotterdam")
    _assert_good(f"```json\n{GOOD}\n```\n```json\n{other}\n```")


def test_unclosed_fence_from_truncated_output_still_parses() -> None:
    _assert_good(f"```json\n{GOOD}")


def test_braces_inside_string_values_survive_a_fenced_block() -> None:
    raw = GOOD.replace("Dockworker strike", "Dockworker {ver.di} strike")
    event = parse_event(f"```json\n{raw}\n```")
    assert event.summary == "Dockworker {ver.di} strike at the Port of Hamburg."


def test_fenced_block_without_any_object_raises_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_event("```json\nI cannot comply.\n```")
