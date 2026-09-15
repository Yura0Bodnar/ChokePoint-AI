"""FastAPI app factory: lifespan, CORS, error handling, routing, static UI.

See ARCHITECTURE_AND_PLAN.md §3 (System Architecture) and §9 (API Surface).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from chokepoint.api.middleware import RequestContextMiddleware
from chokepoint.api.routers import health, simulate
from chokepoint.config import get_settings
from chokepoint.logging import configure_logging, get_logger

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

logger = get_logger("chokepoint.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "startup",
        extra={
            "method": "-",
            "path": "-",
            "status_code": 0,
            "duration_ms": 0.0,
        },
    )
    yield
    logger.info(
        "shutdown",
        extra={
            "method": "-",
            "path": "-",
            "status_code": 0,
            "duration_ms": 0.0,
        },
    )


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ChokePoint AI",
        description="Supply Chain Shock Simulator — OSINT-driven cascading impact forecasts.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)

    if settings.app_env == "dev":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "unhandled exception",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": 0.0,
            },
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected error occurred. This has been logged.",
                "request_id": request_id,
            },
        )

    app.include_router(health.router)
    app.include_router(simulate.router)

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    return app


app = create_app()
