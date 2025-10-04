from __future__ import annotations

import asyncio
import contextlib
import re
import signal
import sys
from itertools import batched
from typing import Sequence

import typer
from loguru import logger

from twitch_subs.application.watcher import Watcher
from twitch_subs.domain.ports import WatchlistRepository
from twitch_subs.infrastructure.logins_provider import WatchListLoginProvider

from .config import Settings
from .container import Container
from .infrastructure.telegram import TelegramNotifier, TelegramWatchlistBot

app = typer.Typer(
    name="twitch-subs-checker",
    help="Watch Twitch logins and notify Telegram when broadcaster_type becomes affiliate/partner",
)
state_app = typer.Typer(help="Inspect subscription state")
app.add_typer(state_app, name="state")

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


def _get_notifier(container: Container | None = None) -> TelegramNotifier | None:
    """Return Telegram notifier if credentials are configured."""
    if container is None:
        container = Container(Settings())
    token = container.settings.telegram_bot_token
    chat = container.settings.telegram_chat_id
    if token and chat:
        return container.notifier
    return None


async def run_watch(
    watcher: Watcher, repo: WatchlistRepository, interval: int, stop: asyncio.Event
):
    await watcher.watch(WatchListLoginProvider(repo), interval, stop)


async def run_bot(bot: TelegramWatchlistBot, stop: asyncio.Event) -> None:
    """Run Telegram bot until *stop* is set."""

    task = asyncio.create_task(bot.run())
    await stop.wait()
    with contextlib.suppress(asyncio.CancelledError):
        await bot.stop()
        await task


@state_app.command("get", help="Get stored state for LOGIN")
def state_get(login: str) -> None:
    repo = Container(Settings()).sub_state_repo
    state = repo.get_sub_state(login)
    if state is None:
        typer.echo("not found", err=True)
        raise typer.Exit(1)
    typer.echo(str(state))


@state_app.command("list", help="List all stored subscription states")
def state_list() -> None:
    repo = Container(Settings()).sub_state_repo
    rows = repo.list_all()
    if not rows:
        typer.echo("No subscription state found")
        raise typer.Exit(0)
    for row in rows:
        typer.echo(str(row))


@app.command("watch", help="Watch logins from watchlist and notify on status changes")
def watch(
    interval: int = typer.Option(300, "--interval", help="Poll interval, seconds"),
) -> None:
    stop = asyncio.Event()
    settings = Settings()
    container = Container(settings)
    repo = container.watchlist_repo
    logins = repo.list()
    watcher = container.build_watcher()
    bot = container.build_bot()

    logger.info(
        "Starting watch for logins %s with interval %ss", ", ".join(logins), interval
    )

    def shutdown():
        stop.set()

    def main() -> int:
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(sig=signal.SIGTERM, callback=shutdown)

        loop.create_task(run_bot(bot, stop), name="run_bot")
        loop.create_task(run_watch(watcher, repo, interval, stop), name="run_watch")

        exit_code = 0
        try:
            loop.run_forever()
        except Exception as e:
            logger.opt(exception=e).exception("Worker crashed")
            exit_code = 1
        finally:
            loop.close()

        return exit_code

    raise typer.Exit(main())


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
            asyncio.run(
                notifier.send_message(
                    "\n".join(
                        [
                            f"➕ <code>{i}</code> добавлен в список наблюдения"
                            for i in batch
                        ]
                    )
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
                asyncio.run(
                    notifier.send_message(
                        f"➖ <code>{username}</code> удален из списка наблюдения",
                    )
                )
        else:
            if quiet:
                raise typer.Exit(0)
            typer.echo(f"{username} not found", err=True)
            raise typer.Exit(1)


def main() -> None:  # pragma: no cover - CLI entry point
    """Entrypoint for the CLI."""
    app()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
