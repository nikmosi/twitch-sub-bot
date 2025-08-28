from __future__ import annotations

import asyncio
from typing import Sequence

import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from loguru import logger

from twitch_subs.domain.models import BroadcasterType, LoginStatus

from ..domain.ports import NotifierProtocol, WatchlistRepository
from . import build_watchlist_repo

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramNotifier(NotifierProtocol):
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def notify_about_change(self, status: LoginStatus, curr: BroadcasterType) -> None:
        user = status.user
        display = user.display_name if user else status.login
        badge = "🟣" if curr == BroadcasterType.PARTNER else "🟡"
        subflag = "да" if curr.is_subscribable() else "нет"
        text = (
            f"{badge} <b>{display}</b> стал <b>{curr.value}</b>\n"
            f"Подписка доступна: <b>{subflag}</b>\n"
            f"Логин: <code>{status.login}</code>"
        )
        self.send_message(text)

    def notify_about_start(self) -> None:
        self.send_message("🟢 <b>Twitch Subs Watcher</b> запущен. Мониторю.")

    def notify_report(
        self,
        logins: Sequence[str],
        state: dict[str, BroadcasterType],
        checks: int,
        errors: int,
    ) -> None:
        text = ["📊 <b>Twitch Subs Daily Report</b>"]
        text.append(f"Checks: <b>{checks}</b>")
        text.append(f"Errors: <b>{errors}</b>")
        text.append("Statuses:")
        for login in logins:
            broadcastertype = state.get(login, BroadcasterType.NONE)
            assert broadcastertype is not None
            btype = broadcastertype.value
            text.append(
                f'• <a href="https://www.twitch.tv/{login}">{login:<10}</a>: <b>{btype:>10}</b>'
            )
        self.send_message("\n".join(text), disable_notification=True)

    def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None:
        url = f"{TELEGRAM_API_BASE}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
            "disable_notification": disable_notification,
            "parse_mode": "HTML",
        }
        try:
            logger.info("Sending Telegram message")
            with httpx.Client(timeout=15.0) as c:
                r = c.post(url, json=payload)
                r.raise_for_status()
        except Exception:
            logger.exception("Telegram send failed")


class TelegramWatchlistBot:
    """Telegram bot to manage the watchlist using aiogram."""

    def __init__(self, token: str, repo: WatchlistRepository | None = None) -> None:
        self.repo = repo or build_watchlist_repo()
        self.bot = Bot(token=token)
        self.dispatcher = Dispatcher()

        self.dispatcher.message.register(self._cmd_add, Command("add"))
        self.dispatcher.message.register(self._cmd_remove, Command("remove"))
        self.dispatcher.message.register(self._cmd_list, Command("list"))

    # ----- pure helpers used by handlers and tests -----
    def _handle_add(self, username: str) -> str:
        if self.repo.exists(username):
            return f"{username} already present"
        self.repo.add(username)
        return f"Added {username}"

    def _handle_remove(self, username: str) -> str:
        if self.repo.remove(username):
            return f"Removed {username}"
        return f"{username} not found"

    def _handle_list(self) -> str:
        users = self.repo.list()
        if users:
            return "\n".join(users)
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
        await message.answer(self._handle_list())

    async def run(self) -> None:
        try:
            await self.dispatcher.start_polling(self.bot, handle_signals=False)  # pyright: ignore
        finally:
            await self.bot.session.close()

    async def stop(self) -> None:
        await self.dispatcher.stop_polling()

    def run_polling(self) -> None:
        asyncio.run(self.run())
