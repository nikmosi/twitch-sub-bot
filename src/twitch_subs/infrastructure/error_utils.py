from __future__ import annotations

import asyncio
import functools
import inspect
import traceback
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from loguru import logger

from twitch_subs.errors import AppError

P = ParamSpec("P")
R = TypeVar("R")


def _format_tail(exc: BaseException, *, limit: int = 6) -> str:
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    return "".join(tb[-limit:])


def log_and_wrap(
    exc: BaseException,
    module_exc_cls: type[AppError],
    log,  # loguru logger-like
    context: dict[str, Any] | None = None,
) -> AppError:
    formatted_tb = _format_tail(exc)
    log.opt(exception=exc).exception("%s", formatted_tb)
    wrapped = module_exc_cls(str(exc), context=context or {})
    raise wrapped from exc


def wrap_exceptions(module_exc_cls: type[AppError]) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to log short traceback and wrap errors into *module_exc_cls*."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs):  # type: ignore[override]
                try:
                    return await func(*args, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # pragma: no cover - thin wrapper
                    formatted_tb = _format_tail(exc)
                    logger.opt(exception=exc).exception("%s", formatted_tb)
                    raise module_exc_cls(str(exc)) from exc

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs):  # type: ignore[override]
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - thin wrapper
                formatted_tb = _format_tail(exc)
                logger.opt(exception=exc).exception("%s", formatted_tb)
                raise module_exc_cls(str(exc)) from exc

        return sync_wrapper  # type: ignore[return-value]

    return decorator
