# Pinned Python base image for deterministic builds
FROM python:3.12.9-slim

# Install git required for experiment tracking commit resolution
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install pinned uv binary matching pyproject.toml required-version
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv

# Set working directory inside container
WORKDIR /app

# Configure uv and Python runtime settings
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

# Layer caching: copy dependency manifests first
COPY pyproject.toml uv.lock ./

# Install project dependencies strictly from the lockfile without root project
RUN uv sync --locked --no-install-project

# Copy project files required by tests and tooling
COPY .python-version README.md ./
COPY .github/ ./.github/
COPY reports/ ./reports/

# Copy source code, configurations, tests, and dataset snapshot
COPY src/ ./src/
COPY configs/ ./configs/
COPY data/ ./data/
COPY tests/ ./tests/

# Install the project itself in the environment
RUN uv sync --locked

# Run the baseline training in exec form with the baseline configuration
CMD ["uv", "run", "--locked", "python", "-m", "bike_demand.train", "--config", "configs/baseline.yaml"]