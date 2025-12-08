from __future__ import annotations

import asyncio
import contextlib
import re
import signal
import sys
from itertools import batched
from typing import Any, AsyncContextManager, Awaitable, Sequence

import typer
from dependency_injector.wiring import Provide, inject
from loguru import logger

from twitch_subs.application.event_handlers import register_notification_handlers
from twitch_subs.application.ports import (
    EventBus,
    NotifierProtocol,
    SubscriptionStateRepo,
    WatchlistRepository,
)
from twitch_subs.application.reporting import DayChangeScheduler
from twitch_subs.application.watcher import Watcher
from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.domain.events import UserAdded, UserRemoved
from twitch_subs.infrastructure.error import InfraError
from twitch_subs.infrastructure.error_utils import log_and_wrap
from twitch_subs.infrastructure.event_bus.rabbitmq.producer import Producer
from twitch_subs.infrastructure.logins_provider import WatchListLoginProvider
from twitch_subs.infrastructure.telegram.bot import TelegramWatchlistBot

from .config import Settings
from .container import AppContainer, build_container

app = typer.Typer(
    name="twitch-subs-checker",
    help="Watch Twitch logins and notify Telegram when broadcaster_type becomes affiliate/partner",
)
state_app = typer.Typer(help="Inspect subscription state")
app.add_typer(state_app, name="state")

logger.remove()
logger.add(sys.stderr, level="TRACE")

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,25}$", re.ASCII)


async def entry_point(func: Awaitable[int]) -> int:
    settings = Settings()
    container = await build_container(settings)
    container.wire(modules=[__name__])

    return await func


def validate_usernames(names: Sequence[str]) -> Sequence[str]:
    """Validate *value* as a Twitch username or exit with code 2."""
    for value in names:
        if not USERNAME_RE.fullmatch(value):
            typer.echo("Invalid username format", err=True)
            raise typer.Exit(2)
    return names


@contextlib.asynccontextmanager
async def _ensure_async_cm(obj: AsyncContextManager[Any] | Any):
    if hasattr(obj, "__aenter__") and hasattr(obj, "__aexit__"):
        async with obj as value:
            yield value
    else:
        yield obj


async def run_watch(
    watcher: Watcher,
    repo: WatchlistRepository,
    interval: int,
    stop: asyncio.Event,
) -> None:
    await watcher.watch(WatchListLoginProvider(repo), interval, stop)


async def run_bot(
    bot_cm: AsyncContextManager[TelegramWatchlistBot], stop: asyncio.Event
) -> None:
    """Run Telegram bot until *stop* is set."""
    async with _ensure_async_cm(bot_cm) as bot:
        task = asyncio.create_task(bot.run(), name="telegram-bot")
        try:
            await stop.wait()
        finally:
            with contextlib.suppress(asyncio.CancelledError):
                await bot.stop()
                await task


@inject
async def _add(
    usernames: list[str],
    notify: bool,
    producer: Producer = Provide[AppContainer.producer],
    service: WatchlistService = Provide[AppContainer.watchlist_service],
) -> int:
    pending_events: list[UserAdded] = []

    async with producer:
        for batch in batched(usernames, n=10):
            for username in batch:
                if not service.add(username):
                    typer.echo(f"{username} already present")
                    continue
                typer.echo(f"Added {username}")
                if notify:
                    pending_events.append(UserAdded(login=username))
        if pending_events:
            await producer.publish(*pending_events)
        return 0


@inject
async def _list_cmd(
    repo: WatchlistRepository = Provide[AppContainer.watchlist_repo],
) -> int:
    users = repo.list()
    if not users:
        typer.echo("Watchlist is empty. Use 'add' to add usernames.")
        raise typer.Exit(0)
    for name in users:
        typer.echo(name)
    return 0


@inject
async def _remove(
    usernames: list[str],
    quiet: bool,
    notify: bool,
    producer: Producer = Provide[AppContainer.producer],
    service: WatchlistService = Provide[AppContainer.watchlist_service],
) -> int:
    pending_events: list[UserRemoved] = []

    async with producer:
        for username in usernames:
            removed = service.remove(username)
            if removed:
                typer.echo(f"Removed {username}")
                if notify:
                    pending_events.append(UserRemoved(login=username))
            else:
                if quiet:
                    continue
                typer.echo(f"{username} not found", err=True)
                raise typer.Exit(1)
        if pending_events:
            await producer.publish(*pending_events)
        return 0


@inject
async def _state_get(
    login: str, repo: SubscriptionStateRepo = Provide[AppContainer.sub_state_repo]
) -> int:
    state = repo.get_sub_state(login)
    if state is None:
        typer.echo("not found", err=True)
        raise typer.Exit(1)
    typer.echo(str(state))
    return 0


