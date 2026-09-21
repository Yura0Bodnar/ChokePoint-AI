"""Dependency-injection seams for the API layer.

The `LLMProvider` and `GraphStore` Protocols, and their Stub implementations,
are defined locally in this file as an intentional simplification for the
Day-1 vertical slice (see PROMPT_P3_BACKEND_DEVOPS.md Step 3). Person 2 will
move the real `LLMProvider` Protocol into `agent/providers/base.py` and add
`HFInferenceProvider`; Person 1 will implement `NetworkXGraphStore` in
`graph/store.py` against the same method shapes used here. This file's
factory functions (`get_llm_provider`, `get_graph_store`) are then updated,
in their own PRs, to select the real implementation once `settings.llm_provider`
/ `settings.graph_backend` says so. `get_graph_store` now returns the real
`NetworkXGraphStore` (the stub survives as the `DEMO_MODE=true` fallback);
`get_llm_provider` is still the stub until Person 2's agent is wired in.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Protocol

from chokepoint.config import get_settings
from chokepoint.contracts import DisruptionEvent, EventType, ExtractedLocation, ImpactedNode
from chokepoint.graph.store import NetworkXGraphStore

#: The curated YAML graph (nodes.yaml / edges.yaml / SOURCES.md) shipped inside the package.
_SEED_DIR = Path(__file__).resolve().parents[1] / "graph" / "seed"


class LLMProvider(Protocol):
    name: str

    def extract(self, text: str) -> DisruptionEvent: ...


class GraphStore(Protocol):
    def simulate(
        self, event: DisruptionEvent, *, max_hops: int, decay: float
    ) -> list[ImpactedNode]: ...


# ─── Shared placeholder node-id vocabulary ─────────────────────────────────
# These exact ids are used identically across all three foundation branches
# until Person 1's real graph seed lands. Do not invent alternate spellings.
#   port_hamburg            — Port of Hamburg
#   com_auto_parts          — Automotive components (commodity)
#   ind_auto_parts_pl       — Polish automotive components industry
#   mkt_ukraine_aftermarket — Ukrainian automotive aftermarket


class StubLLMProvider:
    """Always returns the same canned event. No network, no cost, deterministic."""

    name = "stub"

    def extract(self, text: str) -> DisruptionEvent:
        return DisruptionEvent(
            event_type=EventType.STRIKE,
            locations=[
                ExtractedLocation(raw="Hamburg Port", node_id="port_hamburg", country_iso2="DE")
            ],
            affected_goods=["electronics", "auto parts"],
            severity=3,
            estimated_duration_days=7,
            confidence=0.5,
            summary="Stub extraction: dockworker strike at Hamburg Port (no LLM called).",
            extractor_version="stub-v0",
        )


class StubGraphStore:
    """Hardcoded 3-hop cascade so /simulate is demoable before the real graph exists."""

    name = "stub"

    _MOCK: ClassVar[list[tuple[str, str, str, float, float, int, list[str]]]] = [
        # node_id, label, node_type, base_impact, eta_days, hops, path
        (
            "com_auto_parts",
            "Automotive components (bulk)",
            "commodity",
            0.34,
            3.0,
            1,
            ["port_hamburg", "com_auto_parts"],
        ),
        (
            "ind_auto_parts_pl",
            "Polish automotive components industry",
            "industry",
            0.21,
            9.0,
            2,
            ["port_hamburg", "com_auto_parts", "ind_auto_parts_pl"],
        ),
        (
            "mkt_ukraine_aftermarket",
            "Ukrainian automotive aftermarket",
            "market",
            0.09,
            15.0,
            3,
            ["port_hamburg", "com_auto_parts", "ind_auto_parts_pl", "mkt_ukraine_aftermarket"],
        ),
    ]

    def simulate(
        self, event: DisruptionEvent, *, max_hops: int = 4, decay: float = 0.75
    ) -> list[ImpactedNode]:
        out: list[ImpactedNode] = []
        for node_id, label, node_type, impact, eta, hops, path in self._MOCK:
            if hops > max_hops:
                continue
            scaled = min(1.0, impact * (event.severity / 3) * decay)
            out.append(
                ImpactedNode(
                    node_id=node_id,
                    label=label,
                    node_type=node_type,
                    impact_score=round(scaled, 4),
                    eta_days=eta,
                    hops=hops,
                    confidence=round(event.confidence * (0.8**hops), 4),
                    path=path,
                    explanation=(
                        f"Mock propagation via {' → '.join(path)} "
                        "(StubGraphStore — no real graph loaded yet)."
                    ),
                )
            )
        return sorted(out, key=lambda n: n.impact_score, reverse=True)


@lru_cache
def get_llm_provider() -> LLMProvider:
    # Always the stub today. Person 2's real provider will read
    # `settings.llm_provider` to choose between hf/local/stub — take that as
    # `Annotated[Settings, Depends(get_settings)]` rather than a bare default
    # (FastAPI otherwise infers a bare `Settings` parameter here as an extra
    # JSON body field on every route that depends on this function). Note
    # too that `Settings` instances are not hashable, so this function can no
    # longer stay `@lru_cache`'d once it takes one — cache on a hashable
    # derived key (e.g. `settings.llm_provider`) instead.
    return StubLLMProvider()


@lru_cache
def get_graph_store() -> GraphStore:
    settings = get_settings()
    if settings.demo_mode:
        # Offline-venue safety net (ARCHITECTURE_AND_PLAN.md §16.1): the canned 3-hop cascade.
        return StubGraphStore()
    if settings.graph_backend != "networkx":
        # `kuzu` is documented in .env.example but not implemented; failing loudly beats
        # silently serving a different backend than the one that was asked for.
        raise ValueError(
            f"unsupported GRAPH_BACKEND={settings.graph_backend!r}; only 'networkx' is implemented"
        )
    return NetworkXGraphStore.from_seed_dir(_SEED_DIR)


__all__ = [
    "GraphStore",
    "LLMProvider",
    "StubGraphStore",
    "StubLLMProvider",
    "get_graph_store",
    "get_llm_provider",
    "get_settings",
]
