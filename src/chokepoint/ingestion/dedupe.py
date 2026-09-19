import hashlib


def doc_id_from_url(url: str) -> str:
    """Return the contract's sha256(url)[:16] identifier."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def is_duplicate(doc_id: str, seen_ids: set[str]) -> bool:
    return doc_id in seen_ids
