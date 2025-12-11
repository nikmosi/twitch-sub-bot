from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from itertools import batched

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from loguru import logger

from twitch_subs.application.ports import EventBus
from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.domain.events import DomainEvent, UserAdded, UserError, UserRemoved
from twitch_subs.infrastructure.error import CantExtractNicknama

from .filters import IDFilter


def to_usernames(text: str) -> list[str]:
    res: list[str] = []
    pattern = r"^(?:https?://(?:www|m)?\.?twitch\.tv/)?(\w+)"
    for i in text.split(" "):
        match_ = re.search(pattern, i)
        if not match_:
            raise CantExtractNicknama(nickname=i)
        nickname = match_.group(1)
        res.append(nickname)

    return res


@dataclass(slots=True, frozen=True, kw_only=True)
class Commands:
    service: WatchlistService

    # ----- pure helpers used by handlers and tests -----
    def add(self, usernames: list[str]) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for username in usernames:
            if not self.service.add(username):
                events.append(
                    UserError(login=username, exception="{username} already present")
                )
            else:
                events.append(UserAdded(login=username))
        return events

    def remove(self, usernames: list[str]) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for username in usernames:
            if self.service.remove(username):
                events.append(UserRemoved(login=f"Removed {username}"))
            else:
                events.append(
                    UserError(login=username, exception=f"{username} not found")
                )
        return events

    def _create_users_list(self) -> list[str]:
        users = self.service.list()
        text: list[str] = []
        for login in users:
            text.append(f'• <a href="https://www.twitch.tv/{login}">{login:<10}</a>')
        return text

    def get_list(self) -> str:
        text = ["📊 <b>List</b>"]
        text.append("")
        users = self._create_users_list()
        if users:
            return "\n".join(text + users)
        return "Watchlist is empty"

    def handle_command(self, text: str) -> list[DomainEvent] | str:
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1].strip() if len(parts) > 1 else None
        if cmd == "/add" and arg:
            return self.add(to_usernames(arg))
        if cmd == "/remove" and arg:
            return self.remove(to_usernames(arg))
        if cmd == "/list" and not arg:
            return self.get_list()
        return "Unknown command"

    pass


class TelegramWatchlistBot:
    """Telegram bot to manage the watchlist using aiogram."""

    def __init__(
        self, bot: Bot, chat_id: str, service: WatchlistService, event_bus: EventBus
    ) -> None:
        self.service = service
        self.bus = event_bus
        self.commands = Commands(service=service)
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

    # ----- aiogram command handlers -----
    async def _cmd_add(self, message: types.Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /add <username>...")
            return
        arg = parts[1].strip()
        try:
            usernames = to_usernames(arg)
        except CantExtractNicknama as e:
            logger.opt(exception=e).warning(e.message)
            await self.bus.publish(UserError(login=e.nickname, exception=e.message))
        else:
            events = self.commands.add(usernames)
            await self.bus.publish(*events)

    async def _cmd_remove(self, message: types.Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /remove <username>...")
            return
        arg = parts[1].strip()
        try:
            usernames = to_usernames(arg)
        except CantExtractNicknama as e:
            logger.opt(exception=e).warning(e.message)
            await self.bus.publish(UserError(login=e.nickname, exception=e.message))
        else:
            events = self.commands.remove(usernames)
            await self.bus.publish(*events)

    async def _cmd_list(self, message: types.Message) -> None:
        ans = self.commands.get_list().split("\n")
        for batch in batched(ans, n=100):
            await message.answer(
                "\n".join(batch),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    def handle_command(self, text: str) -> list[DomainEvent] | str:
        return self.commands.handle_command(text)

    async def run(self) -> None:
        try:
            await self.dispatcher.start_polling(self.bot, handle_signals=False)  # pyright: ignore
        finally:
            await self.bot.session.close()

    async def stop(self) -> None:
        await self.dispatcher.stop_polling()

    def run_polling(self) -> None:
        asyncio.run(self.run())
