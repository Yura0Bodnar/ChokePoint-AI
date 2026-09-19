from typing import Protocol


class DocumentSource(Protocol):
    def fetch(self, query: str, *, timespan: str = "24h", max_records: int = 75) -> list[dict]:
        """Fetch source-specific article metadata."""
