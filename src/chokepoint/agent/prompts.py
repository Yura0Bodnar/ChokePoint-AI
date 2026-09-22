"""Versioned extraction prompts (ladder layer ②, ARCHITECTURE_AND_PLAN.md §7.3).

Rules for this file:

* **Never edit a prompt version in place** once it has a recorded score in
  ``docs/PROMPTS.md``. Add ``SYSTEM_V2`` / ``FEW_SHOT_V2`` and bump
  ``PROMPT_VERSION`` instead.
* The schema is inlined into the system message. No provider sends a
  ``response_format`` (the free HF tier rejects it with HTTP 400), so the prompt
  and the fence-aware parser (``agent/parser.py``) carry the whole structure
  guarantee.
* Few-shot pairs cover the hard cases: a single-location strike, a
  multi-location event, and one with ``affected_goods = []`` so the model
  learns it may emit an empty list rather than hallucinate a commodity.
"""

from __future__ import annotations

import json

from chokepoint.agent.providers.base import Message
from chokepoint.agent.schema import DISRUPTION_EVENT_JSON_SCHEMA

PROMPT_VERSION = "v2"

#: Body truncation keeps title + body near ~1,500 tokens. Longer input
#: measurably degrades small-model format adherence and burns free credits.
MAX_BODY_CHARS = 1200

SYSTEM_V1 = """You are a supply-chain OSINT analyst. Extract ONE logistics \
disruption event from the article and return a single JSON object.

Rules:
- Output JSON only. No markdown, no code fences, no commentary.
- event_type MUST be one of: strike, blockade, sanctions, accident, conflict,
  natural_disaster, cyberattack, congestion, export_ban,
  infrastructure_failure, other.
- locations: use the exact wording from the article in "raw". 1-5 entries.
  Set "node_id" to null and "country_iso2" to the ISO 3166-1 alpha-2 code
  of the country if it is clear from the article, otherwise null.
- affected_goods: lowercase commodity or industry terms. Use [] if the article
  names none. NEVER guess goods that are not supported by the text.
- severity: 1 = minor delay, 3 = significant regional disruption,
  5 = full closure of a major corridor.
- estimated_duration_days: integer days if the article states or clearly
  implies a duration, otherwise null.
- confidence: your own certainty (0.0-1.0) that this article describes a real,
  current logistics disruption.
- summary: one plain sentence, at most 200 characters.
- Do not emit source_doc_id, extractor_version or extracted_at.

Schema:
{schema}
"""

#: v2 = v1's rules with the output contract changed to "one ```json fenced block, nothing
#: else" — the shape that models behind the free HF tier follow most reliably now that
#: ``response_format`` is gone. ``parser.extract_json_blob`` pulls the JSON out of the fence.
SYSTEM_V2 = """You are a supply-chain OSINT analyst. Extract ONE logistics \
disruption event from the article and return a single JSON object.

You must return ONLY valid JSON inside a ```json code block. Do not output any other text.

Rules:
- Your entire reply is one ```json fenced block containing exactly one JSON object:
  nothing before the opening fence, nothing after the closing fence.
- event_type MUST be one of: strike, blockade, sanctions, accident, conflict,
  natural_disaster, cyberattack, congestion, export_ban,
  infrastructure_failure, other.
- locations: use the exact wording from the article in "raw". 1-5 entries.
  Set "node_id" to null and "country_iso2" to the ISO 3166-1 alpha-2 code
  of the country if it is clear from the article, otherwise null.
- affected_goods: lowercase commodity or industry terms. Use [] if the article
  names none. NEVER guess goods that are not supported by the text.
- severity: 1 = minor delay, 3 = significant regional disruption,
  5 = full closure of a major corridor.
- estimated_duration_days: integer days if the article states or clearly
  implies a duration, otherwise null.
- confidence: your own certainty (0.0-1.0) that this article describes a real,
  current logistics disruption.
- summary: one plain sentence, at most 200 characters.
- Do not emit source_doc_id, extractor_version or extracted_at.

Schema:
{schema}
"""

