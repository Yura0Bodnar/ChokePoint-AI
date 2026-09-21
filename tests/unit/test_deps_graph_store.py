"""``api/deps.py::get_graph_store`` — the wiring that replaced the hardcoded stub."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from chokepoint.api import deps
from chokepoint.graph.store import NetworkXGraphStore


@pytest.fixture(autouse=True)
def _fresh_caches() -> Iterator[None]:
    # Both factories are lru_cache'd; without this, an earlier test's settings would leak in
    # and this module would leak its env-driven store into the next one.
    deps.get_settings.cache_clear()
    deps.get_graph_store.cache_clear()
    yield
    deps.get_settings.cache_clear()
    deps.get_graph_store.cache_clear()


def test_default_backend_is_the_real_networkx_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("GRAPH_BACKEND", "networkx")
    store = deps.get_graph_store()
    assert isinstance(store, NetworkXGraphStore)
    assert not isinstance(store, deps.StubGraphStore)


def test_the_real_store_is_built_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    assert deps.get_graph_store() is deps.get_graph_store()


def test_demo_mode_serves_the_offline_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    assert isinstance(deps.get_graph_store(), deps.StubGraphStore)


def test_an_unimplemented_backend_fails_loudly_instead_of_serving_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("GRAPH_BACKEND", "kuzu")
    with pytest.raises(ValueError, match="kuzu"):
        deps.get_graph_store()


def test_the_seed_dir_is_the_packaged_graph() -> None:
    for name in ("nodes.yaml", "edges.yaml", "SOURCES.md"):
        assert (deps._SEED_DIR / name).is_file(), name