@inject
async def _state_list(
    repo: SubscriptionStateRepo = Provide[AppContainer.sub_state_repo],
) -> int:
    rows = repo.list_all()
    if not rows:
        typer.echo("No subscription state found")
        raise typer.Exit(0)
    for row in rows:
        typer.echo(str(row))
    return 0


@app.command("watch", help="Watch logins from watchlist and notify on status changes")
def watch(
    interval: int = typer.Option(300, "--interval", help="Poll interval, seconds"),
) -> None:
    stop = asyncio.Event()

    tasks: list[asyncio.Task[Any]] = []
    task_errors: list[BaseException] = []

    async def wait_stop(timeout: int) -> None:
        await stop.wait()
        logger.debug("initial timeout for main tasks")

        waiters = [asyncio.wait_for(t, timeout=timeout) for t in tasks]
        for t in waiters:
            try:
                await t
            except TimeoutError as exc:  # pragma: no cover - defensive logging
                logger.opt(exception=exc).warning(
                    f"{t} can't complete with {timeout} s.",
                )

    def shutdown() -> None:
        stop.set()

    @inject
    async def main(
        settings: Settings = Provide[AppContainer.settings],
        repo: WatchlistRepository = Provide[AppContainer.watchlist_repo],
        event_bus_factory: AsyncContextManager[EventBus] = Provide[
            AppContainer.event_bus_factory
        ],
        notifier: NotifierProtocol = Provide[AppContainer.notifier],
        sub_state_repo: SubscriptionStateRepo = Provide[AppContainer.sub_state_repo],
        watcher_factory: AsyncContextManager[Watcher] = Provide[AppContainer.watcher],
        bot: AsyncContextManager[TelegramWatchlistBot] = Provide[AppContainer.bot_app],
    ) -> int:
        logins = repo.list()

        async with _ensure_async_cm(event_bus_factory) as event_bus, _ensure_async_cm(
            watcher_factory
        ) as watcher:
            scheduler = DayChangeScheduler(
                event_bus=event_bus, cron=settings.report_cron
            )

            register_notification_handlers(
                event_bus, notifier, sub_state_repo, logger=logger
            )

            logger.info(
                f"Starting watch for logins {', '.join(logins)} with interval {interval}"
            )

            loop = asyncio.get_event_loop()
            loop.add_signal_handler(sig=signal.SIGTERM, callback=shutdown)

            bot_task = loop.create_task(run_bot(bot, stop), name="run_bot")
            watcher_task = loop.create_task(
                run_watch(watcher, repo, interval, stop), name="run_watch"
            )

            tasks.extend([bot_task, watcher_task])

            def handle_task_result(task: asyncio.Task[Any]) -> None:
                try:
                    exception = task.exception()
                except asyncio.CancelledError:  # pragma: no cover - cancellation path
                    return
                if exception is not None:
                    task_errors.append(exception)
                    stop.set()

            for task in tasks:
                task.add_done_callback(handle_task_result)

            try:
                scheduler.start()
                await wait_stop(settings.task_timeout)
                logger.debug("shutdown")
                if task_errors:
                    raise InfraError(
                        "Worker tasks failed",
                        context={"errors": [repr(err) for err in task_errors]},
                    )
            except Exception as exc:  # pragma: no cover - defensive logging
                log_and_wrap(
                    exc,
                    InfraError,
                    logger,
                    context={"tasks": [t.get_name() for t in tasks]},
                )
            finally:
                scheduler.stop()
            return 0

    raise typer.Exit(asyncio.run(entry_point(main())))


@app.command("remove", help="Remove a Twitch username from the watchlist")
def remove(
    usernames: list[str] = typer.Argument(..., callback=validate_usernames),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Exit 0 even if username was absent",
    ),
    notify: bool = typer.Option(
        True, "--notify", "-n", help="Publish notification event"
    ),
) -> int:
    return asyncio.run(entry_point(_remove(usernames, quiet, notify)))


@app.command("add", help="Add a Twitch username to the watchlist")
def add(
    usernames: list[str] = typer.Argument(..., callback=validate_usernames),
    notify: bool = typer.Option(
        True, "--notify", "-n", help="Publish notification event"
    ),
) -> int:
    return asyncio.run(entry_point(_add(usernames, notify)))


@app.command("list", help="List Twitch usernames in watchlist")
def list_cmd() -> int:
    return asyncio.run(entry_point(_list_cmd()))


@state_app.command("get", help="Get stored state for LOGIN")
def state_get(login: str) -> int:
    return asyncio.run(entry_point(_state_get(login=login)))


@state_app.command("list", help="List all stored subscription states")
def state_list() -> int:
    return asyncio.run(entry_point(_state_list()))


@app.callback()
def root() -> None:
    """Root command for twitch-subs-checker."""


def main() -> None:  # pragma: no cover - CLI entry point
    """Entrypoint for the CLI."""
    app()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
