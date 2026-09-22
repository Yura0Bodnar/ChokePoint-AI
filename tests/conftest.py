from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from chokepoint.api import deps
from chokepoint.api.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A TestClient that never depends on the developer's ``.env``.

    ``LLM_PROVIDER`` is pinned to ``stub`` so a real ``LLM_PROVIDER=hf`` (and its token)
    can neither change what ``/readyz`` reports nor turn a test into a billed network call.
    """
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    deps.get_settings.cache_clear()
    deps.get_llm_provider.cache_clear()
    yield TestClient(app)
    deps.get_settings.cache_clear()
    deps.get_llm_provider.cache_clear()
