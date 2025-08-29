from __future__ import annotations

import asyncio
import contextlib
import re
import signal
import sys
from itertools import batched
from threading import Event, Thread
from typing import Sequence

import typer
from loguru import logger

from twitch_subs.infrastructure.logins_provider import WatchListLoginProvider

from .config import Settings
from .container import Container
from .infrastructure.telegram import TelegramNotifier, TelegramWatchlistBot

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


def at_exit(notifier: TelegramNotifier) -> None:
    """Send a notification when the watcher stops."""
    logger.info("Watcher stopped by user")
    try:
        notifier.send_message("🔴 <b>Twitch Subs Watcher</b> остановлен.")
    except Exception:
        pass


def _get_notifier(container: Container | None = None) -> TelegramNotifier | None:
    """Return Telegram notifier if credentials are configured."""
    if container is None:
        container = Container(Settings())
    token = container.settings.telegram_bot_token
    chat = container.settings.telegram_chat_id
    if token and chat:
        return container.notifier
    return None


def run_bot(bot: TelegramWatchlistBot, stop: Event) -> None:
    """Run Telegram bot until *stop* is set."""

    async def _runner() -> None:
        loop = asyncio.get_running_loop()
        task = asyncio.create_task(bot.run())
        await loop.run_in_executor(None, stop.wait)
        with contextlib.suppress(asyncio.CancelledError):
            await bot.stop()
            await task

    asyncio.run(_runner())


@app.command("watch", help="Watch logins from watchlist and notify on status changes")
def watch(
    interval: int = typer.Option(
        300, "--interval", help="Poll interval, seconds (default: 300)"
    ),
) -> None:
    """Watch Twitch logins and notify Telegram on status changes."""
    settings = Settings()

    container = Container(settings)
    repo = container.watchlist_repo
    logins = repo.list()
    watcher = container.build_watcher()
    notifier = container.notifier

    logger.info(
        "Starting watch for logins {} with interval {}s", ", ".join(logins), interval
    )

    bot = container.build_bot()

    stop = Event()

    def _request_stop(signum: int, _: object | None) -> None:
        logger.info(f"Received signal {signum=}")
        at_exit(notifier)
        stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    thread_error: list[BaseException] = []

    def _run_watcher() -> None:
        try:
            watcher.watch(WatchListLoginProvider(repo), interval, stop)
        except Exception as exc:  # pragma: no cover - defensive
            thread_error.append(exc)
            stop.set()

    watcher_thread = Thread(target=_run_watcher, daemon=False)
    watcher_thread.start()

    exit_code = 0
    try:
        run_bot(bot, stop)
    except KeyboardInterrupt:  # pragma: no cover - handled via signal
        stop.set()
    except Exception as e:
        logger.exception(f"Bot crashed, {e}")
        exit_code = 1
    finally:
        stop.set()
        watcher_thread.join(10)
        if watcher_thread.is_alive():
            logger.error("Watcher thread did not exit")
            exit_code = 1
        if thread_error:
            logger.error("Watcher thread raised: %s", thread_error[0])
            exit_code = 1

    raise typer.Exit(exit_code)


@app.command("add", help="Add a Twitch username to the watchlist")
def add(
    usernames: list[str] = typer.Argument(..., callback=validate_usernames),
    notify: bool = typer.Option(True, "--notify", "-n", help="notify in telegram"),
) -> None:
    container = Container(Settings())
    notifier = _get_notifier(container)
    service = container.watchlist_service
    for batch in batched(usernames, n=10):
        for username in batch:
            if not service.add(username):
                typer.echo(f"{username} already present")
                continue
            typer.echo(f"Added {username}")
        if notifier and notify:
            notifier.send_message(
                "\n".join(
                    [f"➕ <code>{i}</code> добавлен в список наблюдения" for i in batch]
                )
            )


@app.command("list", help="List Twitch usernames in watchlist")
def list_cmd() -> None:
    repo = Container(Settings()).watchlist_repo
    users = repo.list()
    if not users:
        typer.echo("Watchlist is empty. Use 'add' to add usernames.")
        raise typer.Exit(0)
    for name in users:
        typer.echo(name)


@app.command("remove", help="Remove a Twitch username from the watchlist")
def remove(
    usernames: list[str] = typer.Argument(..., callback=validate_usernames),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Exit 0 even if username was absent",
    ),
    notify: bool = typer.Option(True, "--notify", "-n", help="notify in telegram"),
) -> None:
    container = Container(Settings())
    notifier = _get_notifier(container)
    service = container.watchlist_service
    for username in usernames:
        removed = service.remove(username)
        if removed:
            typer.echo(f"Removed {username}")
            if notifier and notify:
                notifier.send_message(
                    f"➖ <code>{username}</code> удален из списка наблюдения",
                )
        else:
            if quiet:
                raise typer.Exit(0)
            typer.echo(f"{username} not found", err=True)
            raise typer.Exit(1)


def main() -> None:
    """Entrypoint for the CLI."""
    app()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
