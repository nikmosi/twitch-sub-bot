from __future__ import annotations

import asyncio
from dataclasses import dataclass
from itertools import batched

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from loguru import logger

from twitch_subs.application.ports import EventBus
from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.domain.events import DomainEvent, UserAdded, UserError, UserRemoved
from twitch_subs.domain.models import TwitchUsername
from twitch_subs.infrastructure.error import NicknameExtractionError

from .filters import ChatIdFilter


def parse_twitch_usernames(text: str) -> list[str]:
    usernames: list[str] = []
    for token in text.split():
        try:
            username = TwitchUsername.parse_from_token(token)
        except ValueError:
            raise NicknameExtractionError(nickname=token)
        usernames.append(username.value)

    return usernames


@dataclass(slots=True, frozen=True, kw_only=True)
class WatchlistCommands:
    service: WatchlistService

    # ----- pure helpers used by handlers and tests -----
    def add(self, usernames: list[str]) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for username in usernames:
            if not self.service.add(username):
                events.append(
                    UserError(login=username, exception="is already in the watchlist ℹ️")
                )
            else:
                events.append(UserAdded(login=username))
        return events

    def remove(self, usernames: list[str]) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for username in usernames:
            if self.service.remove(username):
                events.append(UserRemoved(login=username))
            else:
                events.append(
                    UserError(login=username, exception="not found in the watchlist ⚠️")
                )
        return events

    def _format_watchlist_entries(self) -> list[str]:
        users = self.service.list()
        text: list[str] = []
        for login in users:
            text.append(f'• <a href="https://www.twitch.tv/{login}">{login:<10}</a>')
        return text

    def get_list(self) -> str:
        text = ["📊 <b>List</b>"]
        text.append("")
        users = self._format_watchlist_entries()
        if users:
            return "\n".join(text + users)
        return "📭 Watchlist is empty"

    def handle_command(self, text: str) -> list[DomainEvent] | str:
        parts = text.strip().split(maxsplit=1)
        command = parts[0]
        argument = parts[1].strip() if len(parts) > 1 else None
        if command == "/add" and argument:
            return self.add(parse_twitch_usernames(argument))
        if command == "/remove" and argument:
            return self.remove(parse_twitch_usernames(argument))
        if command == "/list" and not argument:
            return self.get_list()
        return "❓ Unknown command"


class TelegramWatchlistBot:
    """Telegram bot to manage the watchlist using aiogram."""

    def __init__(
        self, bot: Bot, chat_id: str, service: WatchlistService, event_bus: EventBus
    ) -> None:
        self.service = service
        self.bus = event_bus
        self.commands = WatchlistCommands(service=service)
        self.bot = bot
        self.dispatcher = Dispatcher()

        self.dispatcher.message.register(
            self._cmd_add, Command("add"), ChatIdFilter(chat_id)
        )

        self.dispatcher.message.register(
            self._cmd_remove, Command("remove"), ChatIdFilter(chat_id)
        )
        self.dispatcher.message.register(
            self._cmd_list, Command("list"), ChatIdFilter(chat_id)
        )

    # ----- aiogram command handlers -----
    async def _cmd_add(self, message: types.Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("ℹ️ Usage: /add <username>...")
            return
        usernames_text = parts[1].strip()
        try:
            usernames = parse_twitch_usernames(usernames_text)
        except NicknameExtractionError as e:
            logger.opt(exception=e).warning(e.message)
            await self.bus.publish(UserError(login=e.nickname, exception=e.message))
        else:
            events = self.commands.add(usernames)
            await self.bus.publish(*events)

    async def _cmd_remove(self, message: types.Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("ℹ️ Usage: /remove <username>...")
            return
        usernames_text = parts[1].strip()
        try:
            usernames = parse_twitch_usernames(usernames_text)
        except NicknameExtractionError as e:
            logger.opt(exception=e).warning(e.message)
            await self.bus.publish(UserError(login=e.nickname, exception=e.message))
        else:
            events = self.commands.remove(usernames)
            await self.bus.publish(*events)

    async def _cmd_list(self, message: types.Message) -> None:
        message_lines = self.commands.get_list().split("\n")
        for batch in batched(message_lines, n=100):
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
