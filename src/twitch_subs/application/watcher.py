from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

from loguru import logger

from twitch_subs.application.logins import LoginsProvider
from twitch_subs.domain.models import (
    BroadcasterType,
    LoginReportInfo,
    LoginStatus,
    SubState,
)

from .ports import NotifierProtocol, SubscriptionStateRepo, TwitchClientProtocol


class Watcher:
    """Monitor Twitch logins and notify when subscription becomes available."""

    def __init__(
        self,
        twitch: TwitchClientProtocol,
        notifier: NotifierProtocol,
        state_repo: SubscriptionStateRepo,
    ) -> None:
        self.twitch = twitch
        self.notifier = notifier
        self.state_repo = state_repo

    async def check_login(self, login: str) -> LoginStatus:
        logger.trace("Checking login {}", login)
        user = await self.twitch.get_user_by_login(login)
        btype = BroadcasterType.NONE if user is None else user.broadcaster_type
        logger.trace("Login {} status {}", login, btype or "not-found")
        return LoginStatus(login, btype, user)

    async def run_once(self, logins: Iterable[str], stop_event: asyncio.Event) -> bool:
        changed = False
        updates: list[SubState] = []
        for login in logins:
            if stop_event.is_set():
                return False
            status = await self.check_login(login)
            curr = status.broadcaster_type or BroadcasterType.NONE
            prev = self.state_repo.get_sub_state(status.login)
            prev_sub = prev.is_subscribed if prev else False
            curr_sub = curr.is_subscribable()
            if prev_sub != curr_sub:
                changed = True
                logger.info(
                    "Status change for {}: {} -> {}",
                    status.login,
                    (prev.tier if prev and prev.tier else BroadcasterType.NONE.value),
                    curr.value,
                )
                if curr_sub:
                    await self.notifier.notify_about_change(status, curr)
            since = (
                prev.since
                if prev and prev_sub and curr_sub
                else (datetime.now(timezone.utc) if curr_sub else None)
            )
            updates.append(
                SubState(
                    login=status.login,
                    is_subscribed=curr_sub,
                    tier=curr.value if curr_sub else None,
                    since=since,
                )
            )
        self.state_repo.set_many(updates)
        return changed

    async def _report(
        self,
        logins: Sequence[str],
        checks: int,
        errors: int,
    ) -> None:
        state: list[LoginReportInfo] = []
        for login in logins:
            s = self.state_repo.get_sub_state(login)
            if s and s.is_subscribed and s.tier:
                broadcaster_type = BroadcasterType(s.tier)
            else:
                broadcaster_type = BroadcasterType.NONE
            state.append(LoginReportInfo(login, broadcaster_type))
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
