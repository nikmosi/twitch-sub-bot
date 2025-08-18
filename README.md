# Twitch Subs Checker → Telegram Notifier

A small CLI utility that watches a list of Twitch logins and sends a Telegram message when a channel becomes subscribable.

## Features
- Polls Twitch Helix `/users` API and checks the `broadcaster_type`.
- Persists state in `.subs_status.json` to avoid duplicate notifications.
- Sends formatted notifications to a Telegram chat using a bot token.
- Announces start and graceful shutdown in the Telegram chat.

## Requirements
- Python 3.12+
- `httpx` library
- Environment variables:
  - `TWITCH_CLIENT_ID`
  - `TWITCH_CLIENT_SECRET`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID` – destination for messages

## Usage
Install dependencies and run the watcher:

```bash
pip install httpx
python main.py watch <login1> [<login2> ...] [--interval 300]
```

The optional `--interval` flag controls the polling delay in seconds.

## License
Released under the terms of the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.

