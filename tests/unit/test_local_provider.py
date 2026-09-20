"""LocalHFProvider plumbing with a fake backend — no torch, no weights."""

from __future__ import annotations

import pytest

from chokepoint.agent.providers.base import LLMProvider, Message
from chokepoint.agent.providers.local_hf import LocalHFProvider


class FakeBackend:
    def __init__(self, reply: str = '"event_type": "strike"}', *, fail_load: bool = False) -> None:
        self.reply = reply
        self.fail_load = fail_load
        self.loads = 0
        self.calls: list[tuple[list[Message], str, int]] = []

    def load(self) -> None:
        if self.fail_load:
            raise OSError("weights not found")
        self.loads += 1

    def generate(self, messages: list[Message], *, prefill: str, max_new_tokens: int) -> str:
        self.calls.append((messages, prefill, max_new_tokens))
        return prefill + self.reply


MESSAGES = [{"role": "user", "content": "hi"}]


def test_satisfies_protocol() -> None:
    assert isinstance(LocalHFProvider(backend=FakeBackend()), LLMProvider)
    assert LocalHFProvider(backend=FakeBackend()).supports_structured is False


def test_constructing_does_not_load_weights() -> None:
    be = FakeBackend()
    p = LocalHFProvider(backend=be)
    assert be.loads == 0
    assert p.load_seconds is None


def test_load_is_lazy_and_idempotent() -> None:
    be = FakeBackend()
    p = LocalHFProvider(backend=be)
    p.chat(MESSAGES)
    p.chat(MESSAGES)
    p.load()
    assert be.loads == 1
    assert p.load_seconds is not None and p.load_seconds >= 0


def test_prefill_and_generation_params_are_passed() -> None:
    be = FakeBackend()
    p = LocalHFProvider(backend=be, max_new_tokens=99, prefill="{")
    out = p.chat(MESSAGES, structured=True)
    assert out.startswith("{")
    msgs, prefill, max_new = be.calls[0]
    assert msgs == MESSAGES
    assert prefill == "{"
    assert max_new == 99
    assert p.last_latency_seconds is not None


def test_load_errors_propagate() -> None:
    p = LocalHFProvider(backend=FakeBackend(fail_load=True))
    with pytest.raises(OSError, match="weights not found"):
        p.chat(MESSAGES)


def test_default_backend_is_transformers_and_lazy() -> None:
    from chokepoint.agent.providers.local_hf import TransformersBackend

    p = LocalHFProvider("some/model")
    assert isinstance(p._backend, TransformersBackend)
    # Construction must not touch the heavy stack: a bogus model id is fine until first use.
    assert p.load_seconds is None
