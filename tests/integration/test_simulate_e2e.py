from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from chokepoint.api import deps


@pytest.fixture(autouse=True, scope="module")
def _real_graph_backend() -> Iterator[None]:
    """Run this module against the real NetworkX graph regardless of the developer's .env.

    ``get_graph_store`` is lru_cache'd and ``DEMO_MODE=true`` would silently swap in the
    stub, which returns three canned nodes for *any* event and would make these tests
    pass or fail for the wrong reason.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DEMO_MODE", "false")
        patch.setenv("GRAPH_BACKEND", "networkx")
        deps.get_settings.cache_clear()
        deps.get_graph_store.cache_clear()
        yield
    deps.get_settings.cache_clear()
    deps.get_graph_store.cache_clear()


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


# ── the real graph: Suez / Red Sea and Black Sea grain corridors ───────────────────────
def _event_payload(node_id: str, raw: str, event_type: str, severity: int) -> dict[str, object]:
    return {
        "event": {
            "event_type": event_type,
            "locations": [{"raw": raw, "node_id": node_id}],
            "severity": severity,
            "confidence": 0.9,
            "summary": "test",
        }
    }


def test_simulate_suez_corridor_produces_impact(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/simulate", json=_event_payload("chokepoint_suez", "Suez Canal", "blockade", 5)
    )
    assert resp.status_code == 200

    body = resp.json()
    assert len(body["impacted"]) > 0
    assert body["epicentre_node_ids"] == ["chokepoint_suez"]
    assert body["unresolved_entities"] == []
    # Not vacuous: the stub returns three canned Hamburg-corridor nodes for ANY event, so pin
    # ids that only exist in the real Suez corridor (and its cross-link into corridor 1).
    ids = {node["node_id"] for node in body["impacted"]}
    assert {"port_piraeus", "com_electronics", "ind_electronics_eu", "mkt_eu_retail"} <= ids
    assert "com_containers" in ids
    assert all("weighted propagation" in node["explanation"] for node in body["impacted"])
    assert not any("Stub" in node["explanation"] for node in body["impacted"])


def test_simulate_odesa_grain_cascade_reaches_egypt(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/simulate", json=_event_payload("port_odesa", "Port of Odesa", "conflict", 4)
    )
    assert resp.status_code == 200

    impacted = resp.json()["impacted"]
    ids = [node["node_id"] for node in impacted]
    assert {"com_grain", "ind_agri_ua", "mkt_egypt_wheat", "mkt_mena_food"} <= set(ids)
    hops = {node["node_id"]: node["hops"] for node in impacted}
    assert hops["com_grain"] == 1 and hops["mkt_egypt_wheat"] == 2  # a genuine multi-hop cascade


def test_simulate_severity_override_scales_the_suez_cascade(client: TestClient) -> None:
    base = _event_payload("chokepoint_suez", "Suez Canal", "blockade", 3)
    low = client.post("/api/v1/simulate", json={**base, "severity_override": 1}).json()
    high = client.post("/api/v1/simulate", json={**base, "severity_override": 5}).json()
    assert low["impacted"] and high["impacted"]
    assert high["impacted"][0]["impact_score"] > low["impacted"][0]["impact_score"]


def test_simulate_node_absent_from_the_graph_is_a_clean_empty_result(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/simulate", json=_event_payload("port_atlantis", "Atlantis", "strike", 5)
    )
    assert resp.status_code == 200  # never a 500 for an unmodelled place
    assert resp.json()["impacted"] == []
