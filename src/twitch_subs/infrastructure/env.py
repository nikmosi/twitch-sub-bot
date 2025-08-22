from __future__ import annotations

import os


def get_db_url() -> str:
    return os.getenv("DB_URL", "sqlite:///./data.db")


def get_db_echo() -> bool:
    return os.getenv("DB_ECHO", "0").lower() in {"1", "true", "yes"}
