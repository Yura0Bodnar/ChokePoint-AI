from datetime import UTC, datetime

import httpx
import respx

from chokepoint.ingestion.gdelt import DEFAULT_QUERY, GDELT_URL, fetch_gdelt
from chokepoint.ingestion.normalize import gdelt_article_to_raw_document


@respx.mock
def test_fetch_gdelt_uses_default_query_and_returns_articles() -> None:
    route = respx.get(GDELT_URL).mock(
        return_value=httpx.Response(200, json={"articles": [{"url": "https://example.com"}]})
    )
    assert fetch_gdelt() == [{"url": "https://example.com"}]
    assert route.called
    assert route.calls.last.request.url.params["query"] == DEFAULT_QUERY


def test_normalize_gdelt_article_and_skip_malformed_date() -> None:
    article = {
        "url": "https://example.com/article",
        "domain": "example.com",
        "title": "Port disruption",
        "seendate": "20260918083000",
        "language": "English",
    }
    document = gdelt_article_to_raw_document(article)
    assert document is not None
    assert document.published_at == datetime(2026, 9, 18, 8, 30, tzinfo=UTC)
    assert gdelt_article_to_raw_document({"url": "https://example.com", "seendate": "bad"}) is None
