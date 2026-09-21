"""Seed graph: the Suez / Red Sea and Black Sea grain corridors.

Guards the failure mode that made the demo go dead: the LLM resolver emits a node id that
the graph does not contain, and ``simulate()`` silently returns ``[]``. So these tests pin

* the exact ids the Stage 2 plan requires,
* agreement between ``agent/aliases.yaml`` and the graph (with the remaining gaps *named*),
* the evidence bookkeeping (every edge cited, every citation tag defined, derived weights
  tied to the numbers written in ``SOURCES.md``),
* that real epicentres produce real cascades, and
* the Cytoscape.js export the UI will consume.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from chokepoint.agent.resolver import load_aliases
from chokepoint.contracts import DisruptionEvent, EventType, ExtractedLocation, ImpactedNode
from chokepoint.graph.loader import load_seed_graph
from chokepoint.graph.store import NetworkXGraphStore

SEED_DIR = Path(__file__).resolve().parents[2] / "src" / "chokepoint" / "graph" / "seed"

#: Ids prompts/STAGE2_P1_GRAPH_DATA.md requires verbatim (they must equal the alias-map ids).
REQUIRED_IDS = {
    # corridor 2 - Suez / Red Sea
    "chokepoint_suez",
    "chokepoint_red_sea",
    "chokepoint_bosphorus",
    "port_piraeus",
    "com_electronics",
    "com_semiconductors",
    "ind_electronics_eu",
    "mkt_eu_retail",
    # corridor 3 - Black Sea grain
    "port_odesa",
    "port_constanta",
    "com_grain",
}

#: Alias-map ids that still have no graph node. Named, not silently dropped. Remove an entry
#: when its node lands; the equality assertion below fails in both directions on purpose.
KNOWN_GAPS = {
    # corridor 4 (semiconductors / energy) - explicitly out of scope for Stage 2
    "port_gdansk",
    "port_koper",
    "chokepoint_hormuz",
    "chokepoint_panama",
    "chokepoint_malacca",
    "com_steel",
    "com_crude_oil",
    "com_lng",
    # id mismatch: aliases.yaml says ind_auto_de, the graph node is ind_auto_parts_de
    "ind_auto_de",
}

#: Epicentres of the two new corridors that an LLM headline can realistically resolve to.
SCOPED_EPICENTRES = [
    "chokepoint_suez",
    "chokepoint_red_sea",
    "chokepoint_bosphorus",
    "port_odesa",
    "port_constanta",
    "port_piraeus",
    "route_black_sea",
    "com_semiconductors",
]
MAJOR_EPICENTRES = [
    "chokepoint_suez",
    "chokepoint_red_sea",
    "chokepoint_bosphorus",
    "port_odesa",
    "route_black_sea",
]

_EDGE_LINE = re.compile(r"^([a-z0-9_]+)->([a-z0-9_]+): (.+)$")
_TAG = re.compile(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+\b")


@pytest.fixture(scope="module")
def graph() -> Any:
    return load_seed_graph(SEED_DIR)


@pytest.fixture(scope="module")
def store() -> NetworkXGraphStore:
    return NetworkXGraphStore.from_seed_dir(SEED_DIR)


def simulate(store: NetworkXGraphStore, node_id: str, severity: int) -> list[ImpactedNode]:
    event = DisruptionEvent(
        event_type=EventType.BLOCKADE,
        locations=[ExtractedLocation(raw=node_id, node_id=node_id)],
        severity=severity,
        confidence=0.9,
        summary="test",
    )
    return store.simulate(event)


def weight(graph: Any, source: str, target: str) -> float:
    return float(graph.edges[source, target]["weight"])


# ══════════════════════════════════════════════════════════════════════════
# Ids and structure
# ══════════════════════════════════════════════════════════════════════════
def test_required_ids_exist_in_the_graph(graph: Any) -> None:
    assert set(graph.nodes) >= REQUIRED_IDS, sorted(REQUIRED_IDS - set(graph.nodes))


def test_alias_ids_exist_in_the_graph_except_the_named_gaps(graph: Any) -> None:
    alias_ids = set(load_aliases().values())
    missing = alias_ids - set(graph.nodes)
    assert missing == KNOWN_GAPS, (
        f"alias ids without a graph node: {sorted(missing - KNOWN_GAPS)} (add the node, or name "
        f"the gap in KNOWN_GAPS); gaps now closed: {sorted(KNOWN_GAPS - missing)} (remove them)"
    )


def test_substitutes_reference_existing_nodes(graph: Any) -> None:
    for node_id, attributes in graph.nodes(data=True):
        for substitute in attributes.get("substitutes", []):
            assert substitute in graph, f"{node_id} lists unknown substitute {substitute!r}"


def test_no_node_is_isolated(graph: Any) -> None:
    assert [node for node in graph if graph.degree(node) == 0] == []


def test_node_labels_are_short_enough_for_the_graph_view(graph: Any) -> None:
    # Regression: 60+ character labels made the Cytoscape layout shrink a 5-wide cascade until its
    # text was unreadable. The longest label of the original corridor is 38 characters.
    too_long = {n: a["label"] for n, a in graph.nodes(data=True) if len(a["label"]) > 40}
    assert not too_long, too_long


def test_new_corridors_are_connected_to_the_existing_north_sea_graph(graph: Any) -> None:
    # A Suez event must be able to reach corridor-1 nodes (the cross-corridor cascade).
    assert graph.has_edge("chokepoint_suez", "com_containers")
    assert graph.has_edge("com_semiconductors", "ind_auto_parts_de")
    assert graph.has_edge("mkt_eu_retail", "mkt_cee_retail")


# ══════════════════════════════════════════════════════════════════════════
# Evidence bookkeeping
# ══════════════════════════════════════════════════════════════════════════
def _sources_text() -> str:
    return (SEED_DIR / "SOURCES.md").read_text(encoding="utf-8")


def test_every_edge_has_a_citation(graph: Any) -> None:
    for source, target, attributes in graph.edges(data=True):
        ref = attributes.get("source_ref")
        assert isinstance(ref, str) and ref.strip(), f"{source}->{target} has no source_ref"


def test_sources_md_has_exactly_one_line_per_edge(graph: Any) -> None:
    cited = [
        m.group(1, 2) for line in _sources_text().splitlines() if (m := _EDGE_LINE.match(line))
    ]
    assert len(cited) == len(set(cited)), "duplicate edge line in SOURCES.md"
    assert set(cited) == set(graph.edges), (
        f"edges without a SOURCES.md line: {sorted(set(graph.edges) - set(cited))}; "
        f"stale SOURCES.md lines: {sorted(set(cited) - set(graph.edges))}"
    )


def test_citation_tags_are_defined_and_used(graph: Any) -> None:
    defined = set(re.findall(r"^- \*\*([A-Z0-9-]+)\*\*", _sources_text(), re.M))
    assert defined, "SOURCES.md defines no reference tags"
    used: set[str] = set()
    for source, target, attributes in graph.edges(data=True):
        ref: str = attributes["source_ref"]
        if "Weight " not in ref:  # only the Stage 2 edges use the tagged format
            continue
        tags = set(_TAG.findall(ref))
        if ref.startswith("Structural link."):
            # The honest label for "no dataset backs this strength": it must not cite one.
            assert not tags, f"{source}->{target}: structural link cites {sorted(tags)}"
            continue
        assert tags, f"{source}->{target}: edge cites no reference tag"
        assert tags <= defined, f"{source}->{target} cites undefined tags {sorted(tags - defined)}"
        used |= tags
    assert defined <= used, f"references defined but cited by no edge: {sorted(defined - used)}"


def test_derived_weights_match_the_calculations_in_sources_md(graph: Any) -> None:
    # Ukraine 10% of (Russia 15% + Ukraine 10%) world wheat exports, FAO-2023.
    assert weight(graph, "port_odesa", "com_grain") == pytest.approx(10 / 25)
    # Mean of the 2021 and 2022 shares of wheat imports from Russia+Ukraine, FAO-2023 figs 26-27.
    assert weight(graph, "com_grain", "mkt_egypt_wheat") == pytest.approx((0.78 + 0.66) / 2)
    assert weight(graph, "com_grain", "ind_milling_tr") == pytest.approx((0.88 + 0.94) / 2)
    # 1 - 69% seaborne share in 2022 = 31%, rounded, USDA-2023.
    assert weight(graph, "route_solidarity_lanes", "com_grain") == pytest.approx(0.31, abs=0.02)


def test_the_rail_channel_out_of_piraeus_is_weighted_as_marginal(graph: Any) -> None:
    # SASAC-2024 vs COSCO-2023: ~180,000 TEU by rail vs 4,352,100 TEU at the terminal = ~4%.
    for target in ("ind_logistics_cee", "mkt_cee_retail"):
        assert 0.10 <= weight(graph, "route_land_sea_express", target) < 0.25
    # ...while the line itself is entirely a Piraeus product.
    assert weight(graph, "port_piraeus", "route_land_sea_express") >= 0.80


def test_air_skewed_goods_are_weighted_below_sea_skewed_goods(graph: Any) -> None:
    # EUROSTAT-MODE-2023: air = 17.4% of import value but 0.2% of tonnage (high unit value).
    for chokepoint in ("chokepoint_suez", "chokepoint_red_sea"):
        semis = weight(graph, chokepoint, "com_semiconductors")
        electronics = weight(graph, chokepoint, "com_electronics")
        machinery = weight(graph, chokepoint, "com_machinery")
        assert semis < electronics < machinery


# ══════════════════════════════════════════════════════════════════════════
# Real cascades (the point of the whole exercise)
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("node_id", SCOPED_EPICENTRES)
@pytest.mark.parametrize("severity", [2, 3, 4, 5])
def test_scoped_epicentres_produce_a_cascade(
    store: NetworkXGraphStore, graph: Any, node_id: str, severity: int
) -> None:
    impacted = simulate(store, node_id, severity)
    assert impacted, f"{node_id} at severity {severity} silently returned nothing"
    scores = [node.impact_score for node in impacted]
    assert scores == sorted(scores, reverse=True)
    for node in impacted:
        assert node.node_id in graph
        assert 0.0 < node.impact_score <= 1.0
        assert node.path[0] == node_id
        assert node.path[-1] == node.node_id
        assert len(node.path) == node.hops + 1
        assert " -> ".join(node.path) in node.explanation  # the explanation is the real path


@pytest.mark.parametrize("node_id", MAJOR_EPICENTRES)
def test_major_chokepoints_stay_non_empty_at_the_slider_minimum(
    store: NetworkXGraphStore, node_id: str
) -> None:
    assert simulate(store, node_id, 1)  # the UI slider goes down to severity 1


@pytest.mark.parametrize("node_id", SCOPED_EPICENTRES)
def test_impact_never_decreases_with_severity(store: NetworkXGraphStore, node_id: str) -> None:
    by_severity = {
        severity: {n.node_id: n.impact_score for n in simulate(store, node_id, severity)}
        for severity in range(1, 6)
    }
    for low, high in zip(range(1, 5), range(2, 6), strict=True):
        for target, score in by_severity[low].items():
            assert target in by_severity[high], f"{target} vanished as severity rose"
            assert by_severity[high][target] >= score


def test_suez_blockade_cascades_into_industry_retail_and_the_north_sea(
    store: NetworkXGraphStore,
) -> None:
    ids = {n.node_id for n in simulate(store, "chokepoint_suez", 5)}
    assert {
        "port_piraeus",
        "com_electronics",
        "com_machinery",
        "com_semiconductors",
        "ind_electronics_eu",
        "mkt_eu_retail",
        "com_containers",  # corridor 1 node: the cross-corridor link
    } <= ids


def test_red_sea_event_hits_suez_first(store: NetworkXGraphStore) -> None:
    impacted = simulate(store, "chokepoint_red_sea", 4)
    assert impacted[0].node_id == "chokepoint_suez"
    # Calibration (SOURCES.md): the IMF saw Suez volume fall 50% in the real Red Sea campaign.
    assert 0.3 <= impacted[0].impact_score <= 0.5


def test_odesa_strike_reaches_ukrainian_farms_and_egyptian_wheat(store: NetworkXGraphStore) -> None:
    impacted = simulate(store, "port_odesa", 4)
    ids = [n.node_id for n in impacted]
    assert {
        "com_grain",
        "ind_agri_ua",
        "ind_milling_tr",
        "mkt_egypt_wheat",
        "mkt_mena_food",
    } <= set(ids)
    assert ids[0] == "ind_agri_ua"  # the producers behind the port are the most exposed


def test_bosphorus_closure_reaches_global_food_prices(store: NetworkXGraphStore) -> None:
    ids = {n.node_id for n in simulate(store, "chokepoint_bosphorus", 4)}
    assert {"com_grain", "mkt_egypt_wheat", "mkt_global_food"} <= ids


def test_a_semiconductor_shortage_reaches_german_auto_parts(store: NetworkXGraphStore) -> None:
    ids = {n.node_id for n in simulate(store, "com_semiconductors", 5)}
    assert {"ind_electronics_eu", "ind_auto_parts_de"} <= ids  # EC-CHIPS: "from cars to..."


def test_simulation_is_deterministic(store: NetworkXGraphStore) -> None:
    first = [n.model_dump() for n in simulate(store, "chokepoint_suez", 5)]
    second = [n.model_dump() for n in simulate(store, "chokepoint_suez", 5)]
    assert first == second


def test_a_node_the_graph_does_not_contain_returns_an_empty_cascade(
    store: NetworkXGraphStore,
) -> None:
    # The documented failure mode: unknown ids are ignored, not an error. (The alias/graph
    # agreement test above is what keeps real ids from landing here.)
    assert simulate(store, "port_atlantis", 5) == []


# ══════════════════════════════════════════════════════════════════════════
# Cytoscape.js export
# ══════════════════════════════════════════════════════════════════════════
NODE_KEYS = {"id", "label", "type", "country", "criticality", "resilience"}
EDGE_KEYS = {"id", "source", "target", "type", "weight", "lead_time_days", "source_ref"}


def test_cytoscape_elements_have_the_shape_cytoscape_js_expects(
    store: NetworkXGraphStore, graph: Any
) -> None:
    elements = store.to_cytoscape_elements()

    assert set(elements) == {"nodes", "edges"}
    assert len(elements["nodes"]) == graph.number_of_nodes()
    assert len(elements["edges"]) == graph.number_of_edges()
    for element in [*elements["nodes"], *elements["edges"]]:
        assert set(element) == {"data"}
        assert isinstance(element["data"], dict)

    node_ids = [node["data"]["id"] for node in elements["nodes"]]
    assert len(set(node_ids)) == len(node_ids)
    for node in elements["nodes"]:
        data = node["data"]
        assert set(data) >= NODE_KEYS
        assert "substitutes" not in data  # meaningless to a renderer
        assert "source" not in data and "target" not in data  # would turn a node into an edge

    edge_ids = [edge["data"]["id"] for edge in elements["edges"]]
    assert len(set(edge_ids)) == len(edge_ids)
    for edge in elements["edges"]:
        data = edge["data"]
        assert set(data) >= EDGE_KEYS
        assert data["source"] in node_ids and data["target"] in node_ids  # no dangling edge
        assert data["id"] == f"{data['source']}__{data['target']}"  # same scheme as web/app.js


def test_cytoscape_elements_are_pure_json(store: NetworkXGraphStore) -> None:
    elements = store.to_cytoscape_elements()
    encoded = json.dumps(elements, allow_nan=False)  # allow_nan=False: no NaN/Infinity
    assert json.loads(encoded) == elements


def test_cytoscape_elements_include_the_new_corridors(store: NetworkXGraphStore) -> None:
    elements = store.to_cytoscape_elements()
    node_ids = {node["data"]["id"] for node in elements["nodes"]}
    edge_ids = {edge["data"]["id"] for edge in elements["edges"]}
    assert node_ids >= REQUIRED_IDS
    assert {"chokepoint_suez__com_electronics", "port_odesa__com_grain"} <= edge_ids


def test_cytoscape_elements_are_copies_not_views(store: NetworkXGraphStore, graph: Any) -> None:
    elements = store.to_cytoscape_elements()
    elements["nodes"][0]["data"]["criticality"] = -1
    elements["edges"][0]["data"]["weight"] = -1
    del elements["nodes"][1]

    fresh = store.to_cytoscape_elements()
    assert fresh["nodes"][0]["data"]["criticality"] != -1
    assert fresh["edges"][0]["data"]["weight"] != -1
    assert len(fresh["nodes"]) == graph.number_of_nodes()  # the deleted element is back
    assert store.get_node(fresh["nodes"][0]["data"]["id"])["criticality"] != -1
