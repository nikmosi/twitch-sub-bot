from __future__ import annotations

import argparse
import sys
from signal import SIGTERM, signal
from types import FrameType

from dotenv import load_dotenv
from loguru import logger

from .application.watcher import Watcher
from .domain.exceptions import SigTerm
from .domain.models import TwitchAppCreds
from .infrastructure.env import require_env
from .infrastructure.state import StateRepository
from .infrastructure.telegram import TelegramNotifier
from .infrastructure.twitch import TwitchClient

logger.remove()
logger.add(sys.stderr, level="INFO")


def handle_sigterm(signum: int, frame: FrameType | None) -> None:
    logger.info(f"Got sigterm {signum=}, {frame=}")
    raise SigTerm


def at_exit(notifier: TelegramNotifier) -> None:
    logger.info("Watcher stopped by user")
    try:
        notifier.send_message("🔴 <b>Twitch Subs Watcher</b> остановлен.")
    except Exception:
        pass


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


def cmd_watch(args: argparse.Namespace) -> int:
    interval = args.interval
    logins = list(dict.fromkeys(args.logins))

    load_dotenv()

    tg_token = require_env("TELEGRAM_BOT_TOKEN")
    tg_chat = require_env("TELEGRAM_CHAT_ID")
    creds = TwitchAppCreds(
        client_id=require_env("TWITCH_CLIENT_ID"),
        client_secret=require_env("TWITCH_CLIENT_SECRET"),
    )

    twitch = TwitchClient.from_creds(creds)
    notifier = TelegramNotifier(tg_token, tg_chat)
    state_repo = StateRepository()
    watcher = Watcher(twitch, notifier, state_repo)

    signal(SIGTERM, handle_sigterm)
    logger.info(
        "Starting watch for logins {} with interval {}s", ", ".join(logins), interval
    )

    try:
        watcher.watch(logins, interval)
    except SigTerm:
        at_exit(notifier)
        return 0
    except KeyboardInterrupt:
        at_exit(notifier)
        return 0
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    args = build_parser().parse_args(argv)
    return args.func(args)
