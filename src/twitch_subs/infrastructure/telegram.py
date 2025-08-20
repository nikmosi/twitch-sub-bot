from __future__ import annotations

from pathlib import Path

import httpx
from loguru import logger

from ..domain.ports import NotifierProtocol
from . import watchlist

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramNotifier(NotifierProtocol):
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

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
    """Minimal Telegram bot to manage the watchlist."""

    def __init__(self, token: str, path: Path | None = None) -> None:
        self.token = token
        self.path = watchlist.resolve_path(path)

    def _api_url(self, method: str) -> str:
        return f"{TELEGRAM_API_BASE}/bot{self.token}/{method}"

    def _send_message(self, chat_id: int, text: str) -> None:
        payload = {"chat_id": chat_id, "text": text}
        try:
            with httpx.Client(timeout=15.0) as c:
                r = c.post(self._api_url("sendMessage"), json=payload)
                r.raise_for_status()
        except Exception:
            logger.exception("Telegram send failed")

    def handle_command(self, text: str) -> str:
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1].strip() if len(parts) > 1 else None
        if cmd == "/add" and arg:
            if watchlist.add(self.path, arg):
                return f"Added {arg}"
            return f"{arg} already present"
        if cmd == "/remove" and arg:
            if watchlist.remove(self.path, arg):
                return f"Removed {arg}"
            return f"{arg} not found"
        if cmd == "/list" and not arg:
            users = watchlist.load(self.path)
            if users:
                return "\n".join(users)
            return "Watchlist is empty"
        return "Unknown command"

    def poll(self, offset: int | None = None) -> int | None:
        params: dict[str, int] = {"timeout": 25}
        if offset is not None:
            params["offset"] = offset
        with httpx.Client(timeout=30.0) as c:
            r = c.get(self._api_url("getUpdates"), params=params)
            r.raise_for_status()
            data = r.json()
        for update in data.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message") or {}
            text = message.get("text")
            chat_id = (message.get("chat") or {}).get("id")
            if not text or chat_id is None:
                continue
            reply = self.handle_command(text)
            self._send_message(chat_id, reply)
        return offset
