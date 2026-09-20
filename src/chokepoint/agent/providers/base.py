"""The LLM provider seam (ARCHITECTURE_AND_PLAN.md §7.5).

Every provider — HF Inference API, a local CPU model, or the CI fixture
replay — implements this one Protocol. The rest of the agent package only
ever sees ``chat(messages) -> str``; *where* the string comes from, and how
much it cost, is the provider's business.

This is the formal version of the ad-hoc ``LLMProvider`` Protocol that
``chokepoint.api.deps`` defined inline for the Day-1 stub. ``deps.py`` will be
switched over to import this one on Integration Day.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

Message = dict[str, str]
"""One OpenAI-style chat turn: ``{"role": "system" | "user" | "assistant", "content": str}``."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    supports_structured: bool

    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        """Return the model's raw text reply for ``messages``.

        ``structured=True`` asks the provider to enforce the
        :class:`~chokepoint.contracts.DisruptionEvent` JSON schema at decode
        time when it can (ladder layer ①). Providers that cannot must still
        return whatever the model produced — the parser handles the rest.
        """
        ...
