"""A small retry helper shared by the market-data and Claude steps.

Deliberately tiny: exponential backoff with a cap, an optional predicate so
callers can decide what is worth retrying, and a hook so tests can run it with
no real sleeping.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Iterable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.5,
    max_delay: float = 20.0,
    retry_on: Iterable[type[BaseException]] = (Exception,),
    should_retry: Callable[[BaseException], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    label: str = "call",
) -> T:
    """Call ``fn``, retrying transient failures with exponential backoff.

    The final failure is re-raised untouched so callers can inspect the real
    cause rather than a wrapper.
    """

    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    retry_on = tuple(retry_on)
    last: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except retry_on as exc:  # noqa: PERF203 - the try/except is the point
            last = exc
            if should_retry is not None and not should_retry(exc):
                raise
            if attempt == attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            log.warning(
                "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                label,
                attempt,
                attempts,
                exc,
                delay,
            )
            sleep(delay)

    # Unreachable: the loop either returns or raises.
    raise last  # type: ignore[misc]
