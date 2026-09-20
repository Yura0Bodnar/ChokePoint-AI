"""Ladder layer ⑤ — entity resolution: extracted text → graph ``node_id``.

Exact alias lookup first, then a stdlib ``difflib`` close-match fallback.
No new fuzzy-matching dependency — difflib is sufficient at this graph size.

``aliases.yaml`` is co-owned with Person 1: node ids there must match their
seed graph exactly. Unresolved entities return ``None`` and surface via
``SimulationResult.unresolved_entities`` — that is expected, not an error.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import yaml

ALIASES_PATH = Path(__file__).with_name("aliases.yaml")

_ARTICLES = re.compile(r"^(?:the|port of|harbour of|harbor of)\s+", re.IGNORECASE)


def normalise(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation noise."""
    text = re.sub("[\u2018\u2019'\"\u201c\u201d.,;:!?()]", "", text)
    return " ".join(text.split()).lower()


def load_aliases(path: Path = ALIASES_PATH) -> dict[str, str]:
    """Inverts aliases.yaml into ``{alias_text.lower(): node_id}``."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    index: dict[str, str] = {}
    for node_id, aliases in raw.items():
        if not isinstance(aliases, list):
            raise ValueError(f"aliases.yaml: {node_id!r} must map to a list, got {type(aliases)}")
        for alias in aliases:
            key = normalise(str(alias))
            existing = index.get(key)
            if existing is not None and existing != node_id:
                raise ValueError(
                    f"aliases.yaml: alias {alias!r} claimed by both {existing} and {node_id}"
                )
            index[key] = node_id
    return index


def resolve_location(raw: str, alias_index: dict[str, str], *, cutoff: float = 0.85) -> str | None:
    """Exact match first, then a difflib close-match fallback; ``None`` if unmapped."""
    key = normalise(raw)
    if not key:
        return None
    if key in alias_index:
        return alias_index[key]
    stripped = _ARTICLES.sub("", key)
    if stripped in alias_index:
        return alias_index[stripped]
    matches = difflib.get_close_matches(key, alias_index.keys(), n=1, cutoff=cutoff)
    return alias_index[matches[0]] if matches else None


def resolve_goods(raw: str, alias_index: dict[str, str], *, cutoff: float = 0.85) -> str | None:
    """Same policy as ``resolve_location``; commodities share the alias file."""
    return resolve_location(raw, alias_index, cutoff=cutoff)


__all__ = ["ALIASES_PATH", "load_aliases", "normalise", "resolve_goods", "resolve_location"]
