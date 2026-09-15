"""News -> LLM -> Graph Overlay -> Simulation orchestration.

A pure function of (request, providers) -> SimulationResult, per
ARCHITECTURE_AND_PLAN.md §3.4. It knows nothing about HTTP; the router
translates its `ValueError` into a 422.
"""

from __future__ import annotations

import time

from chokepoint.api.deps import GraphStore, LLMProvider
from chokepoint.contracts import SimulateRequest, SimulationResult


def run_simulation(
    request: SimulateRequest, *, llm: LLMProvider, graph: GraphStore
) -> SimulationResult:
    start = time.perf_counter()
    notes: list[str] = []

    if request.event is not None:
        event = request.event
    elif request.text is not None:
        event = llm.extract(request.text)
    elif request.doc_id is not None:
        # Day-1 slice has no document store wired in yet (that lands with
        # Person 1's ingestion PR). Fail loudly and clearly rather than guess.
        raise ValueError(f"doc_id lookup is not implemented in this slice: {request.doc_id!r}")
    else:
        raise ValueError("SimulateRequest must supply exactly one of: text, doc_id, event")

    if request.severity_override is not None:
        event = event.model_copy(update={"severity": request.severity_override})

    epicentre_ids = [loc.node_id for loc in event.locations if loc.node_id]
    unresolved = [loc.raw for loc in event.locations if not loc.node_id]

    impacted = graph.simulate(event, max_hops=request.max_hops, decay=request.decay)

    return SimulationResult(
        event=event,
        epicentre_node_ids=epicentre_ids,
        impacted=impacted,
        unresolved_entities=unresolved,
        params={"max_hops": float(request.max_hops), "decay": request.decay},
        runtime_ms=round((time.perf_counter() - start) * 1000, 2),
        degraded=(
            getattr(llm, "name", "") == "stub"
            or getattr(graph, "name", "") == "stub"
            or event.extractor_version.startswith("fallback")
        ),
        notes=notes,
    )
