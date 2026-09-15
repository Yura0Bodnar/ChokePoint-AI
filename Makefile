.PHONY: setup dev test lint typecheck fmt docker clean

setup:
	uv sync --all-extras --dev && uv run pre-commit install
	@test -f .env || cp .env.example .env

dev:
	uv run uvicorn chokepoint.api.main:app --reload --port 7860

test:
	uv run pytest -m "not live" --cov=chokepoint --cov-report=term-missing

lint:
	uv run ruff check . && uv run ruff format --check .

typecheck:
	uv run mypy src/chokepoint/contracts.py

fmt:
	uv run ruff check --fix . && uv run ruff format .

docker:
	@test -f .env || cp .env.example .env
	docker build -t chokepoint-ai:dev . && \
	docker run --rm -p 7860:7860 --env-file .env chokepoint-ai:dev

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
