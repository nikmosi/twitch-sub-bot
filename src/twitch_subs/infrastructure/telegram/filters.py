from __future__ import annotations


from aiogram.filters import Filter
from aiogram.types import Message
from loguru import logger

logger = logger.bind(module=__name__)


class ChatIdFilter(Filter):
    def __init__(self, chat_id: str):
        self._chat_id = int(chat_id)

    async def __call__(self, message: Message) -> bool:
        is_allowed_chat = message.chat.id == self._chat_id
        if not is_allowed_chat:
            logger.info("Got message from unregister user.")
        return is_allowed_chat
