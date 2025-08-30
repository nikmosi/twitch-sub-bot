from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

from loguru import logger

from twitch_subs.application.logins import LoginsProvider

from ..domain.models import BroadcasterType, LoginStatus, SubState
from ..domain.ports import NotifierProtocol, SubscriptionStateRepo, TwitchClientProtocol


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

    def check_login(self, login: str) -> LoginStatus:
        logger.info("Checking login {}", login)
        user = self.twitch.get_user_by_login(login)
        btype = BroadcasterType.NONE if user is None else user.broadcaster_type
        logger.info("Login {} status {}", login, btype or "not-found")
        return LoginStatus(login, btype, user)

    def run_once(self, logins: Iterable[str]) -> bool:
        changed = False
        updates: list[SubState] = []
        for status in map(self.check_login, logins):
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
                    self.notifier.notify_about_change(status, curr)
            since = prev.since if prev and prev_sub and curr_sub else (
                datetime.now(timezone.utc) if curr_sub else None
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

    def _report(
        self,
        logins: Sequence[str],
        checks: int,
        errors: int,
    ) -> None:
        state: dict[str, BroadcasterType] = {}
        for login in logins:
            s = self.state_repo.get_sub_state(login)
            if s and s.is_subscribed and s.tier:
                state[login] = BroadcasterType(s.tier)
            else:
                state[login] = BroadcasterType.NONE
        self.notifier.notify_report(logins, state, checks, errors)

    def watch(
        self,
        logins: LoginsProvider,
        interval: int,
        stop_event: threading.Event,
        report_interval: int = 86400,
    ) -> None:
        """Run the watcher until *stop_event* is set."""

        self.notifier.notify_about_start()
        next_report = time.time() + report_interval
        checks = 0
        errors = 0
        while not stop_event.is_set():
            checks += 1
            all_logins = logins.get()
            try:
                self.run_once(all_logins)
            except Exception as e:
                errors += 1
                logger.exception(f"Run once failed: {e}")
            if time.time() >= next_report:
                self._report(all_logins, checks, errors)
                checks = 0
                errors = 0
                next_report += report_interval
            stop_event.wait(interval)
