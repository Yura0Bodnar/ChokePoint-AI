from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx

from chokepoint.contracts import DisruptionEvent, ImpactedNode
from chokepoint.graph.loader import load_seed_graph
from chokepoint.graph.simulator import propagate

if TYPE_CHECKING:
    Graph = nx.DiGraph[str, dict[str, Any], dict[str, Any]]


class NetworkXGraphStore:
    def __init__(self, graph: Graph) -> None:
        self._graph = graph

    @classmethod
    def from_seed_dir(cls, seed_dir: Path) -> NetworkXGraphStore:
        return cls(load_seed_graph(seed_dir))

    def get_node(self, node_id: str) -> dict[str, Any]:
        return dict(self._graph.nodes[node_id])

    def neighbors(self, node_id: str) -> list[str]:
        return list(self._graph.successors(node_id))

    def simulate(
        self,
        event: DisruptionEvent,
        *,
        max_hops: int = 4,
        decay: float = 0.75,
        min_impact: float = 0.02,
    ) -> list[ImpactedNode]:
        epicentres = {
            location.node_id: (event.severity / 5)
            * self._graph.nodes[location.node_id].get("criticality", 0.5)
            for location in event.locations
            if location.node_id and location.node_id in self._graph
        }
        if not epicentres:
            return []
        state = propagate(
            self._graph,
            epicentres,
            max_hops=max_hops,
            decay=decay,
            min_impact=min_impact,
        )
        impacted: list[ImpactedNode] = []
        for node_id, node_state in state.items():
            if node_id in epicentres:
                continue
            node = self._graph.nodes[node_id]
            impacted.append(
                ImpactedNode(
                    node_id=node_id,
                    label=node.get("label", node_id),
                    node_type=node.get("type", "unknown"),
                    impact_score=round(node_state.impact, 4),
                    eta_days=node_state.eta,
                    hops=node_state.hops,
                    confidence=round(event.confidence * (0.8**node_state.hops), 4),
                    path=node_state.path,
                    explanation=(
                        f"{' -> '.join(node_state.path)} (weighted propagation, "
                        f"{node_state.hops} hop(s), decay={decay})."
                    ),
                )
            )
        return sorted(impacted, key=lambda node: node.impact_score, reverse=True)
