import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import httpx  # noqa: E402

from chokepoint.ingestion.gdelt import DEFAULT_QUERY, fetch_gdelt  # noqa: E402
from chokepoint.ingestion.normalize import gdelt_article_to_raw_document  # noqa: E402
from chokepoint.ingestion.store import append_documents  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        articles = fetch_gdelt(DEFAULT_QUERY)
    except (httpx.HTTPError, httpx.TimeoutException) as error:
        logger.error("GDELT fetch failed: %s", error)
        return 1
    documents = [
        document
        for article in articles
        if (document := gdelt_article_to_raw_document(article)) is not None
    ]
    written = append_documents(documents, ROOT / "data/raw")
    print(f"new_documents={written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
