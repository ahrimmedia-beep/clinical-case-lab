"""FastAPI application factory. Construction does no I/O, so `openapi()` works offline."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.db.engine import make_engine
from app.problems import problem_response, register_problem_handlers
from app.ratelimit import make_limits
from app.routers import ai_players, attempts, cases, extract, health, insights, review

MAX_BODY_BYTES = 64 * 1024
# 20,000 characters of clinical text at up to 4 bytes each in UTF-8, plus JSON escaping.
MAX_EXTRACT_BODY_BYTES = 128 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = make_engine(get_settings().sqlalchemy_url)
    app.state.engine = engine
    try:
        yield
    finally:
        await engine.dispose()


def _operation_id(route: APIRoute) -> str:
    return route.name


def body_limit(path: str) -> int | None:
    """Bytes a request body may have. Ingest (POST /api/cases) is left to its route's own
    256 KB check (`limit_case_body`), which names the case in its message."""
    if path == "/api/cases":
        return None
    if path == "/api/extract":
        return MAX_EXTRACT_BODY_BYTES
    return MAX_BODY_BYTES


class BodySizeLimit:
    """413 problem+json for oversized bodies, before any route (or the database) runs.

    The declared Content-Length is checked up front; a chunked body without one is counted
    while it streams and cut off at the limit.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = body_limit(scope["path"]) if scope["type"] == "http" else None
        if limit is None:
            await self.app(scope, receive, send)
            return
        detail = f"A request body must be at most {limit} bytes."
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await problem_response(413, "Payload too large", detail)(scope, receive, send)
            return
        received = 0

        async def capped_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Rendered as problem+json by the HTTPException handler (app.problems).
                    raise HTTPException(413, "Payload too large")
            return message

        await self.app(scope, capped_receive, send)


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
    app.state.limits = make_limits(settings)  # per-IP windows, one set per app (ratelimit.py)
    app.add_middleware(BodySizeLimit)
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
    app.include_router(review.router, prefix="/api")
    app.include_router(insights.router, prefix="/api")
    app.include_router(ai_players.router, prefix="/api")
    return app


app = create_app()
