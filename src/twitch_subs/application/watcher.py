from __future__ import annotations

import asyncio
from collections.abc import Sequence

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
from twitch_subs.domain.models import BroadcasterType, SubState, UserRecord

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

    async def check_logins(self, logins: str | Sequence[str]) -> Sequence[UserRecord]:
        if isinstance(logins, str):
            logins = [logins]
        users = await self.twitch.get_user_by_login(logins)

        if not users:
            logger.warning("got empty users list")
            return []

        return users

    def _get_sub_state_or_default(self, ur: UserRecord) -> SubState:
        prev = self.state_repo.get_sub_state(ur.login)
        if not prev:
            prev = SubState(login=ur.login, broadcaster_type=ur.broadcaster_type)
        return prev

    def _is_user_become_subscribtable(
        self, prev: SubState, curr: BroadcasterType
    ) -> bool:
        prev_sub = prev.is_subscribed
        curr_sub = curr.is_subscribable()

        return curr_sub and prev_sub != curr_sub

    async def run_once(self, logins: Sequence[str]) -> None:
        updates: list[SubState] = []

        try:
            users = await self.check_logins(logins)
        except httpx.TimeoutException as e:
            await self.event_bus.publish(LoopCheckFailed(logins=logins, error=str(e)))
        else:
            for user in users:
                curr = user.broadcaster_type
                prev = self._get_sub_state_or_default(user)

                if self._is_user_become_subscribtable(prev, curr):
                    await self.event_bus.publish(
                        UserBecomeSubscribtable(
                            login=user.login,
                            current_state=curr,
                        )
                    )

                sub_state = SubState(
                    login=user.login,
                    broadcaster_type=curr,
                    since=prev.since,
                )
                updates.append(sub_state)

                await self.event_bus.publish(
                    OnceChecked(login=user.login, current_state=curr)
                )

        self.state_repo.set_many(updates)
        await self.event_bus.publish(LoopChecked(logins=logins))

    async def watch(
        self,
        logins_provider: LoginsProvider,
        interval: int,
        stop_event: asyncio.Event,
    ) -> None:
        """Run the watcher until *stop_event* is set."""

        await self.notifier.notify_about_start()
        try:
            while not stop_event.is_set():
                all_logins = logins_provider.get()
                try:
                    await self.run_once(all_logins)
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
