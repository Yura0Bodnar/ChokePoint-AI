"""Golden-set extraction quality (P2.5) — ``ARCHITECTURE_AND_PLAN.md`` §11.4.

Scores the extraction ladder against ``tests/fixtures/golden_events.json`` (20
hand-written, realistic headlines, each paired with the ``DisruptionEvent`` a perfect
extractor would produce) on five metrics:

* **event_type**  — exact match rate
* **location F1** — over *resolved node ids* (raw span when the place is not in the
  alias map), macro-averaged over cases
* **goods F1**    — over canonicalised commodities ("wheat" == "corn" == ``com_grain``),
  macro-averaged; also reported over only the cases that expect goods, because an empty
  prediction scores 1.0 against an empty expectation and would otherwise inflate it
* **severity MAE** — mean absolute error on the 1-5 scale
* **valid-JSON rate** — share of cases where the *model* produced a schema-valid event
  within the attempt cap, i.e. without falling back to the keyword heuristic

Three ways to run it — read what each one actually measures:

| mode        | provider                     | measures                                          | runs in CI |
|-------------|------------------------------|---------------------------------------------------|------------|
| ``oracle``  | stub replaying the *expected* answer | the pipeline (parse → validate → resolve) and the scoring math — **not** a model | yes |
| ``heuristic`` | stub that always emits garbage | the keyword fallback ("insurance policy") on the real golden headlines | yes |
| ``live`` / ``local`` | real HF / local model | real model quality — **spends credits / CPU time** | no (``-m live`` / ``-m local``) |

CI never calls a real LLM, so the default run is a regression gate for the pipeline and
the fallback, *not* a model-accuracy number. The real-model tests are deliberately capped
(``EVAL_LIVE_LIMIT`` / ``EVAL_LOCAL_LIMIT``, default 3 cases, one attempt each) because the
free HF tier allows only ~6 calls a month (docs/PROMPTS.md §3).
"""

from __future__ import annotations

import importlib.util
import json
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from huggingface_hub.errors import HfHubHTTPError

from chokepoint.agent.extractor import ExtractionAgent
from chokepoint.agent.gate import is_relevant
from chokepoint.agent.prompts import FEW_SHOT_V1, PROMPT_VERSION
from chokepoint.agent.providers.factory import build_extraction_agent
from chokepoint.agent.providers.stub import StubLLMProvider
from chokepoint.agent.resolver import load_aliases, normalise, resolve_goods, resolve_location
from chokepoint.config import Settings
from chokepoint.contracts import DisruptionEvent, EventType
from tests.unit.conftest import make_doc

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "golden_events.json"
SEED_DIR = Path(__file__).resolve().parents[2] / "src" / "chokepoint" / "graph" / "seed"

Case = dict[str, Any]


def load_golden() -> list[Case]:
    cases: list[Case] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return cases


# ══════════════════════════════════════════════════════════════════════════
# Scoring (pure functions — unit-tested at the bottom of this file)
# ══════════════════════════════════════════════════════════════════════════
def f1(expected: set[str], predicted: set[str]) -> float:
    """Set F1. Two empty sets score 1.0: correctly predicting "nothing" is a hit."""
    if not expected and not predicted:
        return 1.0
    true_positives = len(expected & predicted)
    if true_positives == 0:
        return 0.0
    precision = true_positives / len(predicted)
    recall = true_positives / len(expected)
    return 2 * precision * recall / (precision + recall)


def location_keys(locations: Iterable[tuple[str, str | None]]) -> set[str]:
    """Resolved node id when there is one, else the normalised raw span."""
    return {f"id:{node_id}" if node_id else f"raw:{normalise(raw)}" for raw, node_id in locations}


def goods_keys(goods: Iterable[str], aliases: dict[str, str]) -> set[str]:
    """Canonical commodity id when the alias map knows it ("wheat" -> ``com_grain``)."""
    keys: set[str] = set()
    for good in goods:
        node_id = resolve_goods(good, aliases)
        keys.add(f"id:{node_id}" if node_id else f"raw:{normalise(good)}")
    return keys


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    expected_type: str
    got_type: str
    location_f1: float
    goods_f1: float
    expects_goods: bool
    severity_error: int
    attempts: int
    fell_back: bool

    @property
    def event_type_ok(self) -> bool:
        return self.expected_type == self.got_type