# Each pair is (user article text, assistant JSON reply). Written against
# realistic headlines; the JSON replies are exactly what we want back.
FEW_SHOT_V1: list[tuple[str, str]] = [
    (
        "Title: Dockworkers strike shuts Port of Hamburg for 48 hours\n\n"
        "Article: Members of the ver.di union walked out at the Port of Hamburg on "
        "Tuesday, halting container handling at all four terminals for a planned "
        "48-hour stoppage over pay. Shipping lines including Hapag-Lloyd warned of "
        "delays to automotive parts and consumer electronics bound for Central Europe.",
        json.dumps(
            {
                "event_type": "strike",
                "locations": [{"raw": "Port of Hamburg", "node_id": None, "country_iso2": "DE"}],
                "affected_goods": ["automotive parts", "consumer electronics"],
                "severity": 3,
                "estimated_duration_days": 2,
                "confidence": 0.92,
                "summary": "48-hour dockworker strike halts container handling at the Port of Hamburg, delaying auto parts and electronics.",
            }
        ),
    ),
    (
        "Title: Houthi attacks push carriers to suspend Red Sea and Suez transits\n\n"
        "Article: Maersk and MSC said on Friday they would pause all sailings through "
        "the Red Sea and the Suez Canal after two more vessels were struck near Bab "
        "el-Mandeb. Ships will instead round the Cape of Good Hope, adding 10 to 14 "
        "days to Asia-Europe rotations. Retailers said inventories of apparel and "
        "furniture would be hit first.",
        json.dumps(
            {
                "event_type": "conflict",
                "locations": [
                    {"raw": "Red Sea", "node_id": None, "country_iso2": None},
                    {"raw": "Suez Canal", "node_id": None, "country_iso2": "EG"},
                    {"raw": "Bab el-Mandeb", "node_id": None, "country_iso2": None},
                ],
                "affected_goods": ["apparel", "furniture"],
                "severity": 5,
                "estimated_duration_days": 30,
                "confidence": 0.95,
                "summary": "Carriers suspend Red Sea and Suez Canal transits after attacks, rerouting Asia-Europe ships around the Cape.",
            }
        ),
    ),
    (
        "Title: Fog closes Port of Constanta to inbound traffic\n\n"
        "Article: The Romanian port authority suspended pilotage at the Port of "
        "Constanta on Sunday morning after visibility dropped below 200 metres. "
        "Around a dozen vessels are waiting at anchor. Operations are expected to "
        "resume once conditions improve later in the day.",
        json.dumps(
            {
                "event_type": "natural_disaster",
                "locations": [{"raw": "Port of Constanta", "node_id": None, "country_iso2": "RO"}],
                "affected_goods": [],
                "severity": 1,
                "estimated_duration_days": 1,
                "confidence": 0.7,
                "summary": "Dense fog suspends pilotage at the Port of Constanta, leaving about a dozen vessels waiting at anchor.",
            }
        ),
    ),
]

# Same articles and JSON as v1; the assistant turns are fenced so the examples demonstrate
# exactly the format SYSTEM_V2 demands (a bare-JSON example would contradict the rule).
FEW_SHOT_V2: list[tuple[str, str]] = [
    (user, f"```json\n{assistant}\n```") for user, assistant in FEW_SHOT_V1
]

_SYSTEM_BY_VERSION: dict[str, str] = {"v1": SYSTEM_V1, "v2": SYSTEM_V2}
_FEW_SHOT_BY_VERSION: dict[str, list[tuple[str, str]]] = {"v1": FEW_SHOT_V1, "v2": FEW_SHOT_V2}


def render_system(version: str = PROMPT_VERSION) -> str:
    """System message for ``version`` with the contract's JSON schema inlined."""
    template = _SYSTEM_BY_VERSION[version]
    schema = json.dumps(DISRUPTION_EVENT_JSON_SCHEMA["schema"], separators=(",", ":"))
    return template.replace("{schema}", schema)


def format_article(title: str, body: str, *, max_body_chars: int = MAX_BODY_CHARS) -> str:
    body = " ".join(body.split())  # collapse whitespace before truncating
    if len(body) > max_body_chars:
        body = body[:max_body_chars].rsplit(" ", 1)[0] + " …"
    return f"Title: {title.strip()}\n\nArticle: {body}" if body else f"Title: {title.strip()}"


def build_messages(
    article_title: str,
    article_body: str,
    *,
    version: str = PROMPT_VERSION,
    max_body_chars: int = MAX_BODY_CHARS,
) -> list[Message]:
    """System + few-shot pairs + the article, body truncated to ``max_body_chars``."""
    messages: list[Message] = [{"role": "system", "content": render_system(version)}]
    for user, assistant in _FEW_SHOT_BY_VERSION[version]:
        messages.append({"role": "user", "content": user})
        messages.append({"role": "assistant", "content": assistant})
    messages.append(
        {
            "role": "user",
            "content": format_article(article_title, article_body, max_body_chars=max_body_chars),
        }
    )
    return messages


__all__ = [
    "FEW_SHOT_V1",
    "FEW_SHOT_V2",
    "MAX_BODY_CHARS",
    "PROMPT_VERSION",
    "SYSTEM_V1",
    "SYSTEM_V2",
    "build_messages",
    "format_article",
    "render_system",
]
