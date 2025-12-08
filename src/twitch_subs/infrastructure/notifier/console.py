from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from itertools import batched

from loguru import logger

from twitch_subs.application.ports import NotifierProtocol
from twitch_subs.domain.models import (
    BroadcasterType,
    LoginReportInfo,
    LoginStatus,
)
from twitch_subs.infrastructure.error import NotificationDeliveryError

_TAG_RE = re.compile(r"</?b>|</?code>|</?i>|</?u>")
_LINK_RE = re.compile(r'<a\s+href="([^"]+)">([^<]+)</a>')


def _html_to_plain(text: str) -> str:
    # <a href="url">txt</a> -> txt (url)
    text = _LINK_RE.sub(r"\2 (\1)", text)
    # strip simple tags
    text = _TAG_RE.sub("", text)
    return text


class ConsoleNotifier(NotifierProtocol):
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None

    async def notify_about_change(
        self, status: LoginStatus, curr: BroadcasterType
    ) -> None:
        user = status.user
        display = user.display_name if user else status.login
        badge = "🟣" if curr == BroadcasterType.PARTNER else "🟡"
        subflag = "да" if curr.is_subscribable() else "нет"
        login = status.login
        text = (
            f"{badge} {display} (https://www.twitch.tv/{login}) стал {curr.value}\n"
            f"Подписка доступна: {subflag}\n"
            f"Логин: {login}\n"
        )
        await self.send_message(text)

    async def notify_about_start(self) -> None:
        await self.send_message("🟢 Twitch Subs Watcher запущен. Мониторю.")

    async def notify_about_stop(self) -> None:
        await self.send_message("🔴 Twitch Subs Watcher остановлен.")

    async def notify_report(
        self,
        states: Sequence[LoginReportInfo],
        checks: int,
        errors: int,
    ) -> None:
        lines: list[str] = []
        lines.append("📊 Twitch Subs Daily Report")
        lines.append(f"Checks: {checks}")
        lines.append(f"Errors: {errors}")
        lines.append("Statuses:")
        for info in sorted(states, key=lambda item: item.login):
            broadcaster = info.broadcaster
            lines.append(
                f"• {broadcaster.value:>8} {info.login} (https://www.twitch.tv/{info.login})"
            )
        for chunk in batched(lines, n=100):
            await self.send_message("\n".join(chunk))

    async def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,  # unused, kept for API parity
        disable_notification: bool = False,  # unused, kept for API parity
    ) -> None:
        try:
            plain = _html_to_plain(text)
            # Use info for human-visible notifications
            logger.info("\n" + plain if "\n" in plain else plain)
        except Exception as e:
            logger.opt(exception=e).exception("Console notify failed")
            raise NotificationDeliveryError(
                message="Console notification failed", context={"error": repr(e)}
            ) from e
