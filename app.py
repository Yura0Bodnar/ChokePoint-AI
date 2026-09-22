"""Hugging Face Spaces entry point (Gradio SDK).

Docker Spaces on this Hugging Face account need a verified billing method; the Gradio SDK
does not. This file changes nothing about the application — it only makes the existing
FastAPI app importable and runnable the way the Gradio SDK expects (`python app.py`,
listening on port 7860), so the Space can host it for free.

`chokepoint.api.main.create_app()` already registers every API router and mounts the static
frontend (`src/chokepoint/web/`) at "/" — see that module. This file adds only the two things
a plain `python app.py` needs that `uv run` / `pip install -e .` normally provide:

1. `src/` on `sys.path`, so `import chokepoint` resolves (same technique already used by
   `scripts/fetch_sample_news.py` and `scripts/seed_graph.py`).
2. A `uvicorn.run(...)` call on port 7860 — the Gradio SDK ignores `app_port` (that key
   applies only to `sdk: docker`; see docs/PROMPTS.md's Space config reference), so 7860 is
   the fixed port Spaces proxies for every other SDK, same as this project's own Dockerfile.

No `gradio.Blocks` is created: Spaces does not require the process it launches to actually
call into the `gradio` package, only to be launched via `app_file` and serve HTTP on 7860.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from chokepoint.api.main import app  # noqa: E402

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)
