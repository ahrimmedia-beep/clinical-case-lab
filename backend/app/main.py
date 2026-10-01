"""FastAPI application factory. Construction does no I/O, so `openapi()` works offline."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.config import get_settings
from app.problems import register_problem_handlers
from app.routers import attempts, cases, extract, health


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Plan 01: open the async engine here and dispose it on shutdown.
    yield


def _operation_id(route: APIRoute) -> str:
    return route.name


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Case Lab API",
        version="0.1.0",
        description="Clinical cases: ingest, play, score, and extract from raw text with an LLM.",
        lifespan=lifespan,
        separate_input_output_schemas=False,
        generate_unique_id_function=_operation_id,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Internal-Key"],
    )
    register_problem_handlers(app)
    app.include_router(health.router)
    app.include_router(cases.router, prefix="/api")
    app.include_router(attempts.router, prefix="/api")
    app.include_router(extract.router, prefix="/api")
    return app


app = create_app()
