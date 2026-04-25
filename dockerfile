# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm

ARG APP_USER=twitchbot
ARG APP_UID=10123
ARG APP_GID=10123

ENV TERM xterm-256color

WORKDIR /app

RUN groupadd --gid "${APP_GID}" "${APP_USER}" \
  && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin "${APP_USER}"

# Copy dependency files and install
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Copy the application code
COPY . .
RUN mkdir -p /app/var \
  && chown -R "${APP_UID}:${APP_GID}" /app

USER "${APP_UID}:${APP_GID}"

# Default to running the CLI; additional args can be passed at runtime
ENTRYPOINT ["uv", "run", "--no-dev", "src/main.py"]
