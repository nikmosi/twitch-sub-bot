from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from itertools import batched, groupby

from aiogram import Bot
from loguru import logger


from twitch_subs.application.ports import NotifierProtocol
from twitch_subs.domain.models import BroadcasterType, SubState

logger = logger.bind(module=__name__)


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
        self,
        login: str,
        current_state: BroadcasterType,
        display_name: str | None = None,
    ) -> None:
        display = display_name or login
        badge = "🟣" if current_state == BroadcasterType.PARTNER else "🟡"
        subflag = "да" if current_state.is_subscribable() else "нет"
        text = (
            f'{badge} <a href="https://www.twitch.tv/{login}">{display}</a> стал <b>{current_state.value}</b>\n'
            f"Подписка доступна: <b>{subflag}</b>\n"
            f"Логин: <code>{login}</code>\n"
        )
        await self.send_message(text)

    async def notify_about_start(self) -> None:
        await self.send_message("🟢 <b>Twitch Subs Watcher</b> запущен. Мониторю.")

    async def notify_about_stop(self) -> None:
        async with self._lock:
            flush_task = self._flush_task
            self._flush_task = None
            self._buffer[(True, False)].append(
                "🔴 <b>Twitch Subs Watcher</b> остановлен."
            )
            buffers_to_send = self._buffer
            self._buffer = defaultdict(list)

        if flush_task is not None:
            flush_task.cancel()
            await asyncio.gather(flush_task, return_exceptions=True)

        await self._send_buffers(buffers_to_send)

    async def notify_report(
        self,
        states: Sequence[SubState],
        checks: int,
        errors: int,
        missing_logins: Sequence[str],
    ) -> None:
        text = ["📊 <b>Twitch Subs Daily Report</b>"]
        text.append(f"Checks: <b>{checks}</b>")
        text.append(f"Errors: <b>{errors}</b>")
        text.append("Statuses:")
        sorted_states = sorted(states, key=lambda state: state.broadcaster_type)
        for key, group in groupby(
            sorted_states, key=lambda state: state.broadcaster_type
        ):
            text.append(f"• <b>{key}</b> ")
            for info in sorted(group, key=lambda item: item.login):
                text.append(
                    f' <a href="https://www.twitch.tv/{info.login}">{info.login}</a>'
                )
        if missing_logins:
            text.append("Missing on Twitch:")
            for login in missing_logins:
                text.append(f"• <code>{login}</code>")
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
        try:
            await asyncio.sleep(self._flush_timeout)
        except asyncio.CancelledError:
            return

        async with self._lock:
            # Take a snapshot of the current buffer and reset it
            buffers_to_send = self._buffer
            self._buffer = defaultdict(list)
            self._flush_task = None

        await self._send_buffers(buffers_to_send)

    async def _send_buffers(
        self, buffers_to_send: dict[tuple[bool, bool], list[str]]
    ) -> None:
        for (preview, notif), texts in buffers_to_send.items():
            # Send in batches of 100 to avoid exceeding TG limits
            for batch in batched(texts, n=100):
                await self._send_batch(
                    "\n".join(batch),
                    disable_web_page_preview=preview,
                    disable_notification=notif,
                )

    async def _send_batch(
        self,
        text: str,
        *,
        disable_web_page_preview: bool,
        disable_notification: bool,
    ) -> None:
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                disable_web_page_preview=disable_web_page_preview,
                disable_notification=disable_notification,
            )
        except Exception as e:
            logger.opt(exception=e).exception(
                "[TelegramNotifier] Failed to send message to chat={} (exception: {})",
                self.chat_id,
                e,
            )