def score_case(
    case: Case, event: DisruptionEvent, attempts: int, aliases: dict[str, str]
) -> CaseScore:
    expected = case["expected"]
    return CaseScore(
        case_id=case["id"],
        expected_type=expected["event_type"],
        got_type=event.event_type.value,
        location_f1=f1(
            location_keys((loc["raw"], loc["node_id"]) for loc in expected["locations"]),
            location_keys((loc.raw, loc.node_id) for loc in event.locations),
        ),
        goods_f1=f1(
            goods_keys(expected["affected_goods"], aliases),
            goods_keys(event.affected_goods, aliases),
        ),
        expects_goods=bool(expected["affected_goods"]),
        severity_error=abs(event.severity - expected["severity"]),
        attempts=attempts,
        fell_back=event.extractor_version.startswith("fallback"),
    )


@dataclass(frozen=True)
class Report:
    label: str
    n: int
    event_type_accuracy: float
    location_f1: float
    goods_f1: float
    goods_f1_with_goods: float
    severity_mae: float
    valid_json_rate: float
    first_attempt_rate: float
    provider_calls: int
    misses: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def render(self) -> str:
        subtitle = f"{self.n} cases, prompt {PROMPT_VERSION}"
        rows = [
            ("event_type exact match", f"{self.event_type_accuracy:.1%}"),
            ("location F1 (node ids)", f"{self.location_f1:.3f}"),
            ("goods F1 (all cases)", f"{self.goods_f1:.3f}"),
            ("goods F1 (cases with goods)", f"{self.goods_f1_with_goods:.3f}"),
            ("severity MAE (1-5 scale)", f"{self.severity_mae:.2f}"),
            ("valid-JSON rate (no fallback)", f"{self.valid_json_rate:.1%}"),
            ("  ...on the first attempt", f"{self.first_attempt_rate:.1%}"),
            ("provider calls", str(self.provider_calls)),
        ]
        width = max(len(name) for name, _ in rows)
        lines = [f"[{self.label}]  ({subtitle})"]
        lines += [f"  {name:<{width}}  {value:>7}" for name, value in rows]
        if self.misses:
            lines.append("  misses:")
            lines += [f"    - {miss}" for miss in self.misses[:10]]
            if len(self.misses) > 10:
                lines.append(f"    - ... and {len(self.misses) - 10} more")
        lines += [f"  note: {note}" for note in self.notes]
        return "\n".join(lines)


def summarise(label: str, scores: Sequence[CaseScore], *, notes: Sequence[str] = ()) -> Report:
    if not scores:
        raise ValueError("cannot summarise zero cases")
    n = len(scores)
    with_goods = [s for s in scores if s.expects_goods]
    misses = [
        f"{s.case_id}: expected {s.expected_type}, got {s.got_type}"
        for s in scores
        if not s.event_type_ok
    ] + [
        f"{s.case_id}: location F1 {s.location_f1:.2f}"
        for s in scores
        if s.event_type_ok and s.location_f1 < 1.0
    ]
    return Report(
        label=label,
        n=n,
        event_type_accuracy=sum(s.event_type_ok for s in scores) / n,
        location_f1=sum(s.location_f1 for s in scores) / n,
        goods_f1=sum(s.goods_f1 for s in scores) / n,
        goods_f1_with_goods=(sum(s.goods_f1 for s in with_goods) / len(with_goods))
        if with_goods
        else 1.0,
        severity_mae=sum(s.severity_error for s in scores) / n,
        valid_json_rate=sum(not s.fell_back for s in scores) / n,
        first_attempt_rate=sum(s.attempts == 1 and not s.fell_back for s in scores) / n,
        provider_calls=sum(s.attempts for s in scores),
        misses=tuple(misses),
        notes=tuple(notes),
    )


# ══════════════════════════════════════════════════════════════════════════
# Running the agent over the golden set
# ══════════════════════════════════════════════════════════════════════════
def evaluate(
    label: str,
    cases: Sequence[Case],
    agent_for: Callable[[Case], ExtractionAgent],
    *,
    notes: Sequence[str] = (),
) -> Report:
    aliases = load_aliases()
    scores = []
    for case in cases:
        agent = agent_for(case)
        # Through extract(doc), like the ingestion pipeline: a golden headline the
        # relevance gate drops raises ExtractionSkipped here — a real regression.
        event = agent.extract(make_doc(case["title"], case["body"], doc_id=case["id"]))
        scores.append(score_case(case, event, agent.last_attempts, aliases))
    return summarise(label, scores, notes=notes)


