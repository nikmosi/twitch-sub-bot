"""Application-level event handler registration."""

from __future__ import annotations

from loguru import logger

from twitch_subs.application.ports import (
    EventBus,
    NotifierProtocol,
    SubscriptionStateRepo,
)
from twitch_subs.application.reporting import DailyReportCollector
from twitch_subs.domain.events import (
    DayChanged,
    LoopChecked,
    LoopCheckFailed,
    OnceChecked,
    UserAdded,
    UserBecomeSubscribtable,
    UserRemoved,
)
from twitch_subs.domain.models import LoginStatus


def register_notification_handlers(
    event_bus: EventBus,
    notifier: NotifierProtocol,
    sub_state_repo: SubscriptionStateRepo,
) -> DailyReportCollector:
    """Register default notification and logging handlers on *event_bus*."""

    async def notify_about_add(event: UserAdded) -> None:
        await notifier.send_message(
            f"➕ <code>{event.login}</code> добавлен в список наблюдения"
        )

    async def notify_about_remove(event: UserRemoved) -> None:
        await notifier.send_message(
            f"➖ <code>{event.login}</code> удалён из списка наблюдения"
        )

    async def notify_about_subs_change(event: UserBecomeSubscribtable) -> None:
        await notifier.notify_about_change(
            LoginStatus(event.login, event.current_state, None),
            event.current_state,
        )

    async def log_once_check(event: OnceChecked) -> None:
        logger.debug(f"checked {event.login} with status {event.current_state.value}")

    async def log_loop_check(event: LoopChecked) -> None:
        logger.debug(f"checked {event.logins=}")

    async def log_subs_change(event: UserBecomeSubscribtable) -> None:
        logger.info(f"{event.login} become {event.current_state.value}")

    event_bus.subscribe(UserAdded, notify_about_add)
    event_bus.subscribe(UserRemoved, notify_about_remove)
    event_bus.subscribe(UserBecomeSubscribtable, notify_about_subs_change)
    event_bus.subscribe(UserBecomeSubscribtable, log_subs_change)
    event_bus.subscribe(OnceChecked, log_once_check)
    event_bus.subscribe(LoopChecked, log_loop_check)

    collector = DailyReportCollector(notifier, sub_state_repo)
    event_bus.subscribe(LoopChecked, collector.handle_loop_checked)
    event_bus.subscribe(LoopCheckFailed, collector.handle_loop_failed)
    event_bus.subscribe(DayChanged, collector.handle_day_changed)

    return collector
