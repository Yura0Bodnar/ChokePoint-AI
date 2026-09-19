from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx
import yaml

if TYPE_CHECKING:
    Graph = nx.DiGraph[str, dict[str, Any], dict[str, Any]]


class GraphValidationError(ValueError):
    """Raised when the seed graph fails structural validation."""


def load_seed_graph(seed_dir: Path) -> Graph:
    """Load nodes.yaml and edges.yaml into a validated directed graph."""
    nodes = yaml.safe_load((seed_dir / "nodes.yaml").read_text()) or []
    edges = yaml.safe_load((seed_dir / "edges.yaml").read_text()) or []
    graph: Graph = nx.DiGraph()
    for node in nodes:
        node_data = dict(node)
        node_id = node_data.pop("id")
        graph.add_node(node_id, **node_data)
    dangling_errors: list[str] = []
    for edge in edges:
        edge_data = dict(edge)
        source = edge_data.pop("source")
        target = edge_data.pop("target")
        if source not in graph or target not in graph:
            dangling_errors.append(f"dangling edge reference: {source} -> {target}")
            continue
        graph.add_edge(source, target, **edge_data)
    try:
        _validate(graph)
    except GraphValidationError as error:
        dangling_errors.append(str(error))
    if dangling_errors:
        raise GraphValidationError("; ".join(dangling_errors))
    return graph


def _validate(graph: Graph) -> None:
    """Raise one error containing every structural violation in the graph."""
    errors: list[str] = []
    for source, target, attributes in graph.edges(data=True):
        if source not in graph.nodes or target not in graph.nodes:
            errors.append(f"dangling edge reference: {source} -> {target}")
        if source == target:
            errors.append(f"self-loop not allowed: {source} -> {target}")
        weight = attributes.get("weight")
        if not isinstance(weight, int | float) or not 0.0 <= weight <= 1.0:
            errors.append(f"edge weight out of [0,1]: {source} -> {target} = {weight}")
    for node_id, attributes in graph.nodes(data=True):
        for field in ("criticality", "resilience"):
            value: Any = attributes.get(field)
            if not isinstance(value, int | float) or not 0.0 <= value <= 1.0:
                errors.append(f"node {node_id} missing/invalid {field}")
    if errors:
        raise GraphValidationError("; ".join(errors))
