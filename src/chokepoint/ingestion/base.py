from typing import Any, Protocol


class DocumentSource(Protocol):
    def fetch(
        self, query: str, *, timespan: str = "24h", max_records: int = 75
    ) -> list[dict[str, Any]]:
        """Fetch source-specific article metadata."""
