"""Dependency-injection seams for the API layer.

`LLMProvider` and `GraphStore` are the two Protocols the orchestrator depends on, so the
API never imports a concrete implementation. `get_llm_provider` builds the real
`ExtractionAgent` from `settings.llm_provider` (hf | local | stub) via
`build_extraction_agent`; `get_graph_store` returns the NetworkX graph engine, or the
canned `StubGraphStore` cascade when `DEMO_MODE=true`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Protocol

from chokepoint.agent.providers.factory import build_extraction_agent
from chokepoint.config import get_settings
from chokepoint.contracts import DisruptionEvent, ImpactedNode
from chokepoint.graph.store import NetworkXGraphStore

#: The curated YAML graph (nodes.yaml / edges.yaml / SOURCES.md) shipped inside the package.
_SEED_DIR = Path(__file__).resolve().parents[1] / "graph" / "seed"


class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...

    def extract_text(self, text: str, *, force_local: bool = False) -> DisruptionEvent: ...


class GraphStore(Protocol):
    def simulate(
        self, event: DisruptionEvent, *, max_hops: int, decay: float
    ) -> list[ImpactedNode]: ...


# ─── StubGraphStore vocabulary ─────────────────────────────────────────────
# The DEMO_MODE cascade below uses these node ids from the seed graph:
#   port_hamburg            — Port of Hamburg
#   com_auto_parts          — Automotive components (commodity)
#   ind_auto_parts_pl       — Polish automotive components industry
#   mkt_ukraine_aftermarket — Ukrainian automotive aftermarket


class StubGraphStore:
    """Hardcoded 3-hop cascade: the offline `DEMO_MODE=true` fallback (no real graph needed)."""

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
                        "(StubGraphStore — canned DEMO_MODE cascade)."
                    ),
                )
            )
        return sorted(out, key=lambda n: n.impact_score, reverse=True)


@lru_cache
def get_llm_provider() -> LLMProvider:
    return build_extraction_agent(get_settings())


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
    "get_graph_store",
    "get_llm_provider",
    "get_settings",
]
