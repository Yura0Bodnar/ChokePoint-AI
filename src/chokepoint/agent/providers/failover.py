"""``FailoverProvider`` — HF Inference first, local CPU model when HF is gone.

Covers the two failure modes the architecture calls out (§7.5): free credits
exhausted (HTTP 402) and an offline venue (connection errors). ``name`` /
``supports_structured`` always reflect the provider that answers the current
call, so ``extractor_version`` records which one actually produced an event
(``hf-v1`` vs ``local-v1``).

Two policies, chosen at construction:

* **automatic** (default) — on a transport failure the call is retried on the
  local model and, when ``sticky``, every later call stays there. Right for
  unattended runs (scripts, evals).
* **``require_consent=True``** — the local model takes ~40 s to load and run, so
  it must be an explicit user choice. A transport failure raises
  :class:`PrimaryUnavailableError` and nothing is switched; the caller re-issues
  the request inside :func:`local_fallback_consent`, which routes straight to the
  local model without touching HF again. Nothing is sticky: the next request
  without consent tries HF first. Consent lives in a ``ContextVar`` so
  concurrent requests on a shared provider cannot see each other's choice.

Only transport / HTTP failures trigger the failover. Programming errors
(``TypeError``, ``ValueError``, …) propagate unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import httpx
from huggingface_hub.errors import HfHubHTTPError

from chokepoint.agent.providers.base import LLMProvider, Message

log = logging.getLogger(__name__)

_local_consent: ContextVar[bool] = ContextVar("chokepoint_local_fallback_consent", default=False)


def is_transport_failure(exc: BaseException) -> bool:
    """True for anything that means "the remote provider is unusable right now"."""
    return isinstance(exc, HfHubHTTPError | httpx.HTTPError | ConnectionError | TimeoutError)


class PrimaryUnavailableError(RuntimeError):
    """The remote provider failed and the caller has not authorised the local fallback."""

    def __init__(self, primary: str, fallback: str, reason: str) -> None:
        super().__init__(f"{primary} provider unavailable ({reason}); '{fallback}' needs consent")
        self.primary = primary
        self.fallback = fallback
        self.reason = reason


@contextmanager
def local_fallback_consent(granted: bool = True) -> Iterator[None]:
    """Within this block a consent-mode ``FailoverProvider`` runs on the local model."""
    token = _local_consent.set(granted)
    try:
        yield
    finally:
        _local_consent.reset(token)


class FailoverProvider:
    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider,
        *,
        sticky: bool = True,
        require_consent: bool = False,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._sticky = sticky
        self._require_consent = require_consent
        self._active: LLMProvider = primary
        #: Why the last failover (or refusal) happened, for logs / the UI.
        self.failover_reason: str | None = None

    @property
    def active(self) -> LLMProvider:
        return self._current()

    @property
    def name(self) -> str:
        return self._current().name

    @property
    def supports_structured(self) -> bool:
        return self._current().supports_structured

    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        if self._require_consent:
            return self._chat_with_consent(messages, structured)
        if self._active is self._primary:
            try:
                return self._primary.chat(messages, structured=structured)
            except Exception as exc:
                if not is_transport_failure(exc):
                    raise
                self.failover_reason = _describe(exc)
                log.error(
                    "primary provider %s failed (%s); failing over to %s",
                    self._primary.name,
                    self.failover_reason,
                    self._fallback.name,
                )
                if self._sticky:
                    self._active = self._fallback
                return self._fallback.chat(messages, structured=structured)
        return self._fallback.chat(messages, structured=structured)

    def _chat_with_consent(self, messages: list[Message], structured: bool) -> str:
        if _local_consent.get():
            return self._fallback.chat(messages, structured=structured)
        try:
            return self._primary.chat(messages, structured=structured)
        except Exception as exc:
            if not is_transport_failure(exc):
                raise
            self.failover_reason = _describe(exc)
            log.error(
                "primary provider %s failed (%s); local fallback %s awaits user consent",
                self._primary.name,
                self.failover_reason,
                self._fallback.name,
            )
            raise PrimaryUnavailableError(
                self._primary.name, self._fallback.name, self.failover_reason
            ) from exc

    def _current(self) -> LLMProvider:
        if self._require_consent and _local_consent.get():
            return self._fallback
        return self._active


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"


__all__ = [
    "FailoverProvider",
    "PrimaryUnavailableError",
    "is_transport_failure",
    "local_fallback_consent",
]
