"""The v2 extraction prompt: prompt-only, fenced-JSON output contract."""

from __future__ import annotations

from chokepoint.agent.parser import parse_event
from chokepoint.agent.prompts import (
    FEW_SHOT_V1,
    FEW_SHOT_V2,
    PROMPT_VERSION,
    SYSTEM_V1,
    build_messages,
    render_system,
)

CONTRACT = (
    "You must return ONLY valid JSON inside a ```json code block. Do not output any other text."
)


def test_v2_is_the_default_version() -> None:
    assert PROMPT_VERSION == "v2"


def test_v2_states_the_output_contract_verbatim() -> None:
    assert CONTRACT in render_system("v2")


def test_v2_no_longer_forbids_code_fences() -> None:
    system = render_system("v2")
    assert "No markdown, no code fences" not in system
    assert "Output JSON only" not in system


def test_scored_v1_prompt_is_left_untouched() -> None:
    # docs/PROMPTS.md rule: a version with recorded scores is never edited in place.
    assert "Output JSON only. No markdown, no code fences, no commentary." in SYSTEM_V1
    assert CONTRACT not in render_system("v1")


def test_schema_is_still_inlined() -> None:
    assert '"event_type"' in render_system("v2")
    assert "{schema}" not in render_system("v2")


def test_v2_few_shot_replies_demonstrate_the_fenced_format_and_still_parse() -> None:
    assert len(FEW_SHOT_V2) == len(FEW_SHOT_V1)
    for (user_v1, json_v1), (user_v2, fenced) in zip(FEW_SHOT_V1, FEW_SHOT_V2, strict=True):
        assert user_v2 == user_v1
        assert fenced.startswith("```json\n") and fenced.endswith("\n```")
        assert parse_event(fenced) == parse_event(json_v1)


def test_build_messages_uses_fenced_examples_by_default() -> None:
    messages = build_messages("Title", "Body")
    assert [m["role"] for m in messages] == ["system", "user", "assistant"] * 1 + [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert all(m["content"].startswith("```json") for m in messages[2:-1:2])
