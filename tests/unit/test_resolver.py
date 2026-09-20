from __future__ import annotations

from pathlib import Path

import pytest

from chokepoint.agent.resolver import ALIASES_PATH, load_aliases, normalise, resolve_location

# The four ids shared with Person 1's seed graph and Person 3's stub.
SHARED_VOCABULARY = {
    "port_hamburg": ["Hamburg", "Hamburg Port", "Port of Hamburg", "Hamburg harbor"],
    "com_auto_parts": ["auto parts", "automotive parts", "automotive components"],
    "ind_auto_parts_pl": ["Polish automotive industry", "Poland auto parts sector"],
    "mkt_ukraine_aftermarket": ["Ukrainian aftermarket", "Ukraine auto market"],
}


def test_aliases_file_ships_with_package() -> None:
    assert ALIASES_PATH.is_file()


@pytest.mark.parametrize(("node_id", "aliases"), SHARED_VOCABULARY.items())
def test_shared_vocabulary_resolves_exactly(
    alias_index: dict[str, str], node_id: str, aliases: list[str]
) -> None:
    for alias in aliases:
        assert resolve_location(alias, alias_index) == node_id, alias


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HAMBURG PORT", "port_hamburg"),  # case
        ("  Port of Hamburg. ", "port_hamburg"),  # whitespace + punctuation
        ("the Port of Hamburg", "port_hamburg"),  # leading article
        ("Hamburg's port", "port_hamburg"),  # possessive → difflib close match
        ("Hamburgg", "port_hamburg"),  # typo → difflib close match
        ("Rotterdam port", "port_rotterdam"),
        ("Gdańsk", "port_gdansk"),
    ],
)
def test_fuzzy_and_normalised_matches(alias_index: dict[str, str], raw: str, expected: str) -> None:
    assert resolve_location(raw, alias_index) == expected


@pytest.mark.parametrize("raw", ["Shanghai", "Port of Nowhere", "", "   ", "xyz"])
def test_unknown_entity_returns_none(alias_index: dict[str, str], raw: str) -> None:
    assert resolve_location(raw, alias_index) is None


def test_cutoff_is_respected(alias_index: dict[str, str]) -> None:
    assert resolve_location("Hamburgg", alias_index, cutoff=0.99) is None


def test_normalise() -> None:
    assert normalise("  The Port\u2019s  of “Hamburg”. ") == "the ports of hamburg"


def test_load_aliases_inverts_and_lowercases(tmp_path: Path) -> None:
    f = tmp_path / "a.yaml"
    f.write_text("node_a:\n  - Foo\n  - 'Foo Bar'\nnode_b:\n  - baz\n")
    assert load_aliases(f) == {"foo": "node_a", "foo bar": "node_a", "baz": "node_b"}


def test_load_aliases_rejects_duplicate_alias_across_nodes(tmp_path: Path) -> None:
    f = tmp_path / "a.yaml"
    f.write_text("node_a:\n  - Foo\nnode_b:\n  - foo\n")
    with pytest.raises(ValueError, match="claimed by both"):
        load_aliases(f)


def test_load_aliases_rejects_non_list(tmp_path: Path) -> None:
    f = tmp_path / "a.yaml"
    f.write_text("node_a: Foo\n")
    with pytest.raises(ValueError, match="must map to a list"):
        load_aliases(f)


def test_shipped_aliases_have_no_cross_node_duplicates() -> None:
    # load_aliases raises on conflicts, so simply loading the real file is the assertion.
    index = load_aliases()
    assert len(index) >= 40
