"""Relevance gate — measured drop rate against the §11.4 (P2.6) ≥80 % bar."""

from __future__ import annotations

import pytest

from chokepoint.agent.gate import LOGISTICS_KEYWORDS, is_relevant, matched_keywords
from tests.unit.conftest import make_doc

RELEVANT = [
    "Dockworkers strike halts operations at Hamburg Port",
    "Houthi attacks force carriers to suspend Red Sea transits",
    "Container backlog grows at Rotterdam as terminals struggle",
    "Suez Canal blocked after tanker runs aground",
    "EU imposes new sanctions on Russian steel exports",
    "Rail freight derailment closes key Poland-Germany line",
    "Ransomware attack paralyses customs system at Antwerp",
    "Panama Canal cuts daily transits as drought deepens",
    "China announces export ban on gallium and germanium",
    "Typhoon shuts ports across southern China, vessels wait at anchor",
    "Truckers blockade Polish border crossing with Ukraine",
    "Refinery fire in Rotterdam disrupts diesel shipments",
]

IRRELEVANT = [
    "Local bakery wins award for best sourdough in the county",
    "New study reports link between sleep and memory consolidation",
    "Premier League: late goal seals dramatic win for Arsenal",
    "Tech giant unveils foldable phone with improved battery life",
    "City council approves budget for new public library",
    "Actor announces retirement after four-decade career",
    "Scientists discover new species of frog in the Amazon",
    "Central bank holds interest rates steady amid inflation concerns",
    "Museum reopens after two-year renovation with support from donors",
    "Marathon runner sets new national record in Berlin",
    "Recipe: a quick weeknight pasta with lemon and garlic",
    "Opinion: why we need more sports fields in our schools",
]


def test_keyword_list_is_broad_enough() -> None:
    assert len(LOGISTICS_KEYWORDS) >= 60


@pytest.mark.parametrize("title", RELEVANT)
def test_relevant_headlines_pass(title: str) -> None:
    assert is_relevant(make_doc(title))


def test_irrelevant_drop_rate_clears_80_percent_bar() -> None:
    dropped = sum(not is_relevant(make_doc(t)) for t in IRRELEVANT)
    drop_rate = dropped / len(IRRELEVANT)
    assert drop_rate >= 0.8, (
        f"drop rate {drop_rate:.0%} — leaked: {[t for t in IRRELEVANT if is_relevant(make_doc(t))]}"
    )


def test_relevant_recall_is_perfect_on_sample() -> None:
    assert all(is_relevant(make_doc(t)) for t in RELEVANT)


def test_word_boundaries_prevent_substring_false_positives() -> None:
    # "report"/"support"/"sport" contain "port"; "strike" must not fire on "striker".
    assert not is_relevant(make_doc("Annual report shows strong support for local sport"))
    assert not is_relevant(make_doc("Striker signs new contract"))


def test_plurals_and_case_match() -> None:
    assert is_relevant(make_doc("VESSELS diverted as TARIFFS rise"))


def test_body_is_searched_too() -> None:
    assert is_relevant(make_doc("Update", body="The blockade of the harbour continues."))


def test_matched_keywords_lists_hits() -> None:
    assert matched_keywords("Container backlog at the port") == ["backlog", "container", "port"]


def test_custom_keyword_set() -> None:
    doc = make_doc("Bananas are yellow")
    assert not is_relevant(doc)
    assert is_relevant(doc, keywords=frozenset({"banana"}))
