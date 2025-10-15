from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from datetime import datetime, timezone

from loguru import logger

from twitch_subs.application.logins import LoginsProvider
from twitch_subs.domain.events import LoopChecked, OnceChecked, UserBecomeSubscribtable
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
            if curr_sub:
                updates.append(
                    SubState(
                        login=status.login,
                        broadcaster_type=curr,
                        since=since,
                    )
                )
            else:
                updates.append(SubState.unsubscribed(status.login))
            await self.event_bus.publish(OnceChecked(login=login, current_state=curr))
        self.state_repo.set_many(updates)
        await self.event_bus.publish(LoopChecked(logins=logins))
        return changed

    async def _report(
        self,
        logins: Sequence[str],
        checks: int,
        errors: int,
    ) -> None:
        state: list[SubState] = []
        for login in logins:
            s = self.state_repo.get_sub_state(login)
            if s is not None:
                state.append(s)
            else:
                state.append(SubState.unsubscribed(login))
        await self.notifier.notify_report(state, checks, errors)

    async def watch(
        self,
        logins: LoginsProvider,
        interval: int,
        stop_event: asyncio.Event,
        report_interval: int = 86400,
    ) -> None:
        """Run the watcher until *stop_event* is set."""

        await self.notifier.notify_about_start()
        next_report = time.time() + report_interval
        checks = 0
        errors = 0
        try:
            while not stop_event.is_set():
                checks += 1
                all_logins = logins.get()
                try:
                    await self.run_once(all_logins, stop_event)
                except Exception as e:
                    errors += 1
                    logger.opt(exception=e).exception("Run once failed")
                if time.time() >= next_report:
                    await self._report(all_logins, checks, errors)
                    checks = 0
                    errors = 0
                    next_report += report_interval
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except TimeoutError:
                    pass
        finally:
            logger.info("notify_about_stop")
            await asyncio.shield(self.notifier.notify_about_stop())
