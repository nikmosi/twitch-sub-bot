from __future__ import annotations

import threading
import time
from typing import Iterable, Sequence

from loguru import logger

from twitch_subs.application.logins import LoginsProvider

from ..domain.models import BroadcasterType, LoginStatus, State
from ..domain.ports import (
    NotifierProtocol,
    StateRepositoryProtocol,
    TwitchClientProtocol,
)


class Watcher:
    """Monitor Twitch logins and notify when subscription becomes available."""

    def __init__(
        self,
        twitch: TwitchClientProtocol,
        notifier: NotifierProtocol,
        state_repo: StateRepositoryProtocol,
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

    def run_once(self, logins: Iterable[str], state: State) -> bool:
        changed = False
        for status in map(self.check_login, logins):
            prev = state.get(status.login, BroadcasterType.NONE)
            assert prev is not None
            curr = status.broadcaster_type or BroadcasterType.NONE
            if prev != curr:
                state[status.login] = curr
                changed = True
                logger.info(
                    "Status change for {}: {} -> {}",
                    status.login,
                    prev.value,
                    curr.value,
                )
                if curr.is_subscribable():
                    self.notifier.notify_about_change(status, curr)
        return changed

    def _report(
        self,
        logins: Sequence[str],
        state: State,
        checks: int,
        errors: int,
    ) -> None:
        self.notifier.notify_report(logins, state.logins, checks, errors)

    def watch(
        self,
        logins: LoginsProvider,
        interval: int,
        stop_event: threading.Event,
        report_interval: int = 86400,
    ) -> None:
        """Run the watcher until *stop_event* is set."""

        state = self.state_repo.load()
        self.notifier.notify_about_start()
        next_report = time.time() + report_interval
        checks = 0
        errors = 0
        while not stop_event.is_set():
            checks += 1
            all_logins = logins.get()
            try:
                changed = self.run_once(all_logins, state)
                if changed:
                    logger.info("State changed, saving")
                    self.state_repo.save(state)
            except Exception as e:
                errors += 1
                logger.exception(f"Run once failed: {e}")
            if time.time() >= next_report:
                self._report(all_logins, state, checks, errors)
                checks = 0
                errors = 0
                next_report += report_interval
            stop_event.wait(interval)
