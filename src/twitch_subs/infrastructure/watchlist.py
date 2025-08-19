from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Mapping

DEFAULT_PATH = Path(".watchlist.json")
ENV_VAR = "TWITCH_SUBS_WATCHLIST"


def resolve_path(
    path: Path | None = None, env: Mapping[str, str] | None = None
) -> Path:
    """Resolve watchlist path from CLI option, env var or default."""
    if path:
        return path.expanduser()
    env = env or os.environ
    env_path = env.get(ENV_VAR)
    if env_path:
        return Path(env_path).expanduser()
    return DEFAULT_PATH


def load(path: Path) -> list[str]:
    """Load watchlist from *path*, return list of usernames."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []
    users: list[str] | None = data.get("users", [])
    if not isinstance(users, list):
        return []
    return [str(u) for u in users]


def save(path: Path, users: Iterable[str]) -> None:
    """Persist *users* to *path* atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = {"users": sorted(dict.fromkeys(users))}
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def add(path: Path, username: str) -> bool:
    """Add *username* to watchlist at *path*.

    Returns True if username was added, False if already present.
    """
    users = load(path)
    if username in users:
        return False
    users.append(username)
    save(path, users)
    return True


def remove(path: Path, username: str) -> bool:
    """Remove *username* from watchlist at *path*.

    Returns True if username was removed, False if not present.
    """
    users = load(path)
    if username not in users:
        return False
    users = [u for u in users if u != username]
    save(path, users)
    return True
