"""Retry utilities with exponential backoff for resilient API calls."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from loguru import logger

from integrations.exceptions import PanelError

T = TypeVar("T")


def retry_with_backoff(
    *,
    max_retries: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (PanelError, ConnectionError, TimeoutError),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay in seconds between retries
        exponential_base: Base for exponential backoff calculation
        jitter: Whether to add random jitter to delays
        retryable_exceptions: Tuple of exception types that should trigger retry

    Returns:
        Decorated function that retries on specified exceptions

    Example:
        ```python
        @retry_with_backoff(max_retries=3, initial_delay=0.5)
        async def api_call():
            # This will retry up to 3 times with exponential backoff
            ...
        ```
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        # Last attempt failed, raise the exception
                        logger.error(
                            f"Function {func.__name__} failed after {max_retries + 1} attempts: {e}",
                            exc_info=e,
                        )
                        raise

                    # Calculate delay with exponential backoff
                    if jitter:
                        # Add random jitter (±25%)
                        jitter_amount = delay * 0.25 * (2 * random.random() - 1)
                        actual_delay = min(delay + jitter_amount, max_delay)
                    else:
                        actual_delay = min(delay, max_delay)

                    logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {actual_delay:.2f}s..."
                    )

                    await asyncio.sleep(actual_delay)
                    delay *= exponential_base

            # This should never be reached, but type checker needs it
            assert last_exception is not None
            raise last_exception

        return wrapper
    return decorator

