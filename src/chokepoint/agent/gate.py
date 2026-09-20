"""Relevance gate — keyword prefilter, zero tokens spent on irrelevant docs.

ARCHITECTURE_AND_PLAN.md §7.1 / §11.4 (P2.6): ≥80 % of irrelevant documents
must be dropped *before* any LLM call. Measured in ``tests/unit/test_gate.py``.

Matching is word-boundary aware (``"port"`` must not fire on ``"report"``
or ``"support"``) and tolerates simple plurals (``"vessels"``, ``"tariffs"``).
"""

from __future__ import annotations

import re
from functools import lru_cache

from chokepoint.contracts import RawDocument

LOGISTICS_KEYWORDS: frozenset[str] = frozenset(
    {
        # maritime
        "port",
        "seaport",
        "harbor",
        "harbour",
        "terminal",
        "dockworker",
        "longshoreman",
        "stevedore",
        "shipping",
        "shipping line",
        "carrier",
        "container",
        "vessel",
        "tanker",
        "bulk carrier",
        "cargo",
        "freight",
        "canal",
        "strait",
        "chokepoint",
        "anchorage",
        "pilotage",
        "berth",
        "transshipment",
        "maritime",
        # rail / road / air
        "rail",
        "railway",
        "rail freight",
        "trucking",
        "haulage",
        "border crossing",
        "checkpoint",
        "air cargo",
        "air freight",
        "airport cargo",
        "pipeline",
        # trade policy
        "customs",
        "tariff",
        "embargo",
        "sanctions",
        "export ban",
        "export restriction",
        "import ban",
        "quota",
        "trade war",
        "blockade",
        # events
        "strike",
        "walkout",
        "lockout",
        "work stoppage",
        "congestion",
        "backlog",
        "delay",
        "disruption",
        "closure",
        "shutdown",
        "collision",
        "grounding",
        "capsize",
        "derailment",
        "cyberattack",
        "ransomware",
        # supply chain / industry
        "supply chain",
        "logistics",
        "warehouse",
        "refinery",
        "shipment",
        "exports",
        "imports",
        "commodity",
        "semiconductor",
        "grain corridor",
        "lng",
        "crude",
    }
)


@lru_cache(maxsize=8)
def _compile(keywords: frozenset[str]) -> re.Pattern[str]:
    # Longest-first so multi-word terms win; \b keeps "port" out of "report";
    # an optional trailing s/es catches plurals cheaply.
    alternation = "|".join(re.escape(kw) for kw in sorted(keywords, key=len, reverse=True))
    return re.compile(rf"\b(?:{alternation})(?:e?s)?\b", re.IGNORECASE)


def matched_keywords(text: str, *, keywords: frozenset[str] = LOGISTICS_KEYWORDS) -> list[str]:
    """Distinct lowercase keywords found in ``text`` (useful for logging why a doc passed)."""
    found = {m.group(0).lower() for m in _compile(keywords).finditer(text)}
    return sorted(found)


def is_relevant(doc: RawDocument, *, keywords: frozenset[str] = LOGISTICS_KEYWORDS) -> bool:
    text = f"{doc.title} {doc.body}"
    return _compile(keywords).search(text) is not None


__all__ = ["LOGISTICS_KEYWORDS", "is_relevant", "matched_keywords"]
