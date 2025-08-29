# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:alpine

ENV TERM xterm-256color

WORKDIR /app

# Copy dependency files and install
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Copy the application code
COPY . .

# Default to running the CLI; additional args can be passed at runtime
ENTRYPOINT ["uv", "run", "src/main.py"]
