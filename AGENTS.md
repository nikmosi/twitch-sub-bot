# Repository Guidelines

## Project Structure & Module Organization
Core code lives under `src/twitch_subs/` and follows a layered layout: `domain/` for models and events, `application/` for services and ports, and `infrastructure/` for adapters such as Twitch, Telegram, RabbitMQ, and SQLite. CLI entry points are in [src/main.py](/home/nik/git-repos/twitch-sub-bot/src/main.py) and [src/twitch_subs/cli.py](/home/nik/git-repos/twitch-sub-bot/src/twitch_subs/cli.py). Tests live in `tests/` and generally mirror module names, for example `tests/test_watcher.py` and `tests/test_repository_sqlite.py`. Container and local runtime files are at the repo root: `dockerfile`, `compose.yml`, `pyproject.toml`, and `.env`-driven configuration.

## Build, Test, and Development Commands
Use `uv` with Python 3.12.

- `uv sync --dev`: install runtime and development dependencies.
- `uv run src/main.py list`: run the CLI against the configured database.
- `uv run src/main.py watch --interval 300`: start the Twitch watcher loop.
- `uv run src/main.py bot`: start the Telegram bot.
- `uv run --frozen pytest`: run the full test suite with the repo’s default coverage and timeout settings.
- `uv run ruff check src`: run linting.
- `uv run ruff format src`: format source files.
- `docker compose up --build`: start the packaged stack locally.

## Coding Style & Naming Conventions
Follow existing Python conventions: 4-space indentation, type hints on public functions, and small focused modules. The codebase uses `from __future__ import annotations` broadly; keep that pattern in new modules. Use `snake_case` for modules, functions, and variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants like `USERNAME_RE`. Prefer explicit dependency boundaries through the existing `application` ports and `infrastructure` adapters. Run Ruff before opening a PR.

## Testing Guidelines
Tests use `pytest`, `pytest-asyncio`, `pytest-cov`, and `pytest-timeout`. Add tests in `tests/test_<module>.py` and keep names behavior-focused, such as `test_run_watch_invokes_watcher`. The default pytest config enforces coverage on `src/`, emits `coverage.xml`, and fails below 80% coverage. Use `@pytest.mark.asyncio` for async cases and extend `tests/conftest.py` only for shared fixtures.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit style: `feat: ...`, `fix: ...`, `refactor: ...`, `chore: ...`. Keep subjects short and imperative. PRs should include a clear summary, note any config or schema changes, and link the relevant issue when applicable. Include command output or screenshots only when behavior changes are user-visible, such as CLI or Telegram bot flows.

## Security & Configuration Tips
Do not commit secrets. Configure credentials through environment variables like `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `DB_URL`. For local work, prefer a `.env` file and verify database targets before running watcher or bot commands.
