from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from signal import SIGTERM, signal
from types import FrameType
from typing import Sequence

import typer
from loguru import logger

from twitch_subs.infrastructure.logings import WatchListLoginProvider

from .application.watcher import Watcher
from .config import Settings
from .domain.exceptions import SigTerm
from .domain.models import TwitchAppCreds
from .infrastructure import watchlist
from .infrastructure.state import StateRepository
from .infrastructure.telegram import TelegramNotifier, TelegramWatchlistBot
from .infrastructure.twitch import TwitchClient

app = typer.Typer(
    name="twitch-subs-checker",
    help="Watch Twitch logins and notify Telegram when broadcaster_type becomes affiliate/partner",
)

logger.remove()
logger.add(sys.stderr, level="INFO")

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,25}$", re.ASCII)


def validate_usernames(names: Sequence[str]) -> Sequence[str]:
    """Validate *value* as a Twitch username or exit with code 2."""
    for value in names:
        if not USERNAME_RE.fullmatch(value):
            typer.echo("Invalid username format", err=True)
            raise typer.Exit(2)
    return names


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


def _get_notifier() -> TelegramNotifier | None:
    """Return Telegram notifier if credentials are configured."""
    settings = Settings()
    token = settings.telegram_bot_token
    chat = settings.telegram_chat_id
    if token and chat:
        return TelegramNotifier(token, chat)
    return None


@app.command("watch", help="Watch logins from watchlist and notify on status changes")
def watch(
    interval: int = typer.Option(
        300, "--interval", help="Poll interval, seconds (default: 300)"
    ),
    watchlist_path: Path | None = typer.Option(
        None, "--watchlist", help="Path to watchlist file"
    ),
) -> None:
    """Watch Twitch logins and notify Telegram on status changes."""

    path = watchlist.resolve_path(watchlist_path)
    logins = watchlist.load(path)
    if not logins:
        typer.echo("Watchlist is empty", err=True)
        raise typer.Exit(1)

    settings = Settings()
    creds = TwitchAppCreds(
        client_id=settings.twitch_client_id,
        client_secret=settings.twitch_client_secret,
    )

    tg_token = settings.telegram_bot_token
    tg_chat = settings.telegram_chat_id

    twitch = TwitchClient.from_creds(creds)
    notifier = TelegramNotifier(tg_token, tg_chat)
    state_repo = StateRepository()
    watcher = Watcher(twitch, notifier, state_repo)

    signal(SIGTERM, handle_sigterm)
    logger.info(
        "Starting watch for logins {} with interval {}s", ", ".join(logins), interval
    )

    try:
        watcher.watch(WatchListLoginProvider(), interval)
    except (SigTerm, KeyboardInterrupt):
        at_exit(notifier)


@app.command("add", help="Add a Twitch username to the watchlist")
def add(
    usernames: list[str] = typer.Argument(..., callback=validate_usernames),
    watchlist_path: Path | None = typer.Option(
        None, "--watchlist", help="Path to watchlist file"
    ),
    notify: bool = typer.Option(True, "--notify", "-n", help="notify in telegram"),
) -> None:
    notifier = _get_notifier()
    for username in usernames:
        path = watchlist.resolve_path(watchlist_path)
        added = watchlist.add(path, username)
        if added:
            typer.echo(f"Added {username}")
            if notifier and notify:
                notifier.send_message(
                    f"➕ <code>{username}</code> добавлен в список наблюдения"
                )
        else:
            typer.echo(f"{username} already present")


@app.command("list", help="List Twitch usernames in watchlist")
def list_cmd(
    watchlist_path: Path | None = typer.Option(
        None, "--watchlist", help="Path to watchlist file"
    ),
) -> None:
    path = watchlist.resolve_path(watchlist_path)
    users = watchlist.load(path)
    if not users:
        typer.echo("Watchlist is empty. Use 'add' to add usernames.")
        raise typer.Exit(0)
    for name in users:
        typer.echo(name)


@app.command("remove", help="Remove a Twitch username from the watchlist")
def remove(
    usernames: list[str] = typer.Argument(..., callback=validate_usernames),
    watchlist_path: Path | None = typer.Option(
        None, "--watchlist", help="Path to watchlist file"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Exit 0 even if username was absent"
    ),
    notify: bool = typer.Option(True, "--notify", "-n", help="notify in telegram"),
) -> None:
    notifier = _get_notifier()
    for username in usernames:
        path = watchlist.resolve_path(watchlist_path)
        removed = watchlist.remove(path, username)
        if removed:
            typer.echo(f"Removed {username}")
            if notifier and notify:
                notifier.send_message(
                    f"➖ <code>{username}</code> удален из списка наблюдения"
                )
            return
        if quiet:
            raise typer.Exit(0)
        typer.echo(f"{username} not found", err=True)
        raise typer.Exit(1)


@app.command("bot", help="Run Telegram bot to manage the watchlist")
def bot_cmd(
    watchlist_path: Path | None = typer.Option(
        None, "--watchlist", help="Path to watchlist file"
    ),
) -> None:
    path = watchlist.resolve_path(watchlist_path)
    token = Settings().telegram_bot_token
    bot = TelegramWatchlistBot(token, path)
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        typer.echo("Bot stopped")


def main() -> None:
    """Entrypoint for the CLI."""
    app()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
