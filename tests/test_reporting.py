from collections.abc import Iterable

import pytest

from twitch_subs.application.reporting import DailyReportCollector, DayChangeScheduler
from twitch_subs.application.ports import EventBus, NotifierProtocol, SubscriptionStateRepo
from twitch_subs.domain.events import DayChanged, LoopCheckFailed, LoopChecked
from twitch_subs.domain.models import BroadcasterType, LoginReportInfo, SubState


class StubRepo(SubscriptionStateRepo):
    def __init__(self, states: Iterable[SubState]) -> None:
        self._states = {state.login: state for state in states}

    def get_sub_state(self, login: str) -> SubState | None:
        return self._states.get(login)

    def upsert_sub_state(self, state: SubState) -> None:  # pragma: no cover - unused
        self._states[state.login] = state

    def set_many(self, states: Iterable[SubState]) -> None:  # pragma: no cover - unused
        for state in states:
            self._states[state.login] = state


class StubNotifier(NotifierProtocol):
    def __init__(self) -> None:
        self.reports: list[tuple[list[LoginReportInfo], int, int]] = []

    async def notify_about_change(self, status, curr) -> None:  # pragma: no cover - unused
        raise NotImplementedError

    async def notify_about_start(self) -> None:  # pragma: no cover - unused
        raise NotImplementedError

    async def notify_about_stop(self) -> None:  # pragma: no cover - unused
        raise NotImplementedError

    async def notify_report(
        self, states, checks: int, errors: int
    ) -> None:  # pragma: no cover - interface contract
        self.reports.append((list(states), checks, errors))

    async def send_message(
        self, text: str, disable_web_page_preview: bool = True, disable_notification: bool = False
    ) -> None:  # pragma: no cover - unused
        raise NotImplementedError


class StubEventBus(EventBus):
    def __init__(self) -> None:
        self.events: list[DayChanged] = []

    async def publish(self, *events) -> None:
        self.events.extend(events)

    def subscribe(self, event_type, handler):  # pragma: no cover - unused in tests
        raise NotImplementedError


class StubCron:
    def __init__(self, func):
        self.func = func
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_collector_sends_report_and_resets() -> None:
    repo = StubRepo(
        [
            SubState("foo", True, tier=BroadcasterType.AFFILIATE.value, since=None),
            SubState("bar", False, tier=None, since=None),
        ]
    )
    notifier = StubNotifier()
    collector = DailyReportCollector(notifier, repo)

    await collector.handle_loop_checked(LoopChecked(logins=("foo",)))
    await collector.handle_loop_failed(LoopCheckFailed(logins=("bar",), error="boom"))
    await collector.handle_day_changed(DayChanged())

    assert notifier.reports == [
        (
            [
                LoginReportInfo("bar", BroadcasterType.NONE.value),
                LoginReportInfo("foo", BroadcasterType.AFFILIATE.value),
            ],
            2,
            1,
        )
    ]
    assert collector.checks == 0
    assert collector.errors == 0
    assert collector.tracked_logins == set()


@pytest.mark.asyncio
async def test_scheduler_emits_day_changed() -> None:
    bus = StubEventBus()

    created = {}

    def fake_crontab(cron: str, func, start: bool):
        created["cron"] = cron
        created["start"] = start
        created["func"] = func
        return StubCron(func)

    scheduler = DayChangeScheduler(bus, cron="*/5 * * * *")
    scheduler._crontab_factory = fake_crontab
    scheduler.start()

    assert isinstance(scheduler._cron_job, StubCron)
    assert created == {
        "cron": "*/5 * * * *",
        "start": True,
        "func": created["func"],
    }

    await created["func"]()
    assert bus.events and isinstance(bus.events[0], DayChanged)

    scheduler.stop()
    assert scheduler._cron_job is None
