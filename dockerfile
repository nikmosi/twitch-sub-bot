# syntax=docker/dockerfile:1

# ---------- Builder stage ----------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS builder
WORKDIR /app

# Create a non‑root user (will also be used in final stage)
ARG APP_USER=twitchbot
ARG APP_UID=10123
ARG APP_GID=10123
RUN groupadd --gid "${APP_GID}" "${APP_USER}" \
  && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin "${APP_USER}"

# Install only production dependencies (no dev)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-dev

# Copy source code and install the app into a virtual environment
COPY . .
RUN mkdir -p /app/var && chown -R "${APP_UID}:${APP_GID}" /app

# ---------- Runtime stage ----------
FROM python:3.12-slim AS runtime
ENV TERM=xterm-256color
WORKDIR /app

# Copy the non‑root user from builder (UID/GID are the same)
ARG APP_USER=twitchbot
ARG APP_UID=10123
ARG APP_GID=10123
RUN groupadd --gid "${APP_GID}" "${APP_USER}" \
  && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home --shell /usr/sbin/nologin "${APP_USER}"

# Copy only the necessary runtime files (dependencies + source)
COPY --from=builder /app /app

# Use non‑root user for execution
USER "${APP_UID}:${APP_GID}"

# Healthcheck – ensure the CLI can be invoked
HEALTHCHECK --interval=30s --timeout=3s \
  CMD /app/.venv/bin/python src/main.py --help || exit 1

# Default entrypoint (same as original)
ENTRYPOINT ["/app/.venv/bin/python", "src/main.py"]
