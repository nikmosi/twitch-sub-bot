from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone
from itertools import batched

import httpx
from loguru import logger

from twitch_subs.application.error import WatcherRunError
from twitch_subs.application.logins import LoginsProvider
from twitch_subs.domain.events import (
    LoopChecked,
    LoopCheckFailed,
    OnceChecked,
    UserBecomeSubscribtable,
)
from twitch_subs.domain.models import LoginStatus, SubState

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

    async def check_logins(self, logins: str | Sequence[str]) -> Sequence[LoginStatus]:
        if isinstance(logins, str):
            logins = [logins]
        statuses: list[LoginStatus] = []
        for login_batch in batched(logins, n=100):
            users = await self.twitch.get_user_by_login(login_batch)
            if not users:
                continue
            for user in users:
                statuses.append(
                    LoginStatus(
                        login=user.login,
                        broadcaster_type=user.broadcaster_type,
                        user=user,
                    )
                )
        return statuses

    async def run_once(self, logins: Sequence[str]) -> bool:
        changed = False
        updates: list[SubState] = []

        try:
            statuses = await self.check_logins(logins)
        except httpx.TimeoutException as e:
            await self.event_bus.publish(LoopCheckFailed(logins=logins, error=str(e)))
        else:
            for status in statuses:
                curr = status.broadcaster_type
                prev = self.state_repo.get_sub_state(status.login)
                prev_sub = prev.is_subscribed if prev else False
                curr_sub = curr.is_subscribable()
                if prev_sub != curr_sub:
                    changed = True
                    if curr_sub:
                        await self.event_bus.publish(
                            UserBecomeSubscribtable(
                                login=status.login,
                                current_state=curr,
                            )
                        )
                since = (
                    prev.since
                    if prev and prev_sub and curr_sub
                    else (datetime.now(timezone.utc) if curr_sub else None)
                )
                updates.append(SubState(login=status.login, status=curr, since=since))
                await self.event_bus.publish(
                    OnceChecked(login=status.login, current_state=curr)
                )

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
                    raise WatcherRunError(logins=tuple(all_logins), error=e)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except TimeoutError:
                    pass
        finally:
            logger.info("notify_about_stop")
            await asyncio.shield(self.notifier.notify_about_stop())
