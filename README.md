# Twitch Subs Checker → Telegram Notifier

A small CLI utility that watches a list of Twitch logins and sends a Telegram message when a channel becomes subscribable.

## Features
- Polls Twitch Helix `/users` API and checks the `broadcaster_type`.
- Persists state in `.subs_status.json` to avoid duplicate notifications.
- Stores Twitch logins in `.watchlist.json` and provides CLI commands to manage it.
- Sends formatted notifications to a Telegram chat using a bot token.
- Announces start and graceful shutdown in the Telegram chat.

## Installation

### Database
No external database is required. The application persists its state in two
JSON files in the project root:

- `.watchlist.json` – list of Twitch logins to monitor
- `.subs_status.json` – last known `broadcaster_type` for each login

They are created automatically, but you can initialize them manually:

```bash
uv run src/main.py add some_login   # creates .watchlist.json
uv run src/main.py watch            # creates .subs_status.json
```

### Dependencies
- Python 3.12+
- [uv](https://docs.uv.dev/) to manage dependencies

## Environment variables and configuration
Environment variables can be supplied directly or via a `.env` file:

- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` – destination for messages
- `TWITCH_SUBS_WATCHLIST` – optional path to watchlist file

Configuration files:

- `.env` – environment variables for local development
- `.watchlist.json` – maintained manually or through the CLI/Telegram bot
- `.subs_status.json` – watcher state to avoid duplicate notifications

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

The optional `--interval` flag controls the polling delay in seconds. The
watchlist defaults to `.watchlist.json` unless overridden by `--watchlist` or
`TWITCH_SUBS_WATCHLIST`.

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

## License
Released under the terms of the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.

