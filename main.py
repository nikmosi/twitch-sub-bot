#!/usr/bin/env python3
"""
Twitch Subs Checker → Telegram Notifier

Что делает:
- Следит за списком логинов в Twitch и ШЛЁТ УВЕДОМЛЕНИЕ В TELEGRAM,
  когда статус канала меняется на `affiliate` или `partner`.
- Использует Helix /users (broadcaster_type ∈ {"", "affiliate", "partner"}).
- Без лишнего шума в консоль — уведомления идут в ТГ.

CLI:
  python twitch_subs_checker.py watch <login1> [<login2> ...] [--interval 300]

Переменные окружения (обязательно):
  TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  # куда слать уведомления

Зависимости: httpx
(Чат-бот TwitchIO из предыдущей версии убран из CLI по запросу — фокус на Telegram.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

import httpx
from dotenv import load_dotenv
from loguru import logger

# ====== Logging setup =========================================================
logger.remove()
logger.add(sys.stderr, level="INFO")

# ====== Константы Twitch =====================================================
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"

BroadcasterType = Literal["", "affiliate", "partner"]


# ====== Модели ===============================================================
@dataclass(frozen=True)
class TwitchAppCreds:
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class UserRecord:
    id: str
    login: str
    display_name: str
    broadcaster_type: BroadcasterType


# ====== Утилиты ==============================================================
STATE_FILE = Path(".subs_status.json")


def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Environment var {name} is required")
    return v


# ====== Twitch API ===========================================================


def get_app_token(creds: TwitchAppCreds) -> str:
    data = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "grant_type": "client_credentials",
    }
    with httpx.Client(timeout=20.0) as c:
        r = c.post(TWITCH_TOKEN_URL, data=data)
        r.raise_for_status()
        return r.json()["access_token"]


def get_user_by_login(login: str, client_id: str, app_token: str) -> UserRecord | None:
    headers = {"Client-Id": client_id, "Authorization": f"Bearer {app_token}"}
    params = {"login": login}
    with httpx.Client(timeout=15.0) as c:
        r = c.get(TWITCH_USERS_URL, headers=headers, params=params)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return None
        u = data[0]
        return UserRecord(
            id=u["id"],
            login=u["login"],
            display_name=u.get("display_name", u["login"]),
            broadcaster_type=u.get("broadcaster_type", ""),
        )


def is_subscribable(btype: BroadcasterType) -> bool:
    return btype in ("affiliate", "partner")


# ====== Telegram =============================================================

TELEGRAM_API_BASE = "https://api.telegram.org"


def send_telegram_message(
    token: str, chat_id: str, text: str, disable_web_page_preview: bool = True
) -> None:
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
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
        # Не валим процесс, но сигналим
        logger.exception("Telegram send failed")


# ====== State ================================================================


def load_state(path: Path = STATE_FILE) -> dict[str, BroadcasterType]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_state(state: dict[str, BroadcasterType], path: Path = STATE_FILE) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(path)


# ====== Core ================================================================


def check_logins(
    logins: Iterable[str],
) -> list[tuple[str, BroadcasterType | None, UserRecord | None]]:
    creds = TwitchAppCreds(
        client_id=_require_env("TWITCH_CLIENT_ID"),
        client_secret=_require_env("TWITCH_CLIENT_SECRET"),
    )
    token = get_app_token(creds)
    out: list[tuple[str, BroadcasterType | None, UserRecord | None]] = []
    for login in logins:
        logger.info("Checking login {}", login)
        u = get_user_by_login(login, creds.client_id, token)
        btype = None if u is None else u.broadcaster_type
        logger.info("Login {} status {}", login, btype or "not-found")
        out.append((login, btype, u))
    return out


# ====== CLI команды ==========================================================


def cmd_watch(args: argparse.Namespace) -> int:
    interval = args.interval
    logins = list(dict.fromkeys(args.logins))

    # TG окружение
    tg_token = _require_env("TELEGRAM_BOT_TOKEN")
    tg_chat = _require_env("TELEGRAM_CHAT_ID")

    state = load_state()

    logger.info(
        "Starting watch for logins {} with interval {}s", ", ".join(logins), interval
    )

    # Одноразовый пинг, чтобы знать, что вотчер запущен
    try:
        send_telegram_message(
            tg_token,
            tg_chat,
            "🟢 <b>Twitch Subs Watcher</b> запущен. Мониторю: "
            + ", ".join(f"<code>{l}</code>" for l in logins),
        )
    except Exception:
        pass

    try:
        while True:
            rows = check_logins(logins)
            changed = False
            for login, btype, u in rows:
                prev = state.get(login, "")
                curr: BroadcasterType = btype or ""
                if prev != curr:
                    state[login] = curr
                    changed = True
                    logger.info("Status change for {}: {} -> {}", login, prev, curr)
                    # Уведомляем ТОЛЬКО если новый статус — affiliate или partner
                    if curr in ("affiliate", "partner"):
                        # Формируем заметку
                        display = u.display_name if u else login
                        badge = "🟣" if curr == "partner" else "🟡"
                        subflag = "да" if is_subscribable(curr) else "нет"
                        text = (
                            f"{badge} <b>{display}</b> стал <b>{curr}</b>\n"
                            f"Подписка доступна: <b>{subflag}</b>\n"
                            f"Логин: <code>{login}</code>"
                        )
                        send_telegram_message(tg_token, tg_chat, text)
            if changed:
                logger.info("State changed, saving")
                save_state(state)
            time.sleep(interval)
    except KeyboardInterrupt:
        # Тихо выходим
        logger.info("Watcher stopped by user")
        return 0

    return 0


# ====== Парсер ===============================================================


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="twitch-subs-checker",
        description="Watch Twitch logins and notify Telegram when broadcaster_type becomes affiliate/partner",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_watch = sub.add_parser(
        "watch", help="Watch multiple logins for status changes → Telegram notify"
    )
    p_watch.add_argument("logins", nargs="+")
    p_watch.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Poll interval, seconds (default: 300)",
    )
    p_watch.set_defaults(func=cmd_watch)

    return p


# ====== Entry ================================================================


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    argv = argv or sys.argv[1:]
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
