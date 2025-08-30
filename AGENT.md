# Agent Instructions

- Use [uv](https://docs.uv.dev/) for Python environment and running scripts.
- Run scripts or tests with `uv run <script.py>` or `uv run python -m <module>`.
- Follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.
# Project Summary

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation & Usage](#installation--usage)
- [Testing & Coverage](#testing--coverage)
- [License](#license)

## Overview
**twitch_subs** tracks Twitch channels and notifies a Telegram chat when
subscriptions become available. It provides a Typer CLI and a Telegram bot to
manage a watchlist stored in SQLite.

## Features
- Poll the Twitch API and detect broadcaster type changes.
- Notify a Telegram chat about state transitions and daily reports.
- Manage the watchlist via CLI commands or the Telegram bot.

## Architecture
The project is organised as a layered application:

- **domain** – enums, entities and ports.
- **application** – watcher and watchlist service.
- **infrastructure** – Twitch and Telegram integrations, SQLite repository.
- **cli** – Typer-based command-line interface.

## Installation & Usage
### Docker Compose
```
docker compose up --build
```

### Local commands with uv
```
uv run src/main.py add <login>
uv run src/main.py list
uv run src/main.py remove <login>
uv run src/main.py watch --interval 300
```

## Testing & Coverage
```
uv run --frozen pytest --cov=src --cov-report=term-missing
```

## License
Distributed under the GNU General Public License v3.0. See LICENSE for details.
