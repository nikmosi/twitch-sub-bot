from __future__ import annotations

import httpx
from loguru import logger

from ..domain.ports import NotifierProtocol

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramNotifier(NotifierProtocol):
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def send_message(self, text: str, disable_web_page_preview: bool = True) -> None:
        url = f"{TELEGRAM_API_BASE}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
            "parse_mode": "HTML",
        }
        try:
            logger.info("Sending Telegram message")
            with httpx.Client(timeout=15.0) as c:
                r = c.post(url, json=payload)
                r.raise_for_status()
        except Exception:
            logger.exception("Telegram send failed")
