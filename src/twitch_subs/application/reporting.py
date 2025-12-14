from __future__ import annotations

from asyncio import AbstractEventLoop
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Any, Awaitable, Mapping, ParamSpec, Protocol, cast

# pyright: reportMissingTypeStubs=false
import aiocron
from loguru import logger

from twitch_subs.application.error import RepoCantFintLoginError
from twitch_subs.application.ports import (
    EventBus,
    NotifierProtocol,
    SubscriptionStateRepo,
)
from twitch_subs.domain.events import DayChanged, LoopChecked, LoopCheckFailed
from twitch_subs.domain.models import LoginReportInfo


@dataclass(slots=True)
class DailyReportCollector:
    """Aggregate loop statistics and send a daily report when requested."""

    notifier: NotifierProtocol
    state_repo: SubscriptionStateRepo
    tracked_logins: set[str] = field(default_factory=set[str])
    checks: int = 0
    errors: int = 0

    async def handle_loop_checked(self, event: LoopChecked) -> None:
        self.tracked_logins.update(event.logins)
        self.checks += 1

    async def handle_loop_failed(self, event: LoopCheckFailed) -> None:
        self.tracked_logins.update(event.logins)
        self.checks += 1
        self.errors += 1

    async def handle_day_changed(self, _: DayChanged) -> None:
        await self._send_report()
        self._reset()

    async def _send_report(self) -> None:
        states = self._collect_states(self.tracked_logins)
        await self.notifier.notify_report(states, self.checks, self.errors)

    def _collect_states(self, logins: Iterable[str]) -> list[LoginReportInfo]:
        report: list[LoginReportInfo] = []
        for login in sorted(logins):
            state = self.state_repo.get_sub_state(login)
            if state is None:
                raise RepoCantFintLoginError(login=login)
            report.append(LoginReportInfo(login=login, broadcaster=state.status))
        return report

    def _reset(self) -> None:
        self.tracked_logins.clear()
        self.checks = 0
        self.errors = 0


P = ParamSpec("P")


class CronJob(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


# Разрешаем и sync, и async функции
CronCallable = Callable[P, Awaitable[Any] | Any]


def crontab(
    spec: str,
    func: CronCallable[P] | None = None,
    *,
    args: Sequence[Any] = (),
    kwargs: Mapping[str, Any] | None = None,
    start: bool = True,
    loop: AbstractEventLoop | None = None,
    tz: tzinfo | None = None,
) -> CronJob:
    return cast(
        CronJob,
        aiocron.crontab(  # pyright: ignore
            spec, func, args=args, kwargs=kwargs, start=start, loop=loop, tz=tz
        ),
    )


@dataclass(slots=True)
class DayChangeScheduler:
    """Schedule :class:`DayChanged` events using ``aiocron``."""

    event_bus: EventBus
    cron: str = "0 0 * * *"
    _cron_job: CronJob | None = None
    _crontab_factory: Callable[..., CronJob] = crontab

    def start(self) -> None:
        if self._cron_job is not None:
            return
        job = self._crontab_factory(self.cron, func=self._emit, start=True)
        self._cron_job = job
        logger.info("started DayChangeScheduler")

    def stop(self) -> None:
        if self._cron_job is None:
            return
        self._cron_job.stop()
        self._cron_job = None

    async def _emit(self) -> None:
        await self.event_bus.publish(DayChanged())
