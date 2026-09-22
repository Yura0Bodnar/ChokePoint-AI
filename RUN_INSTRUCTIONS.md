# RUN_INSTRUCTIONS.md

Everything below runs through **Docker Compose**; the only prerequisites are Docker (Compose v2)
and `curl`. The default configuration needs **no API key and no network** beyond pulling the image.

## 1. Setup

```bash
cp .env.example .env
```
Creates the environment file used by docker compose. The defaults use the offline `stub` LLM
provider and the real dependency graph.

## 2. Start the app

```bash
docker compose up --build
```
Builds the dev image and starts the hot-reloading API on port 7860.

- Demo UI: http://localhost:7860/
- Interactive API docs: http://localhost:7860/docs

```bash
docker compose up -d --build
```
Same as above, detached in the background.

```bash
docker compose down
```
Stops and removes the containers (the `hf-cache` model volume is kept).

### Using the UI

Press **Simulate** (a Hamburg strike headline is pre-filled). You get the extracted event JSON, an
intelligence brief, the impact graph and the ranked forecast table. Drag the severity slider to
re-run the graph instantly without calling the LLM.

## 3. Testing

```bash
docker compose exec api uv run pytest --cov=chokepoint --cov-report=term-missing
```
Runs the test suite with coverage inside the running container (a few seconds). Tests marked
`live` (real Hugging Face calls) and `local` (real model weights, minutes of CPU time) are excluded
by default through `pyproject.toml`; do not pass `-m` yourself, or those tests will run.

```bash
docker compose run --rm api uv run pytest --cov=chokepoint --cov-report=term-missing
```
Runs the same test suite in a one-off container if the server is not already running.

## 4. Linting & Type Checking

```bash
docker compose exec api uv run ruff check .
```
Lints the codebase inside the running container.

```bash
docker compose exec api uv run ruff format --check .
```
Verifies code formatting inside the running container.

```bash
docker compose exec api uv run mypy src
```
Type-checks the whole `chokepoint` package inside the running container.

## 5. Endpoint Smoke Tests

```bash
curl -s http://localhost:7860/healthz
```
Checks the liveness endpoint (`{"status":"ok"}`).

```bash
curl -s http://localhost:7860/readyz
```
Checks the readiness endpoint and reports the active LLM provider and graph backend.

```bash
curl -s -X POST http://localhost:7860/api/v1/simulate -H "Content-Type: application/json" -d '{}'
```
Sends an empty body to /api/v1/simulate and expects a 422 validation error.

```bash
curl -s -X POST http://localhost:7860/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"event":{"event_type":"strike","locations":[{"raw":"Hamburg Port","node_id":"port_hamburg"}],"affected_goods":["auto parts"],"severity":4,"confidence":0.8,"summary":"test"}}'
```
Sends a minimal valid event and returns a SimulationResult with the ranked cascade (no LLM involved).

```bash
curl -s -X POST http://localhost:7860/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"text":"Dockworkers strike at Hamburg Port halts container handling."}'
```
Runs the full pipeline: text, LLM extraction, graph simulation. With the default `stub` provider the
extraction step returns a canned Hamburg strike and the result is flagged `"degraded": true`.

## 6. Optional: real LLM (Hugging Face)

Edit `.env`, then re-run `docker compose up -d`:

```dotenv
LLM_PROVIDER=hf
HF_TOKEN=hf_your_token_here
HF_MODEL=openai/gpt-oss-20b
```
The model must be served by a free-tier Inference Provider; `openai/gpt-oss-20b` is the measured
default (see `docs/PROMPTS.md` §3). Free credits are small, so expect HTTP 402 once they run out.

## 7. Optional: local CPU fallback

When Hugging Face fails, the API answers HTTP 424 and the UI asks whether to run the model locally
(about 40 s). The dev image already contains the CPU-only `torch` and `transformers`. Download the
weights (about 3 GB, needs roughly 8 GB of RAM to run) into the persistent `hf-cache` volume once:

```bash
docker compose run --rm api hf download Qwen/Qwen2.5-1.5B-Instruct
```
Without this step the first local run downloads the weights on demand.
