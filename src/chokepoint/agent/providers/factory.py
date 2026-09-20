"""``build_provider(settings)`` — the single lever behind ``LLM_PROVIDER``.

Meant for ``api/deps.py`` on Integration Day: replace the inline stub with

    provider = build_provider(settings)
    agent = ExtractionAgent(provider, load_aliases())

| ``LLM_PROVIDER`` | Returns |
|---|---|
| ``hf`` | ``HFInferenceProvider``; wrapped in ``FailoverProvider`` → ``LocalHFProvider`` when ``LLM_FAILOVER_TO_LOCAL`` is true **and** torch is installed (the local model loads lazily, only if HF fails). Without torch (Docker, CI) it is bare HF plus a warning |
| ``local`` | ``LocalHFProvider`` (needs ``uv sync --group local``) |
| ``stub`` | ``StubLLMProvider`` replaying a canned Hamburg strike; no network, for CI and ``DEMO_MODE`` |
"""

from __future__ import annotations

import importlib.util
import logging

from chokepoint.agent.providers.base import LLMProvider
from chokepoint.agent.providers.failover import FailoverProvider
from chokepoint.agent.providers.hf_inference import HFInferenceProvider
from chokepoint.agent.providers.local_hf import LocalHFProvider
from chokepoint.agent.providers.stub import DEFAULT_RESPONSE, StubLLMProvider
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
                return FailoverProvider(
                    hf, LocalHFProvider(settings.local_model, device=settings.local_device)
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


__all__ = ["build_provider", "local_stack_available"]
