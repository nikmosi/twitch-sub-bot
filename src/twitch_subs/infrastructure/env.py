import os


def require_env(name: str) -> str:
    """Return the value of the environment variable *name* or raise."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment var {name} is required")
    return value
