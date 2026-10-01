"""Async engine (asyncpg) and the FastAPI dependency that hands it to route handlers.

Handlers open a connection themselves (`async with engine.connect() as conn`). A yield
dependency would check out a pooled connection before FastAPI validates the request body,
so every malformed request would cost a connection (and need a live database to get its 422).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings


def make_engine(url: str) -> AsyncEngine:
    """Create the pool. No I/O happens here; connections open lazily on first use."""
    return create_async_engine(
        url,
        pool_size=5,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def get_engine(request: Request) -> AsyncEngine:
    """The engine the lifespan created; built on first use when no lifespan ran (no I/O)."""
    engine: AsyncEngine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        engine = make_engine(get_settings().sqlalchemy_url)
        request.app.state.engine = engine
    return engine


EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
