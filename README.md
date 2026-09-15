<<<<<<< HEAD
# ChokePoint-AI
=======
# ChokePoint AI

**Supply Chain Shock Simulator.** Ingest geopolitical / logistics news, extract a structured
disruption event with an LLM agent, overlay it on a dependency graph, and forecast which
industries and markets suffer next.

See [`ARCHITECTURE_AND_PLAN.md`](ARCHITECTURE_AND_PLAN.md) for the full architecture, tech
stack, repository structure, and 3-person division of labor. This is the source of truth for
the project — read it before opening a PR.

## Status

Day-1 vertical slice: the FastAPI service, DI seams, Docker packaging, and CI/CD pipeline are
in place, wired against **stub** implementations (`StubLLMProvider`, `StubGraphStore`) so the
API is fully runnable end-to-end before the real graph engine and LLM agent land. See
`PROMPT_P1_DATA_GRAPH.md` and `PROMPT_P2_AGENT_LLM.md` for those next steps.

## Quickstart

```bash
git clone <repo-url> && cd ChokePoint-AI
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
make setup          # installs deps, installs pre-commit, copies .env.example -> .env
make test           # must be green before you write a line
make dev            # http://localhost:7860/docs
```

Or with Docker:

```bash
make docker         # builds the image and runs it on http://localhost:7860
```

## Try it

```bash
curl -s http://localhost:7860/healthz

curl -s -X POST http://localhost:7860/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"text": "A dockworker strike has halted operations at Hamburg Port."}' \
  | python3 -m json.tool
```

Or open `http://localhost:7860/` for the placeholder demo page.

## Project layout

```text
src/chokepoint/
├── contracts.py     # frozen shared data contracts — read this first
├── config.py        # Settings
├── api/             # FastAPI app, routers, DI seams (deps.py), orchestrator
├── agent/           # LLM extraction agent (Person 2)
├── graph/           # dependency graph + shock propagation (Person 1)
└── web/             # static demo UI
```

## Deployment

CI (`.github/workflows/ci.yml`) lints, type-checks, tests, and builds the Docker image on
every push. `.github/workflows/deploy.yml` pushes `main` directly to a Hugging Face Space's
git remote on merge — no container registry, no Terraform. Requires the repo secrets
`HF_TOKEN` and `HF_SPACE`, set manually via GitHub Settings → Secrets.
>>>>>>> b1ee98e (feat(api): bootstrap FastAPI skeleton, DI stubs, Docker, CI/CD)
