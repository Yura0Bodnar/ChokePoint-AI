"""``FailoverProvider`` — HF Inference first, local CPU model when HF is gone.

Covers the two failure modes the architecture calls out (§7.5): free credits
exhausted (HTTP 402) and an offline venue (connection errors). The switch is
sticky for the life of the process so a dead primary is not re-tried on every
document. ``name`` / ``supports_structured`` always reflect the *active*
provider, so ``extractor_version`` records which one actually produced an
event (``hf-v1`` vs ``local-v1``).

Only transport / HTTP failures trigger the switch. Programming errors
(``TypeError``, ``ValueError``, …) propagate unchanged.
"""

from __future__ import annotations

import logging

import httpx
from huggingface_hub.errors import HfHubHTTPError

from chokepoint.agent.providers.base import LLMProvider, Message

log = logging.getLogger(__name__)


def is_transport_failure(exc: BaseException) -> bool:
    """True for anything that means "the remote provider is unusable right now"."""
    return isinstance(exc, HfHubHTTPError | httpx.HTTPError | ConnectionError | TimeoutError)


class FailoverProvider:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider, *, sticky: bool = True) -> None:
        self._primary = primary
        self._fallback = fallback
        self._sticky = sticky
        self._active: LLMProvider = primary
        self.name = primary.name
        self.supports_structured = primary.supports_structured
        #: Why the last switch happened, for logs / the UI's degraded badge.
        self.failover_reason: str | None = None

    @property
    def active(self) -> LLMProvider:
        return self._active

    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        if self._active is self._primary:
            try:
                return self._primary.chat(messages, structured=structured)
            except Exception as exc:
                if not is_transport_failure(exc):
                    raise
                self.failover_reason = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
                log.error(
                    "primary provider %s failed (%s); failing over to %s",
                    self._primary.name,
                    self.failover_reason,
                    self._fallback.name,
                )
                if self._sticky:
                    self._switch(self._fallback)
                return self._fallback.chat(messages, structured=structured)
        return self._fallback.chat(messages, structured=structured)

    def _switch(self, target: LLMProvider) -> None:
        self._active = target
        self.name = target.name
        self.supports_structured = target.supports_structured


__all__ = ["FailoverProvider", "is_transport_failure"]
