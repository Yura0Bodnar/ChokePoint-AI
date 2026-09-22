"""``build_provider(settings)`` — the single lever behind ``LLM_PROVIDER``.

``build_extraction_agent(settings)`` is the single call ``api/deps.py`` needs on
Integration Day: it returns an ``ExtractionAgent`` whose ``extract_text(str)``
turns the raw text from ``POST /api/v1/simulate`` into a ``DisruptionEvent``.

    agent = build_extraction_agent(get_settings())
    event = agent.extract_text(request.text)

| ``LLM_PROVIDER`` | Returns |
|---|---|
| ``hf`` | ``HFInferenceProvider``; wrapped in ``FailoverProvider`` → ``LocalHFProvider`` when ``LLM_FAILOVER_TO_LOCAL`` is true **and** torch is installed. The local model is never entered silently: an HF outage raises ``PrimaryUnavailableError`` (HTTP 424) and the local model loads lazily, only when the request is re-sent with ``force_local``. Without torch (Docker, CI) it is bare HF plus a warning |
| ``local`` | ``LocalHFProvider`` (needs ``uv sync --group local``) |
| ``stub`` | ``StubLLMProvider`` replaying a canned Hamburg strike; no network, for CI and ``DEMO_MODE`` |
"""

from __future__ import annotations

import importlib.util
import logging

from chokepoint.agent.extractor import ExtractionAgent
from chokepoint.agent.providers.base import LLMProvider
from chokepoint.agent.providers.failover import FailoverProvider
from chokepoint.agent.providers.hf_inference import HFInferenceProvider
from chokepoint.agent.providers.local_hf import LocalHFProvider
from chokepoint.agent.providers.stub import DEFAULT_RESPONSE, StubLLMProvider
from chokepoint.agent.resolver import load_aliases
from chokepoint.config import Settings

log = logging.getLogger(__name__)


def local_stack_available() -> bool:
    """True when the ``local`` dependency group (torch + transformers) is importable."""
    return (
        importlib.util.find_spec("torch") is not None
        and importlib.util.find_spec("transformers") is not None
    )


def build_provider(settings: Settings) -> LLMProvider:
    kind = settings.llm_provider.lower()
    if kind == "stub":
        return StubLLMProvider.from_strings([DEFAULT_RESPONSE])
    if kind == "local":
        return LocalHFProvider(settings.local_model, device=settings.local_device)
    if kind == "hf":
        if not settings.hf_token:
            raise ValueError("LLM_PROVIDER=hf requires HF_TOKEN to be set")
        hf = HFInferenceProvider(
            model=settings.hf_model,
            token=settings.hf_token,
            provider=settings.hf_inference_provider,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )
        if settings.llm_failover_to_local:
            if local_stack_available():
                # require_consent: the ~40 s local run is the *user's* call (API
                # `force_local`), never a silent switch. See failover.py.
                return FailoverProvider(
                    hf,
                    LocalHFProvider(settings.local_model, device=settings.local_device),
                    require_consent=True,
                )
            # Docker / CI images deliberately omit torch. A failover that would
            # itself crash on ImportError is worse than none: run bare HF and
            # rely on DEMO_MODE / LLM_PROVIDER=stub as the venue-day insurance.
            log.warning(
                "LLM_FAILOVER_TO_LOCAL is on but torch/transformers are not installed "
                "(uv sync --group local); running HF without local failover"
            )
        return hf
    raise ValueError(f"unknown LLM_PROVIDER={settings.llm_provider!r}; expected hf | local | stub")


def build_extraction_agent(settings: Settings) -> ExtractionAgent:
    """One call for ``api/deps.py``: provider (per ``LLM_PROVIDER``) + alias map + retry cap.

    ``LLM_MAX_RETRIES`` is the cap on *total* provider attempts per extraction (the
    name is kept for ``.env`` compatibility; the default of 3 matches the ladder's
    "3 attempts, then heuristic fallback"). Every attempt is a billed HF call, so on
    the free tier lowering it directly stretches the monthly credit budget.

    Raises ``ValueError`` for a misconfigured provider (e.g. ``LLM_PROVIDER=hf`` with no
    ``HF_TOKEN``) or ``LLM_MAX_RETRIES < 1`` — at construction, not on the first request.
    """
    return ExtractionAgent(
        build_provider(settings), load_aliases(), max_attempts=settings.llm_max_retries
    )


__all__ = ["build_extraction_agent", "build_provider", "local_stack_available"]
