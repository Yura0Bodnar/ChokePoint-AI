"""Fixture-replay provider (ARCHITECTURE_AND_PLAN.md §7.5).

**CI never calls a real LLM.** This provider replays raw strings recorded
under ``tests/fixtures/llm_responses/`` so the whole ladder — hygiene,
repair, validation, retry, fallback — is exercised deterministically and
offline. It is also the demo safety net behind ``LLM_PROVIDER=stub``.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from chokepoint.agent.providers.base import Message

DEFAULT_FIXTURE = "strike_hamburg.txt"

#: Inline copy of ``strike_hamburg.txt`` so the stub also works where the tests
#: directory is absent (Docker image, ``DEMO_MODE``).
DEFAULT_RESPONSE = (
    '{"event_type": "strike", "locations": [{"raw": "Port of Hamburg", "node_id": null, '
    '"country_iso2": "DE"}], "affected_goods": ["automotive parts", "consumer electronics"], '
    '"severity": 3, "estimated_duration_days": 2, "confidence": 0.91, "summary": "A 48-hour '
    "dockworker strike has halted container handling at the Port of Hamburg, delaying "
    'automotive parts and electronics."}'
)


class StubLLMProvider:
    """Replay one or more fixture files in order; the last one repeats.

    ``StubLLMProvider(dir)`` always returns ``strike_hamburg.txt``.
    ``StubLLMProvider(dir, fixtures=["bad.txt", "good.txt"])`` returns the
    first file on the first ``chat`` call and the second on every call
    after — the simplest way to script a "fails validation once, then
    succeeds" retry scenario.
    """

    name = "stub"
    supports_structured = True

    def __init__(
        self,
        fixtures_dir: Path | None,
        fixtures: Sequence[str] = (DEFAULT_FIXTURE,),
        *,
        responses: Sequence[str] | None = None,
    ) -> None:
        if responses is not None:
            if not responses:
                raise ValueError("StubLLMProvider needs at least one response")
            self._responses: list[str] = list(responses)
        else:
            if fixtures_dir is None:
                raise ValueError("StubLLMProvider needs fixtures_dir or responses")
            if not fixtures:
                raise ValueError("StubLLMProvider needs at least one fixture name")
            self._responses = [
                (Path(fixtures_dir) / name).read_text(encoding="utf-8") for name in fixtures
            ]
        #: Every ``messages`` list this provider has been asked to complete.
        self.calls: list[list[Message]] = []

    @classmethod
    def from_strings(cls, responses: Sequence[str]) -> StubLLMProvider:
        """Replay literal strings instead of files (no fixtures directory needed)."""
        return cls(None, responses=responses)

    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        self.calls.append(list(messages))
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[index]


__all__ = ["DEFAULT_FIXTURE", "DEFAULT_RESPONSE", "StubLLMProvider"]
