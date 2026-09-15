# RUN_INSTRUCTIONS.md

## 1. Setup

```bash
cp .env.example .env
```
Creates the local environment file used by docker compose.

## 2. Development Server

```bash
docker compose up --build
```
Builds the dev image and starts the hot-reloading API container on port 7860.

```bash
docker compose up -d --build
```
Same as above, detached in the background.

```bash
docker compose down
```
Stops and removes the running containers.

## 3. Testing

```bash
docker compose exec api uv run pytest -m "not live" --cov=chokepoint --cov-report=term-missing
```
Runs the test suite with coverage inside the running container.

```bash
docker compose run --rm api uv run pytest -m "not live" --cov=chokepoint --cov-report=term-missing
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
docker compose exec api uv run mypy src/chokepoint/contracts.py
```
Type-checks contracts.py in strict mode inside the running container.

## 5. Endpoint Smoke Tests

```bash
curl -s http://localhost:7860/healthz
```
Checks the liveness endpoint.

```bash
curl -s http://localhost:7860/readyz
```
Checks the readiness endpoint.

```bash
curl -s -X POST http://localhost:7860/api/v1/simulate -H "Content-Type: application/json" -d '{}'
```
Sends an empty body to /api/v1/simulate and expects a 422 validation error.

```bash
curl -s -X POST http://localhost:7860/api/v1/simulate \
  -H "Content-Type: application/json" \
  -d '{"event":{"event_type":"strike","locations":[{"raw":"Hamburg Port","node_id":"port_hamburg"}],"affected_goods":["auto parts"],"severity":4,"confidence":0.8,"summary":"test"}}'
```
Sends a minimal valid payload to /api/v1/simulate and returns a SimulationResult.
