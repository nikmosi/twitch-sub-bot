# Twitch Subs Checker → Telegram Notifier

A small CLI utility that watches a list of Twitch logins and sends a Telegram message when a channel becomes subscribable.

## Features
- Polls Twitch Helix `/users` API and checks the `broadcaster_type`.
- Tracks last known status in memory to avoid duplicate notifications during a run.
- Stores Twitch logins in a local SQLite database and provides CLI commands to manage it.
- Sends formatted notifications to a Telegram chat using a bot token.
- Announces start and graceful shutdown in the Telegram chat.
 - Gracefully handles SIGINT/SIGTERM and stops the watcher thread cleanly.

## Installation

### Database
The application stores the watchlist in a local SQLite database. The path is
controlled by the `DB_URL` environment variable and defaults to
`sqlite:///./data.db`. Tables are created automatically on first use.

### Dependencies
- Python 3.12+
- [uv](https://docs.uv.dev/) to manage dependencies

## Environment variables and configuration
Environment variables can be supplied directly or via a `.env` file:

- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` – destination for messages
- `DB_URL` – optional SQLite database URL (default: `sqlite:///./data.db`)
- `DB_ECHO` – set to `1` to enable SQLAlchemy echo for debugging

Configuration files:

- `.env` – environment variables for local development

## Usage
Manage the watchlist from the CLI:

```bash
uv run src/main.py add <login>
uv run src/main.py list
uv run src/main.py remove <login>
```

Start watching the logins from the watchlist:

```bash
uv run src/main.py watch --interval 300
```

The optional `--interval` flag controls the polling delay in seconds.

Run the Telegram bot to manage the watchlist directly from a chat:

```bash
uv run src/main.py bot
```

In the bot chat you can send commands:

```
/list           # show current watchlist
/add <login>    # add a login
/remove <login> # remove a login
```

## Testing
Run the test suite:

```bash
uv run pytest
```

### Docker

The provided `dockerfile` uses [tini](https://github.com/krallin/tini) as PID 1
so that `docker stop` (SIGTERM followed by SIGKILL) results in a clean shutdown.

## License
Released under the terms of the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.

