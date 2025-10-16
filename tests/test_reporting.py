from collections.abc import Iterable
from datetime import datetime, timezone

import pytest

from twitch_subs.application.reporting import (
    DailyReportCollector,
    DayChangeScheduler,
    crontab,
)
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


class StubClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class StubIdProvider:
    def __init__(self) -> None:
        self.counter = 0

    def new_id(self) -> str:
        self.counter += 1
        return f"id-{self.counter}"


@pytest.mark.asyncio
async def test_collector_sends_report_and_resets() -> None:
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    repo = StubRepo(
        [
            SubState(
                "foo",
                True,
                tier=BroadcasterType.AFFILIATE.value,
                since=None,
                updated_at=now,
            ),
            SubState("bar", False, tier=None, since=None, updated_at=now),
        ]
    )
    notifier = StubNotifier()
    collector = DailyReportCollector(notifier, repo)

    await collector.handle_loop_checked(
        LoopChecked(id="id-1", occurred_at=now, logins=("foo",))
    )
    await collector.handle_loop_failed(
        LoopCheckFailed(
            id="id-2", occurred_at=now, logins=("bar",), error="boom"
        )
    )
    await collector.handle_day_changed(DayChanged(id="id-3", occurred_at=now))

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

    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    scheduler = DayChangeScheduler(
        event_bus=bus,
        clock=StubClock(now),
        id_provider=StubIdProvider(),
        cron="*/5 * * * *",
    )
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
    assert bus.events[0].occurred_at == now

    scheduler.stop()
    assert scheduler._cron_job is None


def test_scheduler_idempotent_start_and_stop() -> None:
    bus = StubEventBus()

    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    scheduler = DayChangeScheduler(
        event_bus=bus,
        clock=StubClock(now),
        id_provider=StubIdProvider(),
    )
    scheduler._crontab_factory = lambda *args, **kwargs: StubCron(kwargs.get("func"))

    scheduler.start()
    first = scheduler._cron_job
    scheduler.start()
    assert scheduler._cron_job is first

    scheduler.stop()
    scheduler.stop()
    assert scheduler._cron_job is None


def test_crontab_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_crontab(spec, func, args, kwargs, start, loop, tz):
        captured.update(
            {
                "spec": spec,
                "func": func,
                "args": args,
                "kwargs": kwargs,
                "start": start,
                "loop": loop,
                "tz": tz,
            }
        )
        return "job"

    monkeypatch.setattr("twitch_subs.application.reporting.aiocron.crontab", fake_crontab)

    job = crontab("*/10 * * * *", func=None, start=False, args=(1,), kwargs={"x": 2})

    assert job == "job"
    assert captured["spec"] == "*/10 * * * *"
    assert captured["start"] is False
