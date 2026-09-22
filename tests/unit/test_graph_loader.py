from pathlib import Path

import pytest

from chokepoint.graph.loader import GraphValidationError, load_seed_graph


def write_seed(tmp_path: Path, nodes: str, edges: str) -> Path:
    (tmp_path / "nodes.yaml").write_text(nodes)
    (tmp_path / "edges.yaml").write_text(edges)
    return tmp_path


def test_load_seed_graph_preserves_node_and_edge_attributes(tmp_path: Path) -> None:
    seed_dir = write_seed(
        tmp_path,
        "- id: A\n  criticality: 0.8\n  resilience: 0.2\n"
        "- id: B\n  criticality: 0.5\n  resilience: 0.3\n",
        "- source: A\n  target: B\n  weight: 0.4\n",
    )
    graph = load_seed_graph(seed_dir)
    assert graph.nodes["A"]["criticality"] == 0.8
    assert graph.edges["A", "B"]["weight"] == 0.4


def test_validation_reports_all_violations(tmp_path: Path) -> None:
    seed_dir = write_seed(
        tmp_path,
        "- id: A\n  criticality: 2\n  resilience: 0.2\n",
        "- source: A\n  target: A\n  weight: -1\n- source: A\n  target: missing\n  weight: 2\n",
    )
    with pytest.raises(GraphValidationError) as error:
        load_seed_graph(seed_dir)
    message = str(error.value)
    assert "self-loop" in message
    assert "out of [0,1]" in message
    assert "missing/invalid criticality" in message
