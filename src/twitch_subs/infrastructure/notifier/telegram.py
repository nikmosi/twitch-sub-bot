from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from itertools import batched, groupby

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

        # Buffer: keys are (disable_web_page_preview, disable_notification), values are lists of texts
        self._buffer: dict[tuple[bool, bool], list[str]] = defaultdict(list)
        self._flush_task: asyncio.Task[None] | None = None
        self._flush_timeout = 0.2  # 200 milliseconds
        self._lock = asyncio.Lock()

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
        sorted_states = sorted(states, key=lambda state: state.broadcaster)
        for key, group in groupby(sorted_states, key=lambda state: state.broadcaster):
            text.append(f"• <b>{key}</b> ")
            for info in sorted(group, key=lambda item: item.login):
                text.append(
                    f' <a href="https://www.twitch.tv/{info.login}">{info.login}</a>'
                )
        for batch in batched(text, n=100):
            await self.send_message("\n".join(batch), disable_notification=True)

    async def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None:
        async with self._lock:
            self._buffer[(disable_web_page_preview, disable_notification)].append(text)
            if self._flush_task is None:
                self._flush_task = asyncio.create_task(self._flush_buffer_later())

    async def _flush_buffer_later(self) -> None:
        await asyncio.sleep(self._flush_timeout)

        async with self._lock:
            # Take a snapshot of the current buffer and reset it
            buffers_to_send = self._buffer
            self._buffer = defaultdict(list)
            self._flush_task = None

        for (preview, notif), texts in buffers_to_send.items():
            # Send in batches of 100 to avoid exceeding TG limits
            for batch in batched(texts, n=100):
                joined_text = "\n".join(batch)
                try:
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=joined_text,
                        disable_web_page_preview=preview,
                        disable_notification=notif,
                    )
                except Exception as e:
                    logger.opt(exception=e).exception(
                        "Telegram send failed in background worker"
                    )
