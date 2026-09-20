from __future__ import annotations

import httpx
import pytest
from huggingface_hub.errors import HfHubHTTPError

from chokepoint.agent.providers.base import LLMProvider, Message
from chokepoint.agent.providers.failover import FailoverProvider, is_transport_failure
from chokepoint.agent.providers.stub import StubLLMProvider


class Flaky:
    name = "hf"
    supports_structured = True

    def __init__(self, exc: BaseException | None) -> None:
        self.exc = exc
        self.calls = 0

    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return "primary"


def _http(status: int) -> HfHubHTTPError:
    resp = httpx.Response(
        status, request=httpx.Request("POST", "https://router.huggingface.co/v1/chat/completions")
    )
    return HfHubHTTPError(f"HTTP {status}", response=resp)


MESSAGES = [{"role": "user", "content": "hi"}]


def _local() -> StubLLMProvider:
    p = StubLLMProvider.from_strings(["local"])
    p.name = "local"  # type: ignore[misc]
    p.supports_structured = False  # type: ignore[misc]
    return p


def test_satisfies_protocol() -> None:
    assert isinstance(FailoverProvider(Flaky(None), _local()), LLMProvider)


def test_primary_used_when_healthy() -> None:
    primary, local = Flaky(None), _local()
    f = FailoverProvider(primary, local)
    assert f.chat(MESSAGES) == "primary"
    assert f.name == "hf" and f.active is primary
    assert local.calls == []


@pytest.mark.parametrize("status", [402, 429, 500, 503])
def test_http_failure_switches_to_fallback_and_sticks(status: int) -> None:
    primary, local = Flaky(_http(status)), _local()
    f = FailoverProvider(primary, local)
    assert f.chat(MESSAGES) == "local"
    assert f.active is local
    assert f.name == "local" and f.supports_structured is False
    assert f.failover_reason is not None and "HfHubHTTPError" in f.failover_reason
    f.chat(MESSAGES)
    assert primary.calls == 1  # dead primary not retried
    assert len(local.calls) == 2


def test_network_failure_switches() -> None:
    f = FailoverProvider(Flaky(httpx.ConnectError("no route")), _local())
    assert f.chat(MESSAGES) == "local"


def test_non_transport_errors_propagate() -> None:
    primary = Flaky(ValueError("bad messages"))
    f = FailoverProvider(primary, _local())
    with pytest.raises(ValueError, match="bad messages"):
        f.chat(MESSAGES)
    assert f.active is primary


def test_non_sticky_retries_primary_each_call() -> None:
    primary = Flaky(_http(503))
    f = FailoverProvider(primary, _local(), sticky=False)
    f.chat(MESSAGES)
    f.chat(MESSAGES)
    assert primary.calls == 2
    assert f.active is primary


def test_is_transport_failure_classification() -> None:
    assert is_transport_failure(_http(402))
    assert is_transport_failure(httpx.ReadTimeout("slow"))
    assert is_transport_failure(ConnectionError())
    assert not is_transport_failure(ValueError())
    assert not is_transport_failure(KeyError())
