from __future__ import annotations

import asyncio
from collections.abc import Sequence
from itertools import batched

from aiogram import Bot
from loguru import logger

from twitch_subs.application.ports import NotifierProtocol
from twitch_subs.domain.models import (
    BroadcasterType,
    LoginReportInfo,
    LoginStatus,
)


class TelegramNotifier(NotifierProtocol):
    def __init__(self, bot: Bot, chat_id: str):
        self.bot = bot
        self.chat_id = chat_id
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
            f'{badge} <a href="https://www.twitch.tv/{login}">{display}</a> стал <b>{curr.value}</b>\n'
            f"Подписка доступна: <b>{subflag}</b>\n"
            f"Логин: <code>{login}</code>\n"
        )
        await self.send_message(text)

    async def notify_about_start(self) -> None:
        await self.send_message("🟢 <b>Twitch Subs Watcher</b> запущен. Мониторю.")

    async def notify_about_stop(self) -> None:
        await self.send_message("🔴 <b>Twitch Subs Watcher</b> остановлен.")

    async def notify_report(
        self,
        states: Sequence[LoginReportInfo],
        checks: int,
        errors: int,
    ) -> None:
        text = ["📊 <b>Twitch Subs Daily Report</b>"]
        text.append(f"Checks: <b>{checks}</b>")
        text.append(f"Errors: <b>{errors}</b>")
        text.append("Statuses:")
        for info in sorted(states, key=lambda item: item.login):
            broadcaster = info.broadcaster
            text.append(
                f"• <b>{broadcaster.value:>8}</b> "
                f'<a href="https://www.twitch.tv/{info.login}">{info.login}</a>'
            )
        for batch in batched(text, n=100):
            await self.send_message("\n".join(batch), disable_notification=True)

    async def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None:
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                disable_web_page_preview=disable_web_page_preview,
                disable_notification=disable_notification,
            )
        except Exception as e:
            logger.opt(exception=e).exception("Telegram send failed")
