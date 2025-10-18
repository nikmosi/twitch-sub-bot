from __future__ import annotations


from aiogram.filters import Filter
from aiogram.types import Message
from loguru import logger


class IDFilter(Filter):
    def __init__(self, id: str):
        self._id = int(id)

    async def __call__(self, obj: Message) -> bool:
        res = obj.chat.id == self._id
        if not res:
            logger.info("Got message from unregister user.")
        return res
