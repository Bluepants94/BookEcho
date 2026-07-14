"""Simple process-local sliding-window rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, status


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str, *, limit: int, window_seconds: float) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="请求过于频繁，请稍后再试",
                )
            bucket.append(now)


limiter = SlidingWindowRateLimiter()


def client_ip(request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
