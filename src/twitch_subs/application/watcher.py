from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Iterable

from loguru import logger

from twitch_subs.application.logins import LoginsProvider

from ..domain.models import BroadcasterType, UserRecord
from ..domain.ports import (
    NotifierProtocol,
    StateRepositoryProtocol,
    TwitchClientProtocol,
)


@dataclass(frozen=True)
class LoginStatus:
    """Result of a single login check."""

    login: str
    broadcaster_type: BroadcasterType | None
    user: UserRecord | None


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

    def check_logins(self, logins: Iterable[str]) -> list[LoginStatus]:
        statuses: list[LoginStatus] = []
        for login in logins:
            logger.info("Checking login {}", login)
            user = self.twitch.get_user_by_login(login)
            btype = None if user is None else user.broadcaster_type
            logger.info("Login {} status {}", login, btype or "not-found")
            statuses.append(LoginStatus(login, btype, user))
        return statuses

    def run_once(
        self, logins: Iterable[str], state: dict[str, BroadcasterType]
    ) -> bool:
        rows = self.check_logins(logins)
        changed = False
        for status in rows:
            prev = state.get(status.login, BroadcasterType.NONE)
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
                    user = status.user
                    display = user.display_name if user else status.login
                    badge = "🟣" if curr == BroadcasterType.PARTNER else "🟡"
                    subflag = "да" if curr.is_subscribable() else "нет"
                    text = (
                        f"{badge} <b>{display}</b> стал <b>{curr.value}</b>\n"
                        f"Подписка доступна: <b>{subflag}</b>\n"
                        f"Логин: <code>{status.login}</code>"
                    )
                    self.notifier.send_message(text)
        return changed

    def watch(
        self,
        logins: LoginsProvider,
        interval: int,
        stop_event: threading.Event | None = None,
    ) -> None:
        state = self.state_repo.load()
        self.notifier.send_message(
            "🟢 <b>Twitch Subs Watcher</b> запущен. Мониторю: "
            + ", ".join(f"<code>{login}</code>" for login in logins.get())
        )
        while not (stop_event and stop_event.is_set()):
            changed = self.run_once(logins.get(), state)
            if changed:
                logger.info("State changed, saving")
                self.state_repo.save(state)
            if stop_event:
                stop_event.wait(interval)
            else:
                time.sleep(interval)
