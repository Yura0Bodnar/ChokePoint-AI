"""ExtractionAgent end-to-end on StubLLMProvider fixtures — zero network."""

from __future__ import annotations

from pathlib import Path

import pytest

from chokepoint.agent.extractor import (
    FALLBACK_CONFIDENCE,
    FALLBACK_EXTRACTOR_VERSION,
    ExtractionAgent,
    ExtractionSkipped,
)
from chokepoint.agent.prompts import PROMPT_VERSION
from chokepoint.agent.providers.base import LLMProvider, Message
from chokepoint.agent.providers.stub import StubLLMProvider
from chokepoint.contracts import DisruptionEvent, EventType, RawDocument
from tests.unit.conftest import make_doc


def _agent(
    fixtures_dir: Path, alias_index: dict[str, str], *fixtures: str
) -> tuple[ExtractionAgent, StubLLMProvider]:
    provider = StubLLMProvider(fixtures_dir, fixtures=fixtures or ("strike_hamburg.txt",))
    return ExtractionAgent(provider, alias_index), provider


def test_stub_provider_satisfies_protocol(llm_fixtures_dir: Path) -> None:
    assert isinstance(StubLLMProvider(llm_fixtures_dir), LLMProvider)


# ── happy path ────────────────────────────────────────────────────────
def test_clean_fixture_yields_resolved_event(
    llm_fixtures_dir: Path, alias_index: dict[str, str], hamburg_doc: RawDocument
) -> None:
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    event = agent.extract(hamburg_doc)

    assert isinstance(event, DisruptionEvent)
    assert event.event_type is EventType.STRIKE
    assert event.locations[0].raw == "Port of Hamburg"
    assert event.locations[0].node_id == "port_hamburg"  # layer ⑤ via aliases.yaml
    assert event.source_doc_id == hamburg_doc.doc_id
    assert event.extracted_at is not None
    assert event.extractor_version == f"stub-{PROMPT_VERSION}"
    assert not event.extractor_version.startswith("fallback")
    assert agent.last_attempts == 1
    assert len(provider.calls) == 1


def test_prompt_sent_to_provider_has_system_fewshot_and_article(
    llm_fixtures_dir: Path, alias_index: dict[str, str], hamburg_doc: RawDocument
) -> None:
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    agent.extract(hamburg_doc)
    messages = provider.calls[0]
    assert messages[0]["role"] == "system"
    assert "You must return ONLY valid JSON inside a ```json code block." in messages[0]["content"]
    assert "Do not output any other text." in messages[0]["content"]
    assert '"event_type"' in messages[0]["content"]  # schema inlined
    assert [m["role"] for m in messages[1:-1]] == ["user", "assistant"] * 3
    assert all(m["content"].startswith("```json") for m in messages[2:-1:2])  # fenced examples
    assert messages[-1]["role"] == "user"
    assert hamburg_doc.title in messages[-1]["content"]


def test_fenced_fixture_is_cleaned_and_resolved(
    llm_fixtures_dir: Path, alias_index: dict[str, str], hamburg_doc: RawDocument
) -> None:
    agent, _ = _agent(llm_fixtures_dir, alias_index, "strike_hamburg_fenced.txt")
    event = agent.extract(hamburg_doc)
    assert event.locations[0].raw == "Hamburg Port"
    assert event.locations[0].node_id == "port_hamburg"
    assert agent.last_attempts == 1


def test_trailing_comma_fixture_is_repaired(
    llm_fixtures_dir: Path, alias_index: dict[str, str], hamburg_doc: RawDocument
) -> None:
    agent, _ = _agent(llm_fixtures_dir, alias_index, "strike_hamburg_trailing_commas.txt")
    event = agent.extract(hamburg_doc)
    assert event.locations[0].node_id == "port_hamburg"
    assert event.affected_goods == ["auto parts"]


