# Multi-stage Dockerfile for Control D Sync
# Stage 1: Build/dependencies
FROM python:3.13-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt requirements-dev.txt ./

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (including dev)
RUN pip install --no-cache-dir -r requirements-dev.txt

# Stage 2: Runtime
FROM python:3.13-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Copy application code
COPY --chown=appuser:appuser . .

# Create .pytest_cache and make it writable for any user (needed in containers with non-root)
RUN mkdir -p .pytest_cache && chmod -R 777 .pytest_cache

# Switch to non-root user
USER appuser

# Health check (optional - for container orchestration)
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Default command
ENTRYPOINT ["python", "main.py"]
CMD ["--dry-run"]
