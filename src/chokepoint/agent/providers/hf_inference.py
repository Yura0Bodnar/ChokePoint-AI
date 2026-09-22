"""Hugging Face Inference API provider (ARCHITECTURE_AND_PLAN.md §7.2).

Prompt-only by design: **no ``response_format`` is ever sent.** The free serverless
tier's routed providers reject it (``json_schema`` and, on several models,
``json_object`` too) with an immediate HTTP 400, so the payload is just
``model`` / ``messages`` / ``max_tokens`` / ``temperature``. The structure comes from
the versioned prompt (``agent/prompts.py``: "return ONLY valid JSON inside a
```json code block") plus the fence-aware parser and repair ladder
(``agent/parser.py``), not from decode-time enforcement.

Every HTTP or network failure propagates uncaught — the caller decides whether to
retry, fall back to a local model, or surface an error. Nothing is swallowed here.
"""

from __future__ import annotations

from typing import cast

from huggingface_hub import InferenceClient
from huggingface_hub.inference._providers import PROVIDER_OR_POLICY_T

from chokepoint.agent.providers.base import Message


class HFInferenceProvider:
    name = "hf"
    #: Nothing here enforces a schema at decode time; see the module docstring.
    supports_structured = False

    def __init__(
        self,
        model: str,
        token: str,
        provider: str = "auto",
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
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

    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        """One chat completion. ``structured`` is accepted for the ``LLMProvider``
        protocol and deliberately ignored: no ``response_format`` is ever sent."""
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        content = completion.choices[0].message.content
        return content or ""


__all__ = ["HFInferenceProvider"]
