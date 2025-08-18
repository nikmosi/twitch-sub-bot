from __future__ import annotations

import sys
from signal import SIGTERM, signal
from types import FrameType

import typer
from dotenv import load_dotenv
from loguru import logger

from .application.watcher import Watcher
from .domain.exceptions import SigTerm
from .domain.models import TwitchAppCreds
from .infrastructure.env import require_env
from .infrastructure.state import StateRepository
from .infrastructure.telegram import TelegramNotifier
from .infrastructure.twitch import TwitchClient


app = typer.Typer(
    name="twitch-subs-checker",
    help="Watch Twitch logins and notify Telegram when broadcaster_type becomes affiliate/partner",
)

logger.remove()
logger.add(sys.stderr, level="INFO")


@app.callback()
def root() -> None:
    """Root command for twitch-subs-checker."""


def handle_sigterm(signum: int, frame: FrameType | None) -> None:
    """Handle SIGTERM by raising a domain-specific exception."""
    logger.info(f"Got sigterm {signum=}, {frame=}")
    raise SigTerm


def at_exit(notifier: TelegramNotifier) -> None:
    """Send a notification when the watcher stops."""
    logger.info("Watcher stopped by user")
    try:
        notifier.send_message("🔴 <b>Twitch Subs Watcher</b> остановлен.")
    except Exception:
        pass


@app.command("watch", help="Watch multiple logins for status changes → Telegram notify")
def watch(
    logins: list[str] = typer.Argument(...),
    interval: int = typer.Option(300, "--interval", help="Poll interval, seconds (default: 300)"),
) -> None:
    """Watch Twitch logins and notify Telegram on status changes."""

    logins = list(dict.fromkeys(logins))

    load_dotenv()

    tg_token = require_env("TELEGRAM_BOT_TOKEN")
    tg_chat = require_env("TELEGRAM_CHAT_ID")
    creds = TwitchAppCreds(
        client_id=require_env("TWITCH_CLIENT_ID"),
        client_secret=require_env("TWITCH_CLIENT_SECRET"),
    )

    twitch = TwitchClient.from_creds(creds)
    notifier = TelegramNotifier(tg_token, tg_chat)
    state_repo = StateRepository()
    watcher = Watcher(twitch, notifier, state_repo)

    signal(SIGTERM, handle_sigterm)
    logger.info(
        "Starting watch for logins {} with interval {}s", ", ".join(logins), interval
    )

    try:
        watcher.watch(logins, interval)
    except (SigTerm, KeyboardInterrupt):
        at_exit(notifier)


def main() -> None:
    """Entrypoint for the CLI."""
    app()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()

