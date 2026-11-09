"""
A tiny time-based cache for async functions.

The frontend polls every few seconds. Without a cache every poll would hit
GitHub/Jenkins and we would quickly reach API rate limits (GitHub allows only
60 unauthenticated requests per hour). Results are reused for `ttl` seconds.
No external library (like Redis) is needed for a single-process app.
"""

from __future__ import annotations

import asyncio
import time
from functools import wraps
from typing import Any, Awaitable, Callable


def ttl_cache(ttl: float) -> Callable:
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        store: dict[tuple, tuple[float, Any]] = {}
        locks: dict[tuple, asyncio.Lock] = {}

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = (args, tuple(sorted(kwargs.items())))
            hit = store.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
            lock = locks.setdefault(key, asyncio.Lock())
            async with lock:  # concurrent callers share one upstream request
                hit = store.get(key)
                if hit and time.monotonic() - hit[0] < ttl:
                    return hit[1]
                value = await func(*args, **kwargs)
                store[key] = (time.monotonic(), value)
                return value

        wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
        return wrapper

    return decorator
