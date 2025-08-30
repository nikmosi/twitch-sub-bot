# Twitch Subs Watcher

## Overview
**twitch_subs** is a Twitch subscriptions and watchlist tracker that sends
notifications to Telegram when a channel becomes subscribable. It ships with a
Typer-powered CLI and a small Telegram bot for watchlist management.

## Features
- Poll the Twitch Helix API and track broadcaster type changes.
- Persist the watchlist in SQLite and expose CRUD operations via CLI or bot.
- Send formatted Telegram messages for status changes, daily reports and
  lifecycle events.
- Gracefully handle SIGINT/SIGTERM and persist state between runs.

## Architecture
The project follows a layered design:

- **domain** – core models, ports and domain exceptions.
- **application** – services such as the watcher and watchlist service.
- **infrastructure** – adapters for Twitch API, Telegram bot and SQLite
  repository.
- **cli** – entry points implemented with [Typer](https://typer.tiangolo.com/).

## Technologies
Python · uv · Typer · SQLite · Telegram Bot API · Twitch API · Docker

## Installation & Usage
### Configuration
Environment variables (or a `.env` file) control credentials and database
location:

```
TWITCH_CLIENT_ID
TWITCH_CLIENT_SECRET
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID      # destination for messages
DB_URL                # defaults to sqlite:///./data.db
DB_ECHO               # set to 1 for SQL echo
```

### Run with Docker Compose

```bash
docker compose up --build
```

### Run locally with uv
Manage the watchlist:

```bash
uv run src/main.py add <login>
uv run src/main.py list
uv run src/main.py remove <login>
```

Start the watcher:

```bash
uv run src/main.py watch --interval 300
```

Optional: run the Telegram bot to manage the watchlist from chat:

```bash
uv run src/main.py bot
```

## Testing & Coverage

```bash
uv run --frozen pytest --cov=src --cov-report=term-missing
```

## License
Released under the terms of the GNU General Public License v3.0. See
[LICENSE](LICENSE) for details.

