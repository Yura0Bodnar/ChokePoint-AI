import networkx as nx

from chokepoint.graph.simulator import propagate


def cyclic_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    for node in "ABCD":
        graph.add_node(node, resilience=0.1, substitutes=[])
    graph.add_edge("A", "B", weight=0.8, lead_time_days=1)
    graph.add_edge("B", "C", weight=0.8, lead_time_days=1)
    graph.add_edge("C", "A", weight=0.8, lead_time_days=1)
    graph.add_edge("B", "D", weight=0.6, lead_time_days=2)
    return graph


def test_cyclic_graph_terminates_with_hop_bound() -> None:
    state = propagate(cyclic_graph(), {"A": 0.8}, max_hops=4)
    assert all(node_state.hops <= 4 for node_state in state.values())
    assert set(state) == {"A", "B", "C", "D"}


def test_doubling_epicentre_impact_does_not_decrease_downstream_impact() -> None:
    graph = cyclic_graph()
    low = propagate(graph, {"A": 0.2}, max_hops=4)
    high = propagate(graph, {"A": 0.4}, max_hops=4)
    for node_id in low:
        assert high[node_id].impact >= low[node_id].impact


def test_propagation_is_deterministic() -> None:
    graph = cyclic_graph()
    first = propagate(graph, {"A": 0.8}, max_hops=4)
    second = propagate(graph, {"A": 0.8}, max_hops=4)
    assert first == second
