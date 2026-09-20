"""Hugging Face Inference API provider (ARCHITECTURE_AND_PLAN.md §7.2).

Ladder layer ①: schema-constrained decoding via OpenAI-compatible
``response_format``. Structured-output support is *provider-dependent*, so
``chat`` degrades in three steps and records which one actually worked:

    json_schema  ->  json_object  ->  (no response_format; prompt only)

Only a 4xx rejection of the ``response_format`` triggers the downgrade.
Auth, quota and server errors, and any network failure, propagate
uncaught — the caller decides whether to retry, fall back to a local
model, or surface a 502. Nothing is swallowed inside the provider.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, cast

from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError
from huggingface_hub.inference._providers import PROVIDER_OR_POLICY_T

from chokepoint.agent.providers.base import Message
from chokepoint.agent.schema import DISRUPTION_EVENT_JSON_SCHEMA

log = logging.getLogger(__name__)

StructuredMode = Literal["json_schema", "json_object", "none"]

# Status codes that mean "the *request shape* was rejected" and therefore
# justify retrying with a weaker response_format. Everything else (401/403
# auth, 402 credits, 404 model, 429 rate limit, 5xx) is not our fault and
# must reach the caller unchanged.
_DOWNGRADE_STATUSES: frozenset[int] = frozenset({400, 422})


class HFInferenceProvider:
    name = "hf"

    def __init__(
        self,
        model: str,
        token: str,
        provider: str = "auto",
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        supports_structured: bool = True,
        base_url: str | None = None,
    ) -> None:
        # provider="auto" routes to the first available Inference Provider for
        # this model, ordered by the account's preferences.
        # `provider` arrives as a plain string from HF_INFERENCE_PROVIDER; the
        # library types it as a Literal of known provider names. With an explicit
        # `base_url` (any OpenAI-compatible endpoint, e.g. a TGI/vLLM server or a
        # test double) the client skips the hub's model→provider lookup entirely.
        if base_url is not None:
            self._client = InferenceClient(api_key=token, base_url=base_url)
        else:
            self._client = InferenceClient(
                model=model, api_key=token, provider=cast(PROVIDER_OR_POLICY_T, provider)
            )
        self._model = model
        self._provider = provider
        self._max_tokens = max_tokens
        self._temperature = temperature
        # Set False (via ctor or the support matrix in docs/PROMPTS.md) for a
        # model/provider pair known to reject json_schema — skips a wasted call.
        self.supports_structured = supports_structured
        #: The response_format mode that produced the most recent reply.
        self.last_mode: StructuredMode = "none"

    # ── public ────────────────────────────────────────────────────────────
    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        modes: list[StructuredMode] = ["none"]
        if structured:
            modes = ["json_object", "none"]
            if self.supports_structured:
                modes.insert(0, "json_schema")

        for i, mode in enumerate(modes):
            is_last = i == len(modes) - 1
            try:
                content = self._complete(messages, mode)
            except HfHubHTTPError as exc:
                if is_last or mode == "none" or not self._is_downgradable(exc):
                    raise
                log.warning(
                    "hf provider rejected response_format=%s for %s (%s); downgrading to %s",
                    mode,
                    self._model,
                    exc.response.status_code,
                    modes[i + 1],
                )
                if mode == "json_schema":
                    self.supports_structured = False
                continue
            self.last_mode = mode
            return content
        raise AssertionError("unreachable: every mode either returned or raised")

    # ── internals ─────────────────────────────────────────────────────────
    def _complete(self, messages: list[Message], mode: StructuredMode) -> str:
        kwargs: dict[str, Any] = {}
        if mode == "json_schema":
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": DISRUPTION_EVENT_JSON_SCHEMA,
            }
        elif mode == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            **kwargs,
        )
        content = completion.choices[0].message.content
        return content or ""

    @staticmethod
    def _is_downgradable(exc: HfHubHTTPError) -> bool:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return status in _DOWNGRADE_STATUSES


__all__ = ["HFInferenceProvider", "StructuredMode"]
