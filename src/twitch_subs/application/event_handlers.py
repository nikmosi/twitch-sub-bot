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
    UserBecameSubscribable,
    UserError,
    UserRemoved,
)

logger = logger.bind(module=__name__)


def register_notification_handlers(
    event_bus: EventBus,
    notifier: NotifierProtocol,
    sub_state_repo: SubscriptionStateRepo,
) -> DailyReportCollector:
    """Register default notification and logging handlers on *event_bus*."""

    async def log_user_error(event: UserError) -> None:
        logger.error(
            "[EventHandler] User error event: login={}, exception={}",
            event.login,
            event.exception,
        )

    async def notify_about_error(event: UserError) -> None:
        await notifier.send_message(
            f"⚠️ Error with <code>{event.login}</code>: {event.exception}"
        )

    async def notify_about_add(event: UserAdded) -> None:
        await notifier.send_message(
            f"➕ <code>{event.login}</code> добавлен в список наблюдения"
        )

    async def notify_about_remove(event: UserRemoved) -> None:
        await notifier.send_message(
            f"➖ <code>{event.login}</code> удалён из списка наблюдения"
        )

    async def notify_about_subscribable_change(
        event: UserBecameSubscribable,
    ) -> None:
        await notifier.notify_about_change(event.login, event.current_state)

    async def log_once_check(event: OnceChecked) -> None:
        logger.debug(
            "[EventHandler] Login checked: login={}, status={}",
            event.login,
            event.current_state.value,
        )

    async def log_loop_check_debug(event: LoopChecked) -> None:
        logger.debug(
            "[EventHandler] Loop checked: found_logins={}, missing_logins={}",
            event.found_logins,
            event.missing_logins,
        )

    async def log_loop_check_info(_: LoopChecked) -> None:
        logger.info("[EventHandler] Loop check completed.")

    async def log_subscribable_change(event: UserBecameSubscribable) -> None:
        logger.info(
            "[EventHandler] User {} has changed state to {}",
            event.login,
            event.current_state.value,
        )

    event_bus.subscribe(UserAdded, notify_about_add)
    event_bus.subscribe(UserRemoved, notify_about_remove)
    event_bus.subscribe(UserBecameSubscribable, notify_about_subscribable_change)
    event_bus.subscribe(UserError, notify_about_error)
    event_bus.subscribe(UserBecameSubscribable, log_subscribable_change)
    event_bus.subscribe(OnceChecked, log_once_check)
    event_bus.subscribe(UserError, log_user_error)
    event_bus.subscribe(LoopChecked, log_loop_check_debug)
    event_bus.subscribe(LoopChecked, log_loop_check_info)

    collector = DailyReportCollector(notifier, sub_state_repo)
    event_bus.subscribe(LoopChecked, collector.handle_loop_checked)
    event_bus.subscribe(LoopCheckFailed, collector.handle_loop_failed)
    event_bus.subscribe(DayChanged, collector.handle_day_changed)

    return collector
