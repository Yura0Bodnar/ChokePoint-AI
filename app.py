"""Hugging Face Spaces entry point (Gradio SDK).

Docker Spaces on this Hugging Face account need a verified billing method; the Gradio SDK
does not. This file changes nothing about the application — it only makes the existing
FastAPI app importable and runnable the way the Gradio SDK expects (`python app.py`,
listening on port 7860), so the Space can host it for free.

`chokepoint.api.main.create_app()` already registers every API router and mounts the static
frontend (`src/chokepoint/web/`) at "/" — see that module. This file adds only what a plain
`python app.py` needs that `uv run` / `pip install -e .` normally provide:

1. `src/` on `sys.path`, so `import chokepoint` resolves (same technique already used by
   `scripts/fetch_sample_news.py` and `scripts/seed_graph.py`).
2. A `uvicorn.run(...)` call on port 7860 — the Gradio SDK ignores `app_port` (that key
   applies only to `sdk: docker`; see docs/PROMPTS.md's Space config reference), so 7860 is
   the fixed port Spaces proxies for every other SDK, same as this project's own Dockerfile.
3. One `@spaces.GPU`-decorated call — see `_warm_up_zerogpu` below.

No `gradio.Blocks` is created: Spaces does not require the process it launches to actually
call into the `gradio` package, only to be launched via `app_file` and serve HTTP on 7860.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import spaces  # noqa: E402

from chokepoint.api.main import app  # noqa: E402

__all__ = ["app"]


@spaces.GPU(duration=10)
def _warm_up_zerogpu() -> bool:
    """Satisfies ZeroGPU's startup check; this project has no actual GPU workload.

    Free personal Hugging Face accounts can no longer create a plain "cpu-basic" Gradio
    Space — creating a compute Space now needs a paid plan, with one exception: free accounts
    may still host up to 2 Gradio Spaces on ZeroGPU hardware (huggingface.co/docs/hub/spaces-overview).
    That's the only free path to host this Space.

    ZeroGPU's own supervisor refuses to start a Space with zero `@spaces.GPU`-decorated
    functions ("No @spaces.GPU function detected during startup") — with none, the Space
    would occupy one of the account's 2 free ZeroGPU slots while never being able to request
    the GPU it was provisioned for, so the supervisor shuts it down. This function exists only
    to satisfy that check: it requests the shared GPU for up to 10 seconds and does nothing
    with it. Verified against the real `spaces` package (0.51.3): calling an `@spaces.GPU`
    function needs neither `torch` nor any other extra dependency when, as here, the function
    itself never touches `torch` — confirmed both outside ZeroGPU (`spaces.config.Config.zero_gpu
    == False`, where the decorator is a plain passthrough per HF's own docs) and with
    `SPACES_ZERO_GPU` set (where the call reaches HF's real GPU broker over the network rather
    than failing on a missing import).
    """
    return True


if __name__ == "__main__":
    import uvicorn

    _warm_up_zerogpu()
    uvicorn.run(app, host="0.0.0.0", port=7860)
