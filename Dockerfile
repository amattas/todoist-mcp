# =============================================================================
# Build stage: Compile dependencies and create wheels
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and build wheels
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# =============================================================================
# Runtime stage: Minimal image with only runtime dependencies
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install only runtime dependencies (no gcc, no build tools)
# Keep image as lean as possible for fast cold starts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy pre-built wheels from builder stage
COPY --from=builder /wheels /wheels

# Install Python dependencies from wheels (much faster than building)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --no-deps /wheels/*.whl && \
    rm -rf /wheels

# Copy application code from src/
COPY src/ ./src/

# Precompile Python bytecode for faster startup
RUN python -m compileall -q /app

# Create a non-root user to run the app
RUN useradd -m -u 1000 mcp && chown -R mcp:mcp /app
USER mcp

# Set environment variables for optimal performance
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOST=0.0.0.0
ENV PORT=8080

# Expose port 8080 for HTTP access
EXPOSE 8080

# Lightweight health check that doesn't trigger service initialization
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/app/health').read()" || exit 1

# Run with uvloop and httptools for maximum performance
# Single worker for scale-to-zero scenarios (less memory, faster startup)
CMD ["python", "-m", "uvicorn", "src.server_remote:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "uvloop", "--http", "httptools", "--workers", "1", "--log-level", "warning", "--no-access-log"]
