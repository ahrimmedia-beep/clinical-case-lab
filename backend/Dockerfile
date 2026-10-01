# syntax=docker/dockerfile:1.7

# ---- builder: resolve the locked runtime dependencies into /app/.venv ----
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
# Source last, so code edits do not invalidate the dependency layer.
# Everything not in .dockerignore is copied: app, alembic, seeds, pipeline, evals.
COPY . .

# ---- runtime: slim, non-root, no build tooling ----
FROM python:3.13-slim
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.source="https://github.com/ahrimmedia-beep/clinical-case-lab" \
      org.opencontainers.image.revision=$GIT_SHA
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --home-dir /app app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080
USER app
EXPOSE 8080
# sh -c so ${PORT} expands; exec so uvicorn is PID 1 and receives SIGTERM from Cloud Run.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*'"]
