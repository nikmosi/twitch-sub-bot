# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:alpine

ENV TERM xterm-256color

RUN apk add --no-cache tini

WORKDIR /app

# Copy dependency files and install
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy the application code
COPY . .

# Default to running the CLI; additional args can be passed at runtime
ENTRYPOINT ["tini", "-g", "--", "uv", "run", "src/main.py"]
