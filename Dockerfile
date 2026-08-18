# Multi-stage Dockerfile for Control D Sync
# Stage 1: Build dependencies
FROM python:3.13-slim AS builder

WORKDIR /app

# Install uv (pinned binary by digest)
COPY --from=ghcr.io/astral-sh/uv:0.7.9@sha256:563b73ab264117698521303e361fb781a0b421058661b4055750b6c822262d1e /uv /uvx /bin/

# Enable bytecode compilation and use copy-mode for a portable venv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy dependency manifests and install runtime deps only
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# Use the venv Python and keep runtime behavior predictable
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Copy virtual environment and application source
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser . .

# Health check (optional - for container orchestration)
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Switch to non-root user
USER appuser

# Default command
ENTRYPOINT ["python", "main.py"]
CMD ["--dry-run"]
