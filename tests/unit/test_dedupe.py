from chokepoint.ingestion.dedupe import doc_id_from_url, is_duplicate


def test_doc_id_is_stable_and_duplicate_check_is_exact() -> None:
    url = "https://example.com/article"
    doc_id = doc_id_from_url(url)
    assert doc_id == doc_id_from_url(url)
    assert is_duplicate(doc_id, {doc_id})
    assert not is_duplicate(doc_id, set())
