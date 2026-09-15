# ---- base: shared uv install + dependency manifests ----
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./

# ---- dev: full dependency set (pytest, ruff, mypy, ...), source is volume-mounted ----
FROM base AS dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-extras --dev --no-install-project
COPY src/ ./src/
COPY tests/ ./tests/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --all-extras --dev
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 7860
CMD ["uv", "run", "uvicorn", "chokepoint.api.main:app", "--host", "0.0.0.0", "--port", "7860", "--reload"]

# ---- builder: production dependency set only ----
FROM base AS builder
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# ---- runtime: lean, non-root, production (default build target) ----
FROM python:3.12-slim AS runtime
RUN useradd -m -u 1000 app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src/ ./src/
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:7860/healthz').status_code==200 else 1)"
CMD ["uvicorn", "chokepoint.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
