"""Retry decorator with exponential backoff for external service calls.

Usage
-----
    from src.utils.retry import with_retry

    @with_retry(max_retries=3, backoff_factor=2.0)
    async def call_llm(prompt: str) -> str:
        ...

Every failed attempt is logged at WARNING level via the structured logger.
After exhausting all retries the original exception is re-raised so the
caller (typically a LangGraph node) can catch it and update `state["errors"]`.
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from src.utils.logger import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def with_retry(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    retriable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    """Decorator factory that adds retry logic with exponential backoff.

    Parameters
    ----------
    max_retries:
        Maximum number of additional attempts after the first failure.
        Total attempts = max_retries + 1.
    backoff_factor:
        Each successive wait = ``backoff_factor ** attempt`` seconds.
        E.g. factor=2 → 1 s, 2 s, 4 s for attempts 0, 1, 2.
    retriable_exceptions:
        Tuple of exception types to catch and retry. Defaults to all
        exceptions; narrow this down in production if needed.

    Returns
    -------
    Callable
        The decorated function preserving the original signature.
    """

    def decorator(func: F) -> F:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc: Exception | None = None
                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except retriable_exceptions as exc:  # noqa: BLE001
                        last_exc = exc
                        if attempt == max_retries:
                            logger.error(
                                "retry_exhausted",
                                function=func.__qualname__,
                                attempt=attempt,
                                max_retries=max_retries,
                                error=str(exc),
                            )
                            raise
                        wait = backoff_factor**attempt
                        logger.warning(
                            "retry_attempt",
                            function=func.__qualname__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            wait_seconds=wait,
                            error=str(exc),
                        )
                        await asyncio.sleep(wait)
                raise last_exc  # type: ignore[misc]  # unreachable but satisfies mypy

            return async_wrapper  # type: ignore[return-value]

        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                last_exc: Exception | None = None
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except retriable_exceptions as exc:  # noqa: BLE001
                        last_exc = exc
                        if attempt == max_retries:
                            logger.error(
                                "retry_exhausted",
                                function=func.__qualname__,
                                attempt=attempt,
                                max_retries=max_retries,
                                error=str(exc),
                            )
                            raise
                        wait = backoff_factor**attempt
                        logger.warning(
                            "retry_attempt",
                            function=func.__qualname__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            wait_seconds=wait,
                            error=str(exc),
                        )
                        time.sleep(wait)
                raise last_exc  # type: ignore[misc]

            return sync_wrapper  # type: ignore[return-value]

    return decorator
