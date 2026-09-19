from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import networkx as nx

if TYPE_CHECKING:
    Graph = nx.DiGraph[str, dict[str, Any], dict[str, Any]]


@dataclass
class NodeState:
    impact: float
    eta: float
    hops: int
    path: list[str] = field(default_factory=list)


def substitution_factor(graph: Graph, node_id: str, state: dict[str, NodeState]) -> float:
    """Reduce impact when a node still has healthy substitute nodes."""
    substitutes: list[str] = graph.nodes[node_id].get("substitutes", [])
    if not substitutes:
        return 1.0
    unaffected = sum(1 for substitute in substitutes if substitute not in state)
    return 1.0 - 0.5 * (unaffected / len(substitutes))


def propagate(
    graph: Graph,
    epicentres: dict[str, float],
    *,
    max_hops: int = 4,
    decay: float = 0.75,
    min_impact: float = 0.02,
) -> dict[str, NodeState]:
    """Propagate impact with a deterministic, cycle-safe weighted BFS."""
    state: dict[str, NodeState] = {
        node_id: NodeState(impact=impact, eta=0.0, hops=0, path=[node_id])
        for node_id, impact in epicentres.items()
    }
    frontier: deque[str] = deque(epicentres)
    while frontier:
        source = frontier.popleft()
        source_state = state[source]
        if source_state.hops >= max_hops:
            continue
        for target in graph.successors(source):
            edge = graph.edges[source, target]
            node = graph.nodes[target]
            contribution = source_state.impact * edge["weight"] * decay ** (source_state.hops + 1)
            contribution *= 1.0 - node.get("resilience", 0.0)
            contribution *= substitution_factor(graph, target, state)
            if contribution < min_impact:
                continue
            candidate = NodeState(
                impact=min(1.0, contribution),
                eta=source_state.eta + edge.get("lead_time_days", 0),
                hops=source_state.hops + 1,
                path=[*source_state.path, target],
            )
            previous = state.get(target)
            if previous is None or candidate.impact > previous.impact:
                state[target] = candidate
                frontier.append(target)
    return state
