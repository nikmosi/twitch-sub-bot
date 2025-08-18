# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install curl to fetch the uv installer
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy dependency files and install
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy the application code
COPY . .

# Default to running the CLI; additional args can be passed at runtime
ENTRYPOINT ["uv", "run", "main.py"]
