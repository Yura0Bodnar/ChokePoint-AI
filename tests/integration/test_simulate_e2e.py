from __future__ import annotations

from fastapi.testclient import TestClient

MINIMAL_EVENT_PAYLOAD = {
    "event": {
        "event_type": "strike",
        "locations": [{"raw": "Hamburg Port", "node_id": "port_hamburg"}],
        "affected_goods": ["auto parts"],
        "severity": 4,
        "confidence": 0.8,
        "summary": "test",
    }
}


def test_simulate_with_event_returns_valid_result(client: TestClient) -> None:
    resp = client.post("/api/v1/simulate", json=MINIMAL_EVENT_PAYLOAD)
    assert resp.status_code == 200

    body = resp.json()
    assert body["epicentre_node_ids"] == ["port_hamburg"]
    assert len(body["impacted"]) > 0
    assert body["degraded"] is True  # only stubs exist in this slice
    assert body["unresolved_entities"] == []
    assert body["runtime_ms"] >= 0


def test_simulate_with_text_uses_stub_llm_provider(client: TestClient) -> None:
    resp = client.post("/api/v1/simulate", json={"text": "A strike hit Hamburg Port today."})
    assert resp.status_code == 200

    body = resp.json()
    assert body["event"]["event_type"] == "strike"
    assert body["degraded"] is True


def test_simulate_impacted_nodes_are_sorted_desc_by_impact(client: TestClient) -> None:
    resp = client.post("/api/v1/simulate", json=MINIMAL_EVENT_PAYLOAD)
    scores = [node["impact_score"] for node in resp.json()["impacted"]]
    assert scores == sorted(scores, reverse=True)


def test_simulate_without_text_doc_id_or_event_returns_422(client: TestClient) -> None:
    resp = client.post("/api/v1/simulate", json={})
    assert resp.status_code == 422


def test_simulate_with_doc_id_returns_422_in_this_slice(client: TestClient) -> None:
    # No document store is wired in yet (arrives with Person 1's ingestion PR).
    resp = client.post("/api/v1/simulate", json={"doc_id": "abc123"})
    assert resp.status_code == 422


def test_simulate_severity_override_changes_impact_scores(client: TestClient) -> None:
    low = client.post(
        "/api/v1/simulate",
        json={**MINIMAL_EVENT_PAYLOAD, "severity_override": 1},
    ).json()
    high = client.post(
        "/api/v1/simulate",
        json={**MINIMAL_EVENT_PAYLOAD, "severity_override": 5},
    ).json()
    assert high["impacted"][0]["impact_score"] >= low["impacted"][0]["impact_score"]


def test_simulate_rejects_out_of_range_max_hops(client: TestClient) -> None:
    resp = client.post("/api/v1/simulate", json={**MINIMAL_EVENT_PAYLOAD, "max_hops": 0})
    assert resp.status_code == 422
