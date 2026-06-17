# syntax=docker/dockerfile:1
# Production image for the backend. Multi-stage: dependencies are resolved with uv in a
# build stage, then the virtualenv + app are copied into a clean runtime stage that runs
# as a non-root user (security baseline). The uv image tag is pinned for reproducibility.

# ── Build stage ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Pinned uv (static binary) from the official image — not :latest, for reproducible builds.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

WORKDIR /app

# Resolve runtime dependencies only (no dev group), cached by the lockfile.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
# To bake in-process local embeddings (Phase 7) into the image, add the extra:
#   RUN uv sync --frozen --no-install-project --no-dev --extra local

# ── Runtime stage ────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy the resolved virtualenv and the application code.
COPY --from=build /app/.venv /app/.venv
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Non-root user owns the app directory.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Liveness check against the in-container API (uses stdlib; no curl needed).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
