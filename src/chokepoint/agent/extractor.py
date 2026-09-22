"""``ExtractionAgent`` — orchestrates the JSON-enforcement ladder (§7).

    RawDocument
      └─ relevance gate ──────────── drop (ExtractionSkipped, 0 tokens)
      └─ build_messages (layer ②)
      └─ provider.chat  (layer ① when supported)
      └─ parse_event    (layers ③ + ④ + Pydantic)
           ├─ ok  → entity resolution (layer ⑤) → DisruptionEvent
           └─ fail, attempt < max → repair prompt with the exact error text
           └─ fail, attempt = max → _fallback_extract (never raises)

Two entry points share one pipeline (``_extract_from_doc``):

* ``extract(doc)`` — a ``RawDocument`` from ingestion (GDELT / RSS). The
  relevance gate runs, because the firehose is mostly noise.
* ``extract_text(text)`` — free text pasted into ``POST /api/v1/simulate``. A
  ``RawDocument`` is synthesised around it and the gate is skipped by default.

``parse_event``'s ``ValidationError`` / ``JSONDecodeError`` are caught here
and **only** here, purely to drive the retry loop. Provider (network/HTTP)
errors propagate — that is the caller's decision, not ours.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime

from pydantic import HttpUrl, ValidationError

from chokepoint.agent.gate import is_relevant
from chokepoint.agent.parser import parse_event
from chokepoint.agent.prompts import PROMPT_VERSION, build_messages
from chokepoint.agent.providers.base import LLMProvider, Message
from chokepoint.agent.providers.failover import local_fallback_consent
from chokepoint.agent.resolver import resolve_location
from chokepoint.contracts import DisruptionEvent, EventType, ExtractedLocation, RawDocument

log = logging.getLogger(__name__)

FALLBACK_EXTRACTOR_VERSION = "fallback-heuristic-v1"
FALLBACK_CONFIDENCE = 0.25

# Ordered: first matching group wins. Specific before generic.
_EVENT_TYPE_HINTS: list[tuple[EventType, tuple[str, ...]]] = [
    (EventType.STRIKE, ("strike", "walkout", "walk out", "walked out", "work stoppage", "lockout")),
    (EventType.BLOCKADE, ("blockade", "blockaded", "blocked", "protesters block")),
    (EventType.SANCTIONS, ("sanction", "sanctions")),
    (EventType.EXPORT_BAN, ("export ban", "export restriction", "import ban", "embargo")),
    (EventType.CYBERATTACK, ("cyberattack", "cyber attack", "ransomware", "hack")),
    (
        EventType.NATURAL_DISASTER,
        ("earthquake", "hurricane", "typhoon", "flood", "storm", "fog", "wildfire", "drought"),
    ),
    (EventType.CONFLICT, ("missile", "attack", "war", "drone", "military", "houthi")),
    (
        EventType.ACCIDENT,
        (
            "collision",
            "collided",
            "aground",
            "grounding",
            "capsized",
            "fire",
            "explosion",
            "derailment",
            "derailed",
        ),
    ),
    (
        EventType.INFRASTRUCTURE_FAILURE,
        (
            "bridge collapse",
            "outage",
            "power failure",
            "lock failure",
            "crane failure",
            "infrastructure",
        ),
    ),
    (EventType.CONGESTION, ("congestion", "backlog", "queue", "waiting at anchor", "delays")),
]

_SEVERITY_HINTS: list[tuple[int, tuple[str, ...]]] = [
    (5, ("closed indefinitely", "full closure", "halted all", "suspend all", "shut down all")),
    (4, ("closure", "shut", "halt", "suspended", "blockade")),
    (2, ("minor", "brief", "short", "partial", "some delays")),
]


class ExtractionSkipped(Exception):  # noqa: N818 — a control-flow signal, not an error (spec name)
    """Raised when the relevance gate drops the document. Not an error."""


class ExtractionAgent:
    def __init__(
        self,
        provider: LLMProvider,
        alias_index: dict[str, str],
        *,
        max_attempts: int = 3,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._provider = provider
        self._aliases = alias_index
        self._max_attempts = max_attempts
        self._prompt_version = prompt_version
        #: Number of provider calls made by the most recent ``extract``.
        self.last_attempts = 0

    # ── public ────────────────────────────────────────────────────────────
    @property
    def name(self) -> str:
        """Name of the provider currently answering (``hf`` / ``local`` / ``stub``).

        Follows a ``FailoverProvider``'s active side. Exposed so callers that
        only hold the agent (``api/orchestrator.py`` flags ``degraded`` when
        ``llm.name == "stub"``) can still see which backend produced an event.
        """
        return self._provider.name

    def extract(self, doc: RawDocument) -> DisruptionEvent:
        """Extract from a document that came out of the ingestion pipeline.

        Runs the relevance gate: scraped feeds are mostly irrelevant, and the
        gate drops those before a single token is spent (``ExtractionSkipped``).
        """
        return self._extract_from_doc(doc, skip_gate=False)

    def extract_text(
        self, text: str, *, apply_gate: bool = False, force_local: bool = False
    ) -> DisruptionEvent:
        """Ad-hoc entry point for text pasted directly into the API (not from the
        ingestion pipeline).

        Skips the relevance gate by default — a user who explicitly submitted text
        has already made the relevance judgement the gate exists to automate for a
        firehose of scraped articles. Pass ``apply_gate=True`` to opt back in.

        ``force_local=True`` is the user's consent to run the slow local model: a
        consent-mode ``FailoverProvider`` then skips HF and answers locally. Without
        it, an HF outage raises ``PrimaryUnavailableError`` (the API maps it to 424).
        Providers that have no local side ignore the flag.

        ``contracts.RawDocument`` is frozen and requires a ``source`` of ``"gdelt"`` or
        ``"rss"`` and a valid ``url``, so the synthetic document uses ``source="rss"``
        (marked ``source_name="api-adhoc"``) and a placeholder ``chokepoint.local`` URL.

        Raises ``ValueError`` for blank text so an empty request never spends an LLM
        call (free-tier credits are scarce — see docs/PROMPTS.md §3); the API layer
        maps ``ValueError`` to HTTP 422.
        """
        if not text.strip():
            raise ValueError("text must not be empty")
        doc_id = hashlib.sha256(text.encode()).hexdigest()[:16]
        now = datetime.now(UTC)
        doc = RawDocument(
            doc_id=doc_id,
            source="rss",
            source_name="api-adhoc",
            url=HttpUrl(f"https://chokepoint.local/adhoc/{doc_id}"),
            title=text[:120],
            body=text,
            published_at=now,
            fetched_at=now,
        )
        with local_fallback_consent(force_local):
            return self._extract_from_doc(doc, skip_gate=not apply_gate)

    # ── shared pipeline (formerly the body of extract()) ─────────────────
    def _extract_from_doc(self, doc: RawDocument, *, skip_gate: bool = False) -> DisruptionEvent:
        if not skip_gate and not is_relevant(doc):
            raise ExtractionSkipped(doc.doc_id)

        messages = build_messages(doc.title, doc.body, version=self._prompt_version)
        event: DisruptionEvent | None = None
        self.last_attempts = 0
        for attempt in range(1, self._max_attempts + 1):
            self.last_attempts = attempt
            raw = self._provider.chat(messages)
            try:
                event = parse_event(raw)
                break
            except (ValidationError, ValueError) as exc:  # JSONDecodeError is a ValueError
                log.warning(
                    "extraction attempt %d/%d failed validation for %s: %s",
                    attempt,
                    self._max_attempts,
                    doc.doc_id,
                    _one_line(str(exc)),
                )
                messages = [*messages, *self._repair_turns(raw, exc)]

        if event is None:
            log.error(
                "all %d attempts failed for %s; using heuristic fallback",
                self._max_attempts,
                doc.doc_id,
            )
            event = self._fallback_extract(doc)
        else:
            event = event.model_copy(
                update={"extractor_version": f"{self._provider.name}-{self._prompt_version}"}
            )

        return self._finalise(event, doc)

    # ── internals ─────────────────────────────────────────────────────────
    @staticmethod
    def _repair_turns(raw: str, exc: Exception) -> list[Message]:
        return [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    f"Your previous output failed validation:\n{exc}\n"
                    "Return the corrected JSON object only."
                ),
            },
        ]

    def _finalise(self, event: DisruptionEvent, doc: RawDocument) -> DisruptionEvent:
        return event.model_copy(
            update={
                "source_doc_id": doc.doc_id,
                "extracted_at": datetime.now(tz=UTC),
                "locations": [
                    loc.model_copy(
                        update={"node_id": loc.node_id or resolve_location(loc.raw, self._aliases)}
                    )
                    for loc in event.locations
                ],
            }
        )

    def _fallback_extract(self, doc: RawDocument) -> DisruptionEvent:
        """Regex/keyword heuristic — never raises. This is the demo's insurance policy."""
        try:
            return self._heuristic(doc)
        except Exception:  # reliability floor: log and return the minimum viable event
            log.exception(
                "heuristic fallback itself failed for %s; returning minimal event", doc.doc_id
            )
            return DisruptionEvent(
                event_type=EventType.OTHER,
                locations=[ExtractedLocation(raw=(doc.title or "unknown")[:120] or "unknown")],
                severity=2,
                confidence=FALLBACK_CONFIDENCE,
                summary=(doc.title or "Unparsed disruption report")[:280],
                extractor_version=FALLBACK_EXTRACTOR_VERSION,
            )

    def _heuristic(self, doc: RawDocument) -> DisruptionEvent:
        text = f"{doc.title} {doc.body}"
        lowered = text.lower()

        event_type = EventType.OTHER
        for candidate, hints in _EVENT_TYPE_HINTS:
            if _has_any(lowered, hints):
                event_type = candidate
                break

        severity = 3
        for value, hints in _SEVERITY_HINTS:
            if _has_any(lowered, hints):
                severity = value
                break

        locations = _find_aliases(text, self._aliases, prefix=("port_", "chokepoint_"))
        goods = _find_aliases(text, self._aliases, prefix=("com_",))
        loc_models = [
            ExtractedLocation(raw=raw, node_id=node_id) for raw, node_id in locations[:5]
        ] or [ExtractedLocation(raw=(doc.title or "unknown")[:120] or "unknown")]

        summary = (
            f"[heuristic] {doc.title.strip()}"[:280]
            if doc.title.strip()
            else "[heuristic] disruption report"
        )
        return DisruptionEvent(
            event_type=event_type,
            locations=loc_models,
            affected_goods=[raw.lower() for raw, _ in goods[:8]],
            severity=severity,
            confidence=FALLBACK_CONFIDENCE,
            summary=summary,
            extractor_version=FALLBACK_EXTRACTOR_VERSION,
        )


def _find_aliases(
    text: str, alias_index: dict[str, str], *, prefix: tuple[str, ...]
) -> list[tuple[str, str]]:
    """Return ``(verbatim_span, node_id)`` for every alias present in ``text``, longest alias first, one per node."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for alias in sorted(alias_index, key=len, reverse=True):
        node_id = alias_index[alias]
        if node_id in seen or not node_id.startswith(prefix) or len(alias) < 3:
            continue
        m = re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE)
        if m:
            seen.add(node_id)
            out.append((m.group(0), node_id))
    return out


def _has_any(text: str, hints: tuple[str, ...]) -> bool:
    """Word-boundary match so "war" does not fire on "warehouse" or "fire" on "firefighters"."""
    return any(re.search(rf"\b{re.escape(h)}\b", text) for h in hints)


def _one_line(s: str, limit: int = 200) -> str:
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


__all__ = [
    "FALLBACK_CONFIDENCE",
    "FALLBACK_EXTRACTOR_VERSION",
    "ExtractionAgent",
    "ExtractionSkipped",
]
