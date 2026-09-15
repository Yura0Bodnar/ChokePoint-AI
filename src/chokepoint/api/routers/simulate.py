"""POST /api/v1/simulate — the money endpoint.

See ARCHITECTURE_AND_PLAN.md §9 for the full API surface and §3.4 for the
request lifecycle this route triggers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from chokepoint.api.deps import GraphStore, LLMProvider, get_graph_store, get_llm_provider
from chokepoint.api.orchestrator import run_simulation
from chokepoint.contracts import SimulateRequest, SimulationResult

router = APIRouter(prefix="/api/v1", tags=["simulate"])


@router.post("/simulate", response_model=SimulationResult)
def simulate(
    request: SimulateRequest,
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    graph: Annotated[GraphStore, Depends(get_graph_store)],
) -> SimulationResult:
    try:
        return run_simulation(request, llm=llm, graph=graph)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
