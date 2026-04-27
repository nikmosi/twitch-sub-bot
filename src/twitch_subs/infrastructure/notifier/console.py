from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from itertools import batched

from loguru import logger

from twitch_subs.application.ports import NotifierProtocol
from twitch_subs.domain.models import BroadcasterType, SubState
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
        self,
        login: str,
        current_state: BroadcasterType,
        display_name: str | None = None,
    ) -> None:
        display = display_name or login
        badge = "🟣" if current_state == BroadcasterType.PARTNER else "🟡"
        subflag = "да" if current_state.is_subscribable() else "нет"
        text = (
            f"{badge} {display} (https://www.twitch.tv/{login}) стал {current_state.value}\n"
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
        states: Sequence[SubState],
        checks: int,
        errors: int,
        missing_logins: Sequence[str],
    ) -> None:
        lines: list[str] = []
        lines.append("📊 Twitch Subs Daily Report")
        lines.append(f"Checks: {checks}")
        lines.append(f"Errors: {errors}")
        lines.append("Statuses:")
        for info in sorted(states, key=lambda item: item.login):
            broadcaster = info.broadcaster_type
            lines.append(
                f"• {broadcaster.value:>8} {info.login} (https://www.twitch.tv/{info.login})"
            )
        if missing_logins:
            lines.append("Missing on Twitch:")
            for login in missing_logins:
                lines.append(f"• {login}")
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
            logger.opt(exception=e).exception(
                "[ConsoleNotifier] Failed to print notification message (exception: {})",
                e,
            )
            raise NotificationDeliveryError(
                message="Console notification failed", context={"error": repr(e)}
            ) from e
