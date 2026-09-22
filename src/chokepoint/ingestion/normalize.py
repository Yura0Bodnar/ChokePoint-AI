import logging
from datetime import UTC, datetime
from typing import Any

from chokepoint.contracts import RawDocument
from chokepoint.ingestion.dedupe import doc_id_from_url

logger = logging.getLogger(__name__)


def _parse_gdelt_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for date_format in ("%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(value, date_format)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
        except ValueError:
            continue
    return None


def gdelt_article_to_raw_document(article: dict[str, Any]) -> RawDocument | None:
    """Normalize one GDELT row, returning None for malformed rows."""
    try:
        url = article.get("url")
        published_at = _parse_gdelt_date(article.get("seendate"))
        if not url or published_at is None:
            raise ValueError("missing URL or parseable seendate")
        return RawDocument(
            doc_id=doc_id_from_url(url),
            source="gdelt",
            source_name=article.get("domain", "GDELT"),
            url=url,
            title=article.get("title", ""),
            body="",
            published_at=published_at,
            language=article.get("language", "en"),
            fetched_at=datetime.now(UTC),
        )
    except (KeyError, TypeError, ValueError) as error:
        logger.warning("Skipping malformed GDELT article: %s", error)
        return None
