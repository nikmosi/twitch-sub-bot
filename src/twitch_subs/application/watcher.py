from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone

from loguru import logger

from twitch_subs.application.error import WatcherRunError
from twitch_subs.application.logins import LoginsProvider
from twitch_subs.domain.events import (
    LoopChecked,
    LoopCheckFailed,
    OnceChecked,
    UserBecomeSubscribtable,
)
from twitch_subs.domain.models import BroadcasterType, LoginStatus, SubState

from .ports import (
    EventBus,
    NotifierProtocol,
    SubscriptionStateRepo,
    TwitchClientProtocol,
)


class Watcher:
    """Monitor Twitch logins and notify when subscription becomes available."""

    def __init__(
        self,
        twitch: TwitchClientProtocol,
        notifier: NotifierProtocol,
        state_repo: SubscriptionStateRepo,
        event_bus: EventBus,
    ) -> None:
        self.twitch = twitch
        self.notifier = notifier
        self.state_repo = state_repo
        self.event_bus = event_bus

    async def check_login(self, login: str) -> LoginStatus:
        user = await self.twitch.get_user_by_login(login)
        btype = BroadcasterType.NONE if user is None else user.broadcaster_type
        return LoginStatus(login, btype, user)

    async def run_once(self, logins: Sequence[str], stop_event: asyncio.Event) -> bool:
        changed = False
        updates: list[SubState] = []
        for login in logins:
            if stop_event.is_set():
                return False
            status = await self.check_login(login)
            curr = status.broadcaster_type
            prev = self.state_repo.get_sub_state(status.login)
            prev_sub = prev.is_subscribed if prev else False
            curr_sub = curr.is_subscribable()
            if prev_sub != curr_sub:
                changed = True
                if curr_sub:
                    await self.event_bus.publish(
                        UserBecomeSubscribtable(
                            login=login,
                            current_state=curr,
                        )
                    )
            since = (
                prev.since
                if prev and prev_sub and curr_sub
                else (datetime.now(timezone.utc) if curr_sub else None)
            )
            updates.append(SubState(login=status.login, status=curr, since=since))
            await self.event_bus.publish(OnceChecked(login=login, current_state=curr))
        self.state_repo.set_many(updates)
        await self.event_bus.publish(LoopChecked(logins=logins))
        return changed

    async def watch(
        self,
        logins: LoginsProvider,
        interval: int,
        stop_event: asyncio.Event,
    ) -> None:
        """Run the watcher until *stop_event* is set."""

        await self.notifier.notify_about_start()
        try:
            while not stop_event.is_set():
                all_logins = logins.get()
                try:
                    await self.run_once(all_logins, stop_event)
                except Exception as e:
                    logger.opt(exception=e).exception("Run once failed", e)
                    await self.event_bus.publish(
                        LoopCheckFailed(logins=tuple(all_logins), error=str(e))
                    )
                    raise WatcherRunError(logins=tuple(all_logins), error=e) from e
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except TimeoutError:
                    pass
        finally:
            logger.info("notify_about_stop")
            await asyncio.shield(self.notifier.notify_about_stop())
