# Twitch Subs Checker → Telegram Notifier

A small CLI utility that watches a list of Twitch logins and sends a Telegram message when a channel becomes subscribable.

## Features
- Polls Twitch Helix `/users` API and checks the `broadcaster_type`.
- Persists state in `.subs_status.json` to avoid duplicate notifications.
- Stores Twitch logins in `.watchlist.json` and provides CLI commands to manage it.
- Sends formatted notifications to a Telegram chat using a bot token.
- Announces start and graceful shutdown in the Telegram chat.

## Requirements
- Python 3.12+
- [uv](https://docs.uv.dev/) to manage dependencies
- Environment variables (can be set in a `.env` file):
  - `TWITCH_CLIENT_ID`
  - `TWITCH_CLIENT_SECRET`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID` – destination for messages
  - `TWITCH_SUBS_WATCHLIST` – optional path to watchlist file

## Usage
Manage the watchlist:

```bash
uv run src/main.py add <login>
uv run src/main.py list
uv run src/main.py remove <login>
```

Start watching the logins from the watchlist:

```bash
uv run src/main.py watch [--interval 300] [--watchlist path]
```

The optional `--interval` flag controls the polling delay in seconds. The watchlist
defaults to `.watchlist.json` unless overridden by `--watchlist` or
`TWITCH_SUBS_WATCHLIST`.

## License
Released under the terms of the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.

