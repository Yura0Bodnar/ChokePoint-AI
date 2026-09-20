from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from chokepoint.agent.resolver import load_aliases
from chokepoint.contracts import RawDocument

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"


@pytest.fixture(scope="session")
def llm_fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def alias_index() -> dict[str, str]:
    return load_aliases()


def make_doc(title: str, body: str = "", *, doc_id: str = "doc0000000000001") -> RawDocument:
    now = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    return RawDocument(
        doc_id=doc_id,
        source="rss",
        source_name="test",
        url="https://example.com/article",
        title=title,
        body=body,
        published_at=now,
        fetched_at=now,
    )


@pytest.fixture
def hamburg_doc() -> RawDocument:
    return make_doc(
        "Strike halts operations at Hamburg Port",
        "Dockworkers walked out today at the Port of Hamburg, halting container handling "
        "for 48 hours. Carriers warned of delays to automotive parts bound for Poland.",
    )
