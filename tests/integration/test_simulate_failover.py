"""POST /api/v1/simulate while Hugging Face is down: 424 first, local only on ``force_local``."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from huggingface_hub.errors import HfHubHTTPError

from chokepoint.agent.extractor import ExtractionAgent
from chokepoint.agent.providers.base import Message
from chokepoint.agent.providers.failover import FailoverProvider
from chokepoint.agent.providers.stub import DEFAULT_RESPONSE
from chokepoint.agent.resolver import load_aliases
from chokepoint.api import deps
from chokepoint.api.main import app
from chokepoint.contracts import SimulateRequest

TEXT = {"text": "Dockworkers strike at Hamburg Port halts container handling."}


class DownHF:
    name = "hf"
    supports_structured = True

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        self.calls += 1
        resp = httpx.Response(
            402, request=httpx.Request("POST", "https://router.huggingface.co/v1/chat/completions")
        )
        raise HfHubHTTPError("402 Client Error: credits depleted", response=resp)


class LocalModel:
    name = "local"
    supports_structured = False

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[Message], *, structured: bool = True) -> str:
        self.calls += 1
        return DEFAULT_RESPONSE


@pytest.fixture
def hf_down(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[DownHF, LocalModel]]:
    hf, local = DownHF(), LocalModel()
    agent = ExtractionAgent(FailoverProvider(hf, local, require_consent=True), load_aliases())
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("GRAPH_BACKEND", "networkx")
    deps.get_settings.cache_clear()
    deps.get_graph_store.cache_clear()
    app.dependency_overrides[deps.get_llm_provider] = lambda: agent
    yield hf, local
    app.dependency_overrides.pop(deps.get_llm_provider, None)
    deps.get_settings.cache_clear()
    deps.get_graph_store.cache_clear()


def test_hf_outage_returns_424_with_an_actionable_payload(
    client: TestClient, hf_down: tuple[DownHF, LocalModel]
) -> None:
    hf, local = hf_down
    resp = client.post("/api/v1/simulate", json=TEXT)

    assert resp.status_code == 424
    detail = resp.json()["detail"]
    assert detail["code"] == "hf_unavailable"
    assert "Hugging Face" in detail["message"]
    assert "HfHubHTTPError" in detail["reason"]
    assert (hf.calls, local.calls) == (1, 0)  # local never starts without consent


def test_force_local_runs_the_local_model_and_skips_hf(
    client: TestClient, hf_down: tuple[DownHF, LocalModel]
) -> None:
    hf, local = hf_down
    resp = client.post("/api/v1/simulate", json={**TEXT, "force_local": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["event"]["extractor_version"].startswith("local-")
    assert len(body["impacted"]) > 0
    assert (hf.calls, local.calls) == (0, 1)


def test_local_consent_does_not_stick_to_later_requests(
    client: TestClient, hf_down: tuple[DownHF, LocalModel]
) -> None:
    hf, local = hf_down
    assert client.post("/api/v1/simulate", json={**TEXT, "force_local": True}).status_code == 200

    again = client.post("/api/v1/simulate", json=TEXT)

    assert again.status_code == 424  # the user is asked again; HF was retried, not skipped
    assert (hf.calls, local.calls) == (1, 1)


def test_force_local_is_harmless_when_an_event_is_supplied(
    client: TestClient, hf_down: tuple[DownHF, LocalModel]
) -> None:
    hf, local = hf_down
    payload = {
        "event": {
            "event_type": "strike",
            "locations": [{"raw": "Hamburg Port", "node_id": "port_hamburg"}],
            "severity": 3,
            "confidence": 0.8,
            "summary": "test",
        },
        "force_local": True,
    }
    assert client.post("/api/v1/simulate", json=payload).status_code == 200
    assert (hf.calls, local.calls) == (0, 0)  # no LLM involved at all


def test_force_local_defaults_to_false() -> None:
    assert SimulateRequest(text="x").force_local is False
