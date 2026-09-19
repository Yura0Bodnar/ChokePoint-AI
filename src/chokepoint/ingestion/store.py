from datetime import UTC, date, datetime
from pathlib import Path

from chokepoint.contracts import RawDocument
from chokepoint.ingestion.dedupe import is_duplicate


def append_documents(
    documents: list[RawDocument], directory: Path, *, day: date | None = None
) -> int:
    """Append documents not already present in the day's JSONL cache."""
    directory.mkdir(parents=True, exist_ok=True)
    cache_day = day or datetime.now(UTC).date()
    cache_path = directory / f"gdelt_{cache_day:%Y%m%d}.jsonl"
    seen_ids = _read_ids(cache_path)
    new_documents: list[RawDocument] = []
    for document in documents:
        if is_duplicate(document.doc_id, seen_ids):
            continue
        new_documents.append(document)
        seen_ids.add(document.doc_id)
    with cache_path.open("a", encoding="utf-8") as cache_file:
        for document in new_documents:
            cache_file.write(document.model_dump_json() + "\n")
    return len(new_documents)


def _read_ids(cache_path: Path) -> set[str]:
    if not cache_path.exists():
        return set()
    seen_ids: set[str] = set()
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        try:
            document = RawDocument.model_validate_json(line)
        except ValueError:
            continue
        seen_ids.add(document.doc_id)
    return seen_ids
