"""Shared data contracts. FROZEN — changes require a PR + team notice.

This module is the single source of truth for the shapes that flow between
the four layers of ChokePoint AI (ingestion -> agent -> graph -> API). It is
authored once, together, by the whole team (see ARCHITECTURE_AND_PLAN.md §6)
and treated afterwards as an API: any change needs a PR and a heads-up in the
team channel, because Person 1 and Person 2 build against this exact shape
on their own branches.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


# ─── L1 → L2 ────────────────────────────────────────────────────────────────
class RawDocument(BaseModel):
    """A single OSINT item, normalized. Produced by ingestion."""

    doc_id: str = Field(description="sha256(url)[:16]")
    source: Literal["gdelt", "rss"]
    source_name: str = Field(description="e.g. 'gCaptain' or 'GDELT/DE'")
    url: HttpUrl
    title: str
    body: str = Field(default="", description="Cleaned text, may be empty")
    published_at: datetime
    language: str = Field(default="en", description="ISO 639-1")
    fetched_at: datetime


# ─── L2 → L3 ────────────────────────────────────────────────────────────────
class EventType(StrEnum):
    STRIKE = "strike"
    BLOCKADE = "blockade"
    SANCTIONS = "sanctions"
    ACCIDENT = "accident"
    CONFLICT = "conflict"
    NATURAL_DISASTER = "natural_disaster"
    CYBERATTACK = "cyberattack"
    CONGESTION = "congestion"
    EXPORT_BAN = "export_ban"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    OTHER = "other"


class ExtractedLocation(BaseModel):
    raw: str = Field(description="Verbatim span from the article")
    node_id: str | None = Field(
        default=None, description="Resolved graph node id, None if unmapped"
    )
    country_iso2: str | None = None


class DisruptionEvent(BaseModel):
    """The LLM's structured output, post-validation and entity resolution.

    This model's JSON Schema is fed to the model via `response_format`.
    Keep it FLAT and SMALL — deep nesting degrades small-model compliance.
    """

    event_type: EventType
    locations: list[ExtractedLocation] = Field(min_length=1, max_length=5)
    affected_goods: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Lowercase commodity/industry terms, e.g. 'electronics'",
    )
    severity: int = Field(ge=1, le=5, description="1 minor, 5 corridor-closing")
    estimated_duration_days: int | None = Field(default=None, ge=0, le=365)
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(max_length=280)

    # provenance — set by our code, never by the model
    source_doc_id: str | None = None
    extractor_version: str = "v1"
    extracted_at: datetime | None = None


# ─── L3 → L4 ────────────────────────────────────────────────────────────────
class ImpactedNode(BaseModel):
    node_id: str
    label: str
    node_type: str
    impact_score: float = Field(ge=0.0, le=1.0)
    eta_days: float = Field(ge=0.0, description="Days until impact materializes")
    hops: int
    confidence: float = Field(ge=0.0, le=1.0)
    path: list[str] = Field(description="node_ids from epicentre to this node")
    explanation: str


class SimulationResult(BaseModel):
    event: DisruptionEvent
    epicentre_node_ids: list[str]
    impacted: list[ImpactedNode] = Field(description="Sorted by impact_score desc")
    unresolved_entities: list[str] = Field(
        default_factory=list, description="Extracted but absent from the graph"
    )
    params: dict[str, float] = Field(description="Propagation params used")
    runtime_ms: float
    degraded: bool = Field(default=False, description="True if any fallback path was taken")
    notes: list[str] = Field(default_factory=list)


# ─── API I/O ────────────────────────────────────────────────────────────────
class SimulateRequest(BaseModel):
    """Exactly one of text / doc_id / event must be provided."""

    text: str | None = Field(default=None, max_length=8000)
    doc_id: str | None = None
    event: DisruptionEvent | None = None
    severity_override: int | None = Field(default=None, ge=1, le=5)
    max_hops: int = Field(default=4, ge=1, le=8)
    decay: float = Field(default=0.75, ge=0.1, le=1.0)
    force_local: bool = Field(
        default=False,
        description=(
            "Consent to run the slow local CPU model (~40 s) after Hugging Face failed. "
            "Without it, an HF outage returns HTTP 424 instead of silently going local."
        ),
    )
