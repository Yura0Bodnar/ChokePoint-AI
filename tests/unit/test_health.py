from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz(client: TestClient) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["llm_provider"] == "stub"
    assert body["graph_backend"] == "networkx"


def test_healthz_carries_request_id_header(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert "X-Request-ID" in resp.headers
