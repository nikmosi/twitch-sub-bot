from __future__ import annotations

import time
from typing import Iterable, List, Tuple
from loguru import logger

from ..domain.models import BroadcasterType, UserRecord
from ..infrastructure.state import StateRepository
from ..infrastructure.telegram import TelegramNotifier
from ..infrastructure.twitch import TwitchClient


class Watcher:
    def __init__(
        self,
        twitch: TwitchClient,
        notifier: TelegramNotifier,
        state_repo: StateRepository,
    ):
        self.twitch = twitch
        self.notifier = notifier
        self.state_repo = state_repo

    def check_logins(
        self, logins: Iterable[str]
    ) -> List[Tuple[str, BroadcasterType | None, UserRecord | None]]:
        out: List[Tuple[str, BroadcasterType | None, UserRecord | None]] = []
        for login in logins:
            logger.info("Checking login {}", login)
            user = self.twitch.get_user_by_login(login)
            btype = None if user is None else user.broadcaster_type
            logger.info("Login {} status {}", login, btype or "not-found")
            out.append((login, btype, user))
        return out

    def watch(self, logins: list[str], interval: int) -> None:
        state = self.state_repo.load()
        self.notifier.send_message(
            "🟢 <b>Twitch Subs Watcher</b> запущен. Мониторю: "
            + ", ".join(f"<code>{login}</code>" for login in logins)
        )
        while True:
            rows = self.check_logins(logins)
            changed = False
            for login, btype, user in rows:
                prev = state.get(login, BroadcasterType.NONE)
                curr = btype or BroadcasterType.NONE
                if prev != curr:
                    state[login] = curr
                    changed = True
                    logger.info("Status change for {}: {} -> {}", login, prev.value, curr.value)
                    if curr.is_subscribable():
                        display = user.display_name if user else login
                        badge = "🟣" if curr == BroadcasterType.PARTNER else "🟡"
                        subflag = "да" if curr.is_subscribable() else "нет"
                        text = (
                            f"{badge} <b>{display}</b> стал <b>{curr.value}</b>\n"
                            f"Подписка доступна: <b>{subflag}</b>\n"
                            f"Логин: <code>{login}</code>"
                        )
                        self.notifier.send_message(text)
            if changed:
                logger.info("State changed, saving")
                self.state_repo.save(state)
            time.sleep(interval)