def oracle_response(case: Case) -> str:
    """What a *perfect* model would emit for ``case`` (node ids left to layer ⑤)."""
    expected = case["expected"]
    return json.dumps(
        {
            "event_type": expected["event_type"],
            "locations": [
                {"raw": loc["raw"], "node_id": None, "country_iso2": None}
                for loc in expected["locations"]
            ],
            "affected_goods": expected["affected_goods"],
            "severity": expected["severity"],
            "estimated_duration_days": None,
            "confidence": 0.9,
            "summary": case["title"][:280],
        }
    )


def graph_coverage_note(cases: Sequence[Case]) -> str:
    """How many golden cases the *current* seed graph can actually simulate."""
    try:
        from chokepoint.graph.loader import load_seed_graph

        graph_ids = set(load_seed_graph(SEED_DIR).nodes)
    except Exception as exc:  # informational only — never fail the eval on graph problems
        return f"graph coverage unavailable ({type(exc).__name__}: {exc})"
    wanted = {
        loc["node_id"] for case in cases for loc in case["expected"]["locations"] if loc["node_id"]
    }
    simulatable = sum(
        any(loc["node_id"] in graph_ids for loc in case["expected"]["locations"]) for case in cases
    )
    return (
        f"seed graph has {len(wanted & graph_ids)}/{len(wanted)} of the expected epicentre ids; "
        f"{simulatable}/{len(cases)} golden cases would produce a non-empty simulation today "
        "(Person 1's corridor expansion raises this)"
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. Scoring math
# ══════════════════════════════════════════════════════════════════════════
def test_f1_edge_cases() -> None:
    assert f1({"a", "b"}, {"a", "b"}) == 1.0
    assert f1({"a", "b"}, {"a", "c"}) == pytest.approx(0.5)
    assert f1({"a"}, set()) == 0.0
    assert f1(set(), {"a"}) == 0.0
    assert f1(set(), set()) == 1.0  # correctly predicting "no goods" is a hit
    assert f1({"a", "b", "c"}, {"a"}) == pytest.approx(0.5)  # P=1, R=1/3


def test_location_keys_prefer_node_id_then_normalised_raw() -> None:
    keys = location_keys([("Port of Hamburg", "port_hamburg"), ("  Valencia. ", None)])
    assert keys == {"id:port_hamburg", "raw:valencia"}
    # two spellings that resolve to the same node collapse into one key
    assert location_keys(
        [("Red Sea", "chokepoint_red_sea"), ("Bab el-Mandeb", "chokepoint_red_sea")]
    ) == {"id:chokepoint_red_sea"}


def test_goods_keys_canonicalise_synonyms() -> None:
    aliases = load_aliases()
    assert (
        goods_keys(["wheat", "corn"], aliases) == goods_keys(["grain"], aliases) == {"id:com_grain"}
    )
    assert goods_keys(["chemicals"], aliases) == {"raw:chemicals"}  # unknown to the alias map


def _score(case_id: str, **kw: Any) -> CaseScore:
    base: dict[str, Any] = {
        "case_id": case_id,
        "expected_type": "strike",
        "got_type": "strike",
        "location_f1": 1.0,
        "goods_f1": 1.0,
        "expects_goods": True,
        "severity_error": 0,
        "attempts": 1,
        "fell_back": False,
    }
    return CaseScore(**{**base, **kw})


def test_summarise_aggregates_every_metric() -> None:
    report = summarise(
        "t",
        [
            _score("a"),
            _score("b", got_type="conflict", location_f1=0.5, goods_f1=0.0, severity_error=2),
            _score("c", expects_goods=False, attempts=3, fell_back=True, severity_error=1),
            _score("d", attempts=2),
        ],
    )
    assert report.n == 4
    assert report.event_type_accuracy == pytest.approx(3 / 4)
    assert report.location_f1 == pytest.approx((1 + 0.5 + 1 + 1) / 4)
    assert report.goods_f1 == pytest.approx((1 + 0 + 1 + 1) / 4)
    assert report.goods_f1_with_goods == pytest.approx((1 + 0 + 1) / 3)  # 'c' excluded
    assert report.severity_mae == pytest.approx((0 + 2 + 1 + 0) / 4)
    assert report.valid_json_rate == pytest.approx(3 / 4)  # 'c' fell back
    assert report.first_attempt_rate == pytest.approx(1 / 2)  # a and b succeeded on attempt 1
    assert report.provider_calls == 1 + 1 + 3 + 2
    assert any("b: expected strike, got conflict" in miss for miss in report.misses)


def test_summarise_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="zero cases"):
        summarise("t", [])