def test_multi_location_partial_resolution_and_empty_goods(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    doc = make_doc(
        "Carriers suspend Red Sea and Suez transits", "Shipping lines pause all sailings."
    )
    agent, _ = _agent(llm_fixtures_dir, alias_index, "multi_location_no_goods.txt")
    event = agent.extract(doc)
    by_raw = {loc.raw: loc.node_id for loc in event.locations}
    assert by_raw == {
        "Red Sea": "chokepoint_red_sea",
        "Suez Canal": "chokepoint_suez",
        "Port of Shanghai": None,  # unresolved is expected, not an error
    }
    assert event.affected_goods == []


# ── relevance gate ────────────────────────────────────────────────────
def test_irrelevant_doc_is_skipped_without_calling_provider(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    doc = make_doc("Local bakery wins award for best sourdough", doc_id="deadbeefdeadbeef")
    with pytest.raises(ExtractionSkipped) as info:
        agent.extract(doc)
    assert str(info.value) == "deadbeefdeadbeef"
    assert provider.calls == []  # zero tokens spent


# ── retry loop ────────────────────────────────────────────────────────
def test_retry_after_one_validation_failure_then_success(
    llm_fixtures_dir: Path, alias_index: dict[str, str], hamburg_doc: RawDocument
) -> None:
    agent, provider = _agent(
        llm_fixtures_dir, alias_index, "strike_hamburg_invalid.txt", "strike_hamburg.txt"
    )
    event = agent.extract(hamburg_doc)

    assert agent.last_attempts == 2
    assert len(provider.calls) == 2
    assert event.severity == 3
    assert event.locations[0].node_id == "port_hamburg"
    assert not event.extractor_version.startswith("fallback")

    # The repair prompt feeds back the bad output and the exact ValidationError text.
    second = provider.calls[1]
    assert second[-2]["role"] == "assistant"
    assert '"severity": 8' in second[-2]["content"]
    assert second[-1]["role"] == "user"
    assert "failed validation" in second[-1]["content"]
    assert "severity" in second[-1]["content"]
    assert "event_type" in second[-1]["content"]
    assert second[-1]["content"].rstrip().endswith("Return the corrected JSON object only.")


def test_retry_after_decode_error_then_success(
    llm_fixtures_dir: Path, alias_index: dict[str, str], hamburg_doc: RawDocument
) -> None:
    agent, _ = _agent(llm_fixtures_dir, alias_index, "garbage.txt", "strike_hamburg.txt")
    event = agent.extract(hamburg_doc)
    assert agent.last_attempts == 2
    assert event.locations[0].node_id == "port_hamburg"


# ── fallback ──────────────────────────────────────────────────────────
def test_fallback_after_max_attempts(
    llm_fixtures_dir: Path, alias_index: dict[str, str], hamburg_doc: RawDocument
) -> None:
    agent, provider = _agent(llm_fixtures_dir, alias_index, "strike_hamburg_invalid.txt")
    event = agent.extract(hamburg_doc)

    assert len(provider.calls) == 3  # hard cap
    assert event.extractor_version == FALLBACK_EXTRACTOR_VERSION
    assert event.extractor_version.startswith("fallback")  # what P3's orchestrator checks
    assert event.confidence == FALLBACK_CONFIDENCE
    assert event.event_type is EventType.STRIKE  # keyword heuristic
    assert event.locations[0].node_id == "port_hamburg"
    assert "auto parts" in event.affected_goods or "automotive parts" in event.affected_goods
    assert event.source_doc_id == hamburg_doc.doc_id


def test_max_attempts_is_configurable(
    llm_fixtures_dir: Path, alias_index: dict[str, str], hamburg_doc: RawDocument
) -> None:
    provider = StubLLMProvider(llm_fixtures_dir, fixtures=["garbage.txt"])
    agent = ExtractionAgent(provider, alias_index, max_attempts=1)
    event = agent.extract(hamburg_doc)
    assert len(provider.calls) == 1
    assert event.extractor_version.startswith("fallback")


@pytest.mark.parametrize(
    ("title", "body", "expected_type"),
    [
        ("Port strike enters second day", "", EventType.STRIKE),
        ("Cargo ship runs aground in the Suez Canal", "", EventType.ACCIDENT),
        ("EU widens sanctions on shipping", "", EventType.SANCTIONS),
        ("Typhoon shuts port for a day", "", EventType.NATURAL_DISASTER),
        ("Container congestion worsens at Rotterdam", "", EventType.CONGESTION),
        ("Port update", "", EventType.OTHER),
    ],
)
def test_fallback_heuristic_event_type(
    llm_fixtures_dir: Path,
    alias_index: dict[str, str],
    title: str,
    body: str,
    expected_type: EventType,
) -> None:
    agent, _ = _agent(llm_fixtures_dir, alias_index)
    event = agent._fallback_extract(make_doc(title, body))
    assert event.event_type is expected_type
    assert 1 <= event.severity <= 5
    assert event.locations  # min_length=1 always honoured


@pytest.mark.parametrize("title", ["", "   ", "x" * 5000, "\u2603 unicode only \u2603"])
def test_fallback_never_raises_on_degenerate_input(
    llm_fixtures_dir: Path, alias_index: dict[str, str], title: str
) -> None:
    agent, _ = _agent(llm_fixtures_dir, alias_index)
    event = agent._fallback_extract(make_doc(title, ""))
    assert isinstance(event, DisruptionEvent)
    assert event.extractor_version.startswith("fallback")


def test_fallback_survives_heuristic_crash(
    llm_fixtures_dir: Path, hamburg_doc: RawDocument
) -> None:
    class Exploding(ExtractionAgent):
        def _heuristic(self, doc: RawDocument) -> DisruptionEvent:
            raise RuntimeError("boom")

    agent = Exploding(StubLLMProvider(llm_fixtures_dir), {})
    event = agent._fallback_extract(hamburg_doc)
    assert event.extractor_version == FALLBACK_EXTRACTOR_VERSION
    assert event.event_type is EventType.OTHER


# ── provider errors propagate ─────────────────────────────────────────
def test_provider_errors_are_not_swallowed(
    alias_index: dict[str, str], hamburg_doc: RawDocument
) -> None:
    class Down:
        name = "down"
        supports_structured = True

        def chat(self, messages: list[Message], *, structured: bool = True) -> str:
            raise ConnectionError("network is down")

    with pytest.raises(ConnectionError):
        ExtractionAgent(Down(), alias_index).extract(hamburg_doc)


# ── extract_text: the API bridge (ad-hoc text -> synthetic RawDocument) ────────
def test_extract_text_returns_valid_event_against_stub(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    event = agent.extract_text("A strike hit Hamburg Port")

    assert isinstance(event, DisruptionEvent)
    assert event.event_type is EventType.STRIKE
    assert event.locations[0].node_id == "port_hamburg"  # layer ⑤ still runs
    assert event.extractor_version == f"stub-{PROMPT_VERSION}"
    assert len(provider.calls) == 1


def test_extract_text_skips_relevance_gate_by_default(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    # A user who pasted text has already decided it is relevant; the gate is for the firehose.
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    event = agent.extract_text("Local bakery wins award for best sourdough")
    assert isinstance(event, DisruptionEvent)
    assert len(provider.calls) == 1


def test_extract_text_apply_gate_opt_in_skips_irrelevant_text(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    with pytest.raises(ExtractionSkipped):
        agent.extract_text("Local bakery wins award for best sourdough", apply_gate=True)
    assert provider.calls == []  # zero tokens spent


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_extract_text_rejects_blank_text_without_calling_provider(
    llm_fixtures_dir: Path, alias_index: dict[str, str], blank: str
) -> None:
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    with pytest.raises(ValueError, match="must not be empty"):  # API layer maps this to a 422
        agent.extract_text(blank)
    assert provider.calls == []  # an empty request must never burn a free-tier credit


def test_extract_text_synthesises_a_deterministic_document(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    text = "Dockworkers walked out at Hamburg Port. " * 5  # > 120 chars: title is truncated
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    first = agent.extract_text(text)
    second = agent.extract_text(text)

    assert first.source_doc_id == second.source_doc_id  # sha256(text)[:16] — stable
    assert first.source_doc_id is not None
    assert len(first.source_doc_id) == 16
    article = provider.calls[0][-1]["content"]
    assert article.startswith(f"Title: {text[:120].strip()}")  # title = text[:120]
    assert "Article: Dockworkers walked out" in article  # body = the full text


def test_extract_text_shares_the_retry_loop(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    agent, provider = _agent(
        llm_fixtures_dir, alias_index, "strike_hamburg_invalid.txt", "strike_hamburg.txt"
    )
    event = agent.extract_text("A strike hit Hamburg Port")
    assert agent.last_attempts == 2
    assert len(provider.calls) == 2
    assert not event.extractor_version.startswith("fallback")


def test_extract_text_shares_the_heuristic_fallback(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    agent, provider = _agent(llm_fixtures_dir, alias_index, "garbage.txt")
    event = agent.extract_text("Dockworkers strike at Hamburg Port halts container handling")
    assert len(provider.calls) == 3  # hard cap, same as extract()
    assert event.extractor_version == FALLBACK_EXTRACTOR_VERSION  # -> orchestrator sets degraded
    assert event.event_type is EventType.STRIKE
    assert event.locations[0].node_id == "port_hamburg"


def test_extract_still_applies_the_gate_to_ingested_documents(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    # Regression guard for the _extract_from_doc refactor: extract() must keep gating.
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    with pytest.raises(ExtractionSkipped):
        agent.extract(make_doc("Local bakery wins award for best sourdough"))
    assert provider.calls == []


def test_agent_name_follows_the_provider(
    llm_fixtures_dir: Path, alias_index: dict[str, str]
) -> None:
    agent, provider = _agent(llm_fixtures_dir, alias_index)
    assert agent.name == provider.name == "stub"
