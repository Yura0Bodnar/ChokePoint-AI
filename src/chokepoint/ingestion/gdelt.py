from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_QUERY = '(port OR strike OR blockade OR "supply chain") sourcelang:english'


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def fetch_gdelt(
    query: str = DEFAULT_QUERY, *, timespan: str = "24h", max_records: int = 75
) -> list[dict[str, Any]]:
    """Fetch GDELT article metadata; HTTP failures propagate after retries."""
    params: dict[str, str | int] = {
        "query": query,
        "mode": "artlist",
        "maxrecords": max_records,
        "timespan": timespan,
        "format": "json",
    }
    response = httpx.get(GDELT_URL, params=params, timeout=15.0)
    response.raise_for_status()
    payload = response.json()
    articles: list[dict[str, Any]] = payload.get("articles", [])
    return articles