# ══════════════════════════════════════════════════════════════════════════
# 2. Golden-set integrity — the fixture is a contract, guard it
# ══════════════════════════════════════════════════════════════════════════
def test_golden_set_is_20_diverse_cases() -> None:
    cases = load_golden()
    assert len(cases) == 20
    assert len({case["id"] for case in cases}) == 20
    assert {case["expected"]["event_type"] for case in cases} == {e.value for e in EventType}
    assert all(1 <= case["expected"]["severity"] <= 5 for case in cases)
    assert all(case["expected"]["locations"] for case in cases)  # DisruptionEvent needs >= 1
    assert any(len(case["expected"]["locations"]) > 1 for case in cases)  # multi-location
    assert any(not case["expected"]["affected_goods"] for case in cases)  # empty goods
    assert any(
        loc["node_id"] is None for case in cases for loc in case["expected"]["locations"]
    )  # a place the alias map does not know


def test_golden_locations_resolve_through_the_alias_map() -> None:
    # Regression gate on aliases.yaml: if an alias is renamed or dropped, this names the case.
    aliases = load_aliases()
    for case in load_golden():
        for loc in case["expected"]["locations"]:
            assert resolve_location(loc["raw"], aliases) == loc["node_id"], (case["id"], loc)


def test_golden_spans_are_verbatim_in_the_article() -> None:
    for case in load_golden():
        text = f"{case['title']} {case['body']}".lower()
        for loc in case["expected"]["locations"]:
            assert loc["raw"].lower() in text, (case["id"], loc["raw"])
        for good in case["expected"]["affected_goods"]:
            assert good.lower() in text or good.lower().rstrip("s") in text, (case["id"], good)


def test_golden_headlines_pass_the_relevance_gate() -> None:
    for case in load_golden():
        assert is_relevant(make_doc(case["title"], case["body"])), case["id"]


def test_golden_set_does_not_reuse_the_prompts_few_shot_examples() -> None:
    # A golden headline that is also a few-shot example measures memorisation, not skill.
    few_shot_text = " ".join(user for user, _assistant in FEW_SHOT_V1)
    for case in load_golden():
        assert case["title"] not in few_shot_text, case["id"]


# ══════════════════════════════════════════════════════════════════════════
# 3. CI-safe modes: oracle (pipeline) and heuristic (fallback baseline)
# ══════════════════════════════════════════════════════════════════════════
def test_oracle_pipeline_preserves_every_golden_event(eval_reports: list[object]) -> None:
    cases = load_golden()
    aliases = load_aliases()

    def agent_for(case: Case) -> ExtractionAgent:
        return ExtractionAgent(StubLLMProvider.from_strings([oracle_response(case)]), aliases)

    report = evaluate(
        "oracle: stub replays the expected answer -> pipeline + scoring self-check, NOT a model score",
        cases,
        agent_for,
        notes=[graph_coverage_note(cases)],
    )
    eval_reports.append(report)

    # A perfect model answer must survive parse -> validate -> resolve untouched.
    assert report.event_type_accuracy == 1.0
    assert report.location_f1 == 1.0
    assert report.goods_f1 == 1.0
    assert report.severity_mae == 0.0
    assert report.valid_json_rate == 1.0
    assert report.first_attempt_rate == 1.0
    assert report.provider_calls == len(cases)


# Measured 2026-09-21 on the 20 golden cases: event_type 80.0 %, location F1 0.850,
# goods F1 0.933, severity MAE 0.75. Floors leave ~2 cases of headroom so a small keyword
# tweak does not trip them, while a real regression of the last line of defence does.
# Do NOT tune the heuristic *to* this set — that would turn a baseline into a memorised score.
HEURISTIC_FLOORS = {
    "event_type_accuracy": 0.70,
    "location_f1": 0.75,
    "goods_f1": 0.85,
    "severity_mae": 1.00,  # ceiling, not a floor
}


