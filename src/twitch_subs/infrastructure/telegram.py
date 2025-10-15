from __future__ import annotations

import asyncio
from collections.abc import Sequence
from itertools import batched

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, Filter
from aiogram.types import Message
from loguru import logger

from twitch_subs.application.ports import NotifierProtocol
from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.domain.models import BroadcasterType, LoginStatus, SubState


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
        states: Sequence[SubState],
        checks: int,
        errors: int,
    ) -> None:
        text = ["📊 <b>Twitch Subs Daily Report</b>"]
        text.append(f"Checks: <b>{checks}</b>")
        text.append(f"Errors: <b>{errors}</b>")
        text.append("Statuses:")
        for state in sorted(states, key=lambda a: a.broadcaster_type.value):
            text.append(
                f'• <b>{state.broadcaster_type.value:>8}</b> '
                f'<a href="https://www.twitch.tv/{state.login}">{state.login}</a>'
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


class IDFilter(Filter):
    def __init__(self, id: str):
        self._id = int(id)

    async def __call__(self, obj: Message) -> bool:
        res = obj.chat.id == self._id
        if not res:
            logger.info("Got message from unregister user.")
        return res


class TelegramWatchlistBot:
    """Telegram bot to manage the watchlist using aiogram."""

    def __init__(self, bot: Bot, chat_id: str, service: WatchlistService) -> None:
        self.service = service
        self.bot = bot
        self.dispatcher = Dispatcher()

        self.dispatcher.message.register(
            self._cmd_add, Command("add"), IDFilter(chat_id)
        )

        self.dispatcher.message.register(
            self._cmd_remove, Command("remove"), IDFilter(chat_id)
        )
        self.dispatcher.message.register(
            self._cmd_list, Command("list"), IDFilter(chat_id)
        )

    # ----- pure helpers used by handlers and tests -----
    def _handle_add(self, username: str) -> str:
        if not self.service.add(username):
            return f"{username} already present"
        return f"Added {username}"

    def _handle_remove(self, username: str) -> str:
        if self.service.remove(username):
            return f"Removed {username}"
        return f"{username} not found"

    def _create_users_list(self) -> list[str]:
        users = self.service.list()
        text: list[str] = []
        for login in users:
            text.append(f'• <a href="https://www.twitch.tv/{login}">{login:<10}</a>')
        return text

    def _handle_list(self) -> str:
        text = ["📊 <b>List</b>"]
        text.append("")
        users = self._create_users_list()
        if users:
            return "\n".join(text + users)
        return "Watchlist is empty"

    def handle_command(self, text: str) -> str:
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1].strip() if len(parts) > 1 else None
        if cmd == "/add" and arg:
            return self._handle_add(arg)
        if cmd == "/remove" and arg:
            return self._handle_remove(arg)
        if cmd == "/list" and not arg:
            return self._handle_list()
        return "Unknown command"

    # ----- aiogram command handlers -----
    async def _cmd_add(self, message: types.Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /add <username>")
            return
        await message.answer(self._handle_add(parts[1].strip()))

    async def _cmd_remove(self, message: types.Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /remove <username>")
            return
        await message.answer(self._handle_remove(parts[1].strip()))

    async def _cmd_list(self, message: types.Message) -> None:
        ans = self._handle_list().split("\n")
        for batch in batched(ans, n=100):
            await message.answer(
                "\n".join(batch),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    async def run(self) -> None:
        try:
            await self.dispatcher.start_polling(self.bot, handle_signals=False)  # pyright: ignore
        finally:
            await self.bot.session.close()

    async def stop(self) -> None:
        await self.dispatcher.stop_polling()

    def run_polling(self) -> None:
        asyncio.run(self.run())
