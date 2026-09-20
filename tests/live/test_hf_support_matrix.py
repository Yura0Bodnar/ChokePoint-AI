"""P2.2 support matrix — hits the real HF Inference API. NOT a CI gate.

Run manually:

    export HF_TOKEN=hf_xxx
    uv run pytest tests/live/test_hf_support_matrix.py -m live -s

Prints one row per model x response_format mode; copy the table into
docs/PROMPTS.md. Requires HF_HUB_OFFLINE to be unset.
"""

from __future__ import annotations

import json
import os
import statistics
import time

import pytest
from huggingface_hub.errors import HfHubHTTPError

from chokepoint.agent.parser import parse_event
from chokepoint.agent.prompts import build_messages
from chokepoint.agent.providers.hf_inference import HFInferenceProvider

pytestmark = pytest.mark.live

DEFAULT_CANDIDATES = [
    "Qwen/Qwen2.5-7B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen2.5-1.5B-Instruct",
]
# Override with a comma-separated list, e.g. HF_MATRIX_MODELS="openai/gpt-oss-20b,Qwen/Qwen3-32B"
CANDIDATES = [
    m for m in os.environ.get("HF_MATRIX_MODELS", ",".join(DEFAULT_CANDIDATES)).split(",") if m
]
TITLE = "Strike halts operations at Hamburg Port"
BODY = (
    "Dockworkers walked out today at the Port of Hamburg, halting container handling "
    "for 48 hours. Carriers warned of delays to automotive parts bound for Poland."
)
REPEATS = int(os.environ.get("HF_MATRIX_REPEATS", "3"))


def _probe(model: str, mode: str) -> tuple[str, float | None, str]:
    """Return (verdict, p50 latency seconds, note) for one model x mode."""
    token = os.environ["HF_TOKEN"]
    provider = os.environ.get("HF_INFERENCE_PROVIDER", "auto")
    p = HFInferenceProvider(model=model, token=token, provider=provider)
    p.supports_structured = mode == "json_schema"
    latencies: list[float] = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        try:
            raw = p._complete(build_messages(TITLE, BODY), mode)  # type: ignore[arg-type]
        except HfHubHTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", "?")
            return ("✗", None, f"HTTP {status}: {str(exc)[:80]}")
        latencies.append(time.perf_counter() - t0)
        try:
            parse_event(raw)
        except Exception as exc:
            return (
                "~",
                statistics.median(latencies),
                f"accepted but output invalid: {type(exc).__name__}",
            )
    return ("✓", statistics.median(latencies), f"provider={p._provider}")


@pytest.mark.skipif("HF_TOKEN" not in os.environ, reason="needs a real HF_TOKEN")
@pytest.mark.parametrize("model", CANDIDATES)
def test_support_matrix_row(model: str) -> None:
    rows = {}
    for mode in ("json_schema", "json_object", "none"):
        rows[mode] = _probe(model, mode)
    print(
        f"\n| {model} | "
        + " | ".join(
            f"{v} ({lat:.2f}s) {note}" if lat else f"{v} {note}" for v, lat, note in rows.values()
        )
        + " |"
    )
    print(json.dumps({model: rows}, default=str))
    assert any(v == "✓" for v, _, _ in rows.values()), f"{model}: no mode produced a valid event"