def test_heuristic_fallback_baseline(eval_reports: list[object]) -> None:
    cases = load_golden()
    aliases = load_aliases()
    garbage = StubLLMProvider.from_strings(["this is not json at all"])

    report = evaluate(
        "heuristic: stub always emits garbage -> keyword fallback on the real golden headlines",
        cases,
        lambda _case: ExtractionAgent(garbage, aliases, max_attempts=1),
        notes=[
            "this is the demo's insurance policy (confidence 0.25, flagged degraded), not the model"
        ],
    )
    eval_reports.append(report)

    # By construction every case falls back — proves the harness reads the fallback flag.
    assert report.valid_json_rate == 0.0
    assert report.provider_calls == len(cases)
    # If a heuristic edit drops below these floors it is a real degradation.
    assert report.event_type_accuracy >= HEURISTIC_FLOORS["event_type_accuracy"]
    assert report.location_f1 >= HEURISTIC_FLOORS["location_f1"]
    assert report.goods_f1 >= HEURISTIC_FLOORS["goods_f1"]
    assert report.severity_mae <= HEURISTIC_FLOORS["severity_mae"]


# ══════════════════════════════════════════════════════════════════════════
# 4. Real-model modes — opt-in, capped, never run in CI
# ══════════════════════════════════════════════════════════════════════════
def _evenly_spaced(cases: Sequence[Case], limit: int) -> list[Case]:
    """``limit`` cases spread across the set, so a small sample still spans event types."""
    if limit >= len(cases):
        return list(cases)
    return [cases[i * len(cases) // limit] for i in range(limit)]


def _run_real_model(label: str, settings: Settings, limit: int) -> Report:
    cases = _evenly_spaced(load_golden(), limit)
    # One shared agent (the local model loads once). One attempt per case, so the spend is
    # exactly len(cases) provider calls — a retry loop would multiply the credit burn.
    agent = build_extraction_agent(settings.model_copy(update={"llm_max_retries": 1}))
    return evaluate(
        label,
        cases,
        lambda _case: agent,
        notes=[f"sampled {len(cases)} of 20 cases, 1 attempt each; extractor: {agent.name}"],
    )


def test_evenly_spaced_sampling_spans_the_set() -> None:
    cases = load_golden()
    picked = _evenly_spaced(cases, 3)
    assert len(picked) == 3
    assert picked[0] is cases[0]  # deterministic: same sample every run
    assert len({case["id"] for case in picked}) == 3
    assert {case["id"] for case in _evenly_spaced(cases, 99)} == {case["id"] for case in cases}


def test_real_model_runner_plumbing_with_a_stub_provider() -> None:
    # Everything the live/local tests do except the network/torch call itself:
    # settings -> build_extraction_agent -> evaluate. One attempt per case, exactly N calls.
    settings = Settings(_env_file=None, llm_provider="stub")  # type: ignore[call-arg]
    report = _run_real_model("stub via the real-model runner", settings, limit=3)
    assert report.n == 3
    assert report.provider_calls == 3  # LLM_MAX_RETRIES is forced to 1: spend == cases sampled
    assert report.valid_json_rate == 1.0  # the canned Hamburg strike is schema-valid
    assert any("extractor: stub" in note for note in report.notes)


@pytest.mark.live
def test_live_hf_extraction_quality(eval_reports: list[object]) -> None:
    """Real HF Inference traffic. Spends ``EVAL_LIVE_LIMIT`` (default 3) of the ~6 monthly calls.

    export HF_TOKEN=hf_xxx; unset HF_HUB_OFFLINE
    uv run pytest tests/eval -m live -s
    """
    settings = Settings(llm_provider="hf", llm_failover_to_local=False)  # no silent local switch
    if not settings.hf_token or settings.hf_token.startswith("hf_xxxx"):
        pytest.skip("HF_TOKEN is not set (or is the .env.example placeholder)")
    limit = int(os.environ.get("EVAL_LIVE_LIMIT", "3"))
    try:
        report = _run_real_model(f"live: HF {settings.hf_model}", settings, limit)
    except HfHubHTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (401, 402):
            pytest.skip(f"HF rejected the call (HTTP {status}): bad token or credits depleted")
        raise
    eval_reports.append(report)
    assert report.provider_calls == min(limit, 20)


@pytest.mark.local
@pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="uv sync --group local")
def test_local_model_extraction_quality(eval_reports: list[object]) -> None:
    """Real local CPU model (free, offline). ~15-20 s per case, so the default cap is 3.

    uv sync --group local
    HF_HUB_OFFLINE=1 uv run pytest tests/eval -m local -s
    """
    settings = Settings(llm_provider="local")
    limit = int(os.environ.get("EVAL_LOCAL_LIMIT", "3"))
    report = _run_real_model(f"local: {settings.local_model}", settings, limit)
    eval_reports.append(report)
    assert report.provider_calls == min(limit, 20)
