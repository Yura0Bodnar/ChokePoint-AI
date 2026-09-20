"""Local CPU provider — the demo's insurance policy (ARCHITECTURE_AND_PLAN.md §7.5, P2.8).

Runs ``Qwen/Qwen2.5-1.5B-Instruct`` (or any chat model) through ``transformers``
on the CPU. Slow (seconds per extraction) but unkillable: no credits, no
network once the weights are cached. Weights are loaded lazily on the first
``chat`` so constructing the provider is free.

``torch`` / ``transformers`` live in the ``local`` dependency group
(``uv sync --group local``); this module imports them only inside
``TransformersBackend`` so the rest of the agent package never needs them.

Layer ① (schema-constrained decoding) is not available here —
``supports_structured`` is ``False`` and the parser/retry/fallback layers
carry the guarantee. As a cheap substitute the assistant turn is *prefilled*
with ``{`` (§7.3): a model that has already emitted an opening brace rarely
starts with "Sure, here is…".
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from chokepoint.agent.providers.base import Message

log = logging.getLogger(__name__)

DEFAULT_LOCAL_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


class TextBackend(Protocol):
    """The one seam between the provider and the heavy ML stack (fakeable in tests)."""

    def load(self) -> None: ...

    def generate(self, messages: list[Message], *, prefill: str, max_new_tokens: int) -> str: ...


class TransformersBackend:
    """Real backend: tokenizer + causal LM from ``transformers``, greedy decoding."""

    def __init__(self, model_id: str, *, device: str = "cpu") -> None:
        self._model_id = model_id
        self._device = device
        self._tok: Any = None
        self._model: Any = None

    def load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._tok = AutoTokenizer.from_pretrained(self._model_id)
        # float32 on CPU: bf16 matmuls are slow or unsupported on many CPUs,
        # and a 1.5B model is ~6 GB in fp32 — fine on a 16 GB laptop.
        self._model = AutoModelForCausalLM.from_pretrained(self._model_id, dtype=torch.float32)
        self._model.to(self._device).eval()

    def generate(self, messages: list[Message], *, prefill: str, max_new_tokens: int) -> str:
        import torch

        self.load()
        prompt = (
            self._tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            + prefill
        )
        inputs = self._tok(prompt, return_tensors="pt").to(self._device)
        with torch.inference_mode():
            out = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,  # deterministic: extraction, not creative writing
                pad_token_id=self._tok.eos_token_id,
            )
        new_tokens = out[0, inputs["input_ids"].shape[1] :]
        return prefill + str(self._tok.decode(new_tokens, skip_special_tokens=True))


class LocalHFProvider:
    name = "local"
    supports_structured = False

    def __init__(
        self,
        model_id: str = DEFAULT_LOCAL_MODEL,
        *,
        device: str = "cpu",
        max_new_tokens: int = 512,
        prefill: str = "{",
        backend: TextBackend | None = None,
    ) -> None:
        self.model_id = model_id
        self._max_new_tokens = max_new_tokens
        self._prefill = prefill
        self._backend: TextBackend = backend or TransformersBackend(model_id, device=device)
        #: Seconds spent loading weights (``None`` until the first ``load``).
        self.load_seconds: float | None = None
        #: Wall-clock seconds of the most recent ``chat``.
        self.last_latency_seconds: float | None = None

    def load(self) -> float:
        """Load weights now (idempotent). Returns the load time in seconds."""
        if self.load_seconds is None:
            t0 = time.perf_counter()
            self._backend.load()
            self.load_seconds = time.perf_counter() - t0
            log.info("local model %s loaded in %.1fs", self.model_id, self.load_seconds)
        return self.load_seconds

    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        self.load()
        t0 = time.perf_counter()
        text = self._backend.generate(
            messages, prefill=self._prefill, max_new_tokens=self._max_new_tokens
        )
        self.last_latency_seconds = time.perf_counter() - t0
        return text


__all__ = ["DEFAULT_LOCAL_MODEL", "LocalHFProvider", "TextBackend", "TransformersBackend"]
