"""P2.8 acceptance: full extraction with the real local model, no network.

    uv sync --group local
    uv run pytest tests/local -m local -s

First run downloads ~3 GB of weights (needs network + HF_HUB_OFFLINE unset).
Every later run works with the cable unplugged; set HF_HUB_OFFLINE=1 to prove it.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

from chokepoint.agent.extractor import ExtractionAgent
from chokepoint.agent.providers.local_hf import DEFAULT_LOCAL_MODEL, LocalHFProvider
from chokepoint.agent.resolver import load_aliases
from tests.unit.conftest import make_doc

pytestmark = [
    pytest.mark.local,
    pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="uv sync --group local"),
]

DOCS = [
    make_doc(
        "Strike halts operations at Hamburg Port",
        "Dockworkers walked out today at the Port of Hamburg, halting container handling for "
        "48 hours. Carriers warned of delays to automotive parts bound for Poland.",
    ),
    make_doc(
        "Carriers suspend Red Sea transits after new attacks",
        "Maersk and MSC paused all sailings through the Red Sea and the Suez Canal after two "
        "vessels were struck. Ships will round the Cape of Good Hope, adding 10 to 14 days.",
    ),
    make_doc(
        "Fog closes Port of Constanta to inbound traffic",
        "The port authority suspended pilotage on Sunday after visibility dropped below 200 "
        "metres. Around a dozen vessels are waiting at anchor.",
    ),
]


def test_local_model_extracts_valid_events() -> None:
    provider = LocalHFProvider(os.environ.get("LOCAL_MODEL", DEFAULT_LOCAL_MODEL))
    load_s = provider.load()
    agent = ExtractionAgent(provider, load_aliases())
    print(f"\nmodel={provider.model_id} load={load_s:.1f}s")
    rows = []
    for doc in DOCS:
        event = agent.extract(doc)
        rows.append((doc.title, agent.last_attempts, provider.last_latency_seconds, event))
        print(
            f"| {doc.title[:45]} | attempts={agent.last_attempts} | {provider.last_latency_seconds:.1f}s "
            f"| {event.extractor_version} | {event.event_type.value} sev={event.severity} "
            f"| {[(loc.raw, loc.node_id) for loc in event.locations]} | goods={event.affected_goods} |"
        )
    real = [r for r in rows if not r[3].extractor_version.startswith("fallback")]
    assert real, "local model never produced a valid event — fallback fired every time"
    assert any(loc.node_id == "port_hamburg" for loc in rows[0][3].locations)
