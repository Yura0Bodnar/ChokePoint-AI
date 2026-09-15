from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from chokepoint.contracts import (
    DisruptionEvent,
    EventType,
    ExtractedLocation,
    ImpactedNode,
    RawDocument,
    SimulateRequest,
    SimulationResult,
)


def test_raw_document_builds_from_minimal_payload() -> None:
    doc = RawDocument(
        doc_id="abc123",
        source="gdelt",
        source_name="GDELT/DE",
        url="https://example.com/article",
        title="Strike halts Hamburg Port",
        published_at=datetime.now(UTC),
        fetched_at=datetime.now(UTC),
    )
    assert doc.body == ""
    assert doc.language == "en"


def test_disruption_event_builds_from_minimal_payload() -> None:
    event = DisruptionEvent(
        event_type=EventType.STRIKE,
        locations=[ExtractedLocation(raw="Hamburg Port")],
        severity=3,
        confidence=0.7,
        summary="A strike at Hamburg Port.",
    )
    assert event.affected_goods == []
    assert event.extractor_version == "v1"


def test_disruption_event_rejects_out_of_range_severity() -> None:
    with pytest.raises(ValidationError):
        DisruptionEvent(
            event_type=EventType.STRIKE,
            locations=[ExtractedLocation(raw="Hamburg Port")],
            severity=8,
            confidence=0.7,
            summary="bad severity",
        )


def test_disruption_event_requires_at_least_one_location() -> None:
    with pytest.raises(ValidationError):
        DisruptionEvent(
            event_type=EventType.STRIKE,
            locations=[],
            severity=3,
            confidence=0.7,
            summary="no locations",
        )


def test_disruption_event_json_schema_contains_required_fields() -> None:
    schema = DisruptionEvent.model_json_schema()
    assert "event_type" in schema["properties"]
    assert "severity" in schema["properties"]
    assert "confidence" in schema["properties"]


def test_simulation_result_builds_from_minimal_payload() -> None:
    event = DisruptionEvent(
        event_type=EventType.STRIKE,
        locations=[ExtractedLocation(raw="Hamburg Port", node_id="port_hamburg")],
        severity=4,
        confidence=0.8,
        summary="A strike at Hamburg Port.",
    )
    result = SimulationResult(
        event=event,
        epicentre_node_ids=["port_hamburg"],
        impacted=[
            ImpactedNode(
                node_id="com_auto_parts",
                label="Automotive components",
                node_type="commodity",
                impact_score=0.5,
                eta_days=3.0,
                hops=1,
                confidence=0.7,
                path=["port_hamburg", "com_auto_parts"],
                explanation="test",
            )
        ],
        params={"max_hops": 4.0, "decay": 0.75},
        runtime_ms=12.3,
    )
    assert result.degraded is False
    assert len(result.impacted) == 1


def test_simulate_request_accepts_event_only() -> None:
    request = SimulateRequest(
        event=DisruptionEvent(
            event_type=EventType.STRIKE,
            locations=[ExtractedLocation(raw="Hamburg Port", node_id="port_hamburg")],
            severity=4,
            confidence=0.8,
            summary="test",
        )
    )
    assert request.text is None
    assert request.max_hops == 4
    assert request.decay == 0.75
