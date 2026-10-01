"""In-memory limits for POST /api/extract: a per-IP sliding window plus a global daily cap.

State lives in one process (per Cloud Run instance, max 3). Production alternative: Cloud Armor
rate-based rules or a shared Redis/Memorystore counter.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache

from fastapi import Request

from app.config import get_settings

WINDOW_S = 60.0
DAY_S = 86_400
MAX_TRACKED_KEYS = 10_000


class RateLimited(Exception):
    def __init__(self, message: str, retry_after_s: int) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class ExtractLimiter:
    def __init__(
        self, per_minute: int, daily_cap: int, clock: Callable[[], float] = time.time
    ) -> None:
        self._per_minute = per_minute
        self._daily_cap = daily_cap
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._day = -1
        self._day_count = 0

    def check(self, key: str) -> None:
        """Record one request for `key` or raise RateLimited (rejected calls are not counted)."""
        now = self._clock()
        day = int(now // DAY_S)
        if day != self._day:
            self._day, self._day_count = day, 0
        if self._day_count >= self._daily_cap:
            raise RateLimited(
                "The daily extraction budget is used up; try again tomorrow (UTC).",
                retry_after_s=int(DAY_S - now % DAY_S),
            )
        window = self._hits.setdefault(key, deque())
        while window and now - window[0] >= WINDOW_S:
            window.popleft()
        if len(window) >= self._per_minute:
            retry = max(1, math.ceil(WINDOW_S - (now - window[0])))
            raise RateLimited(
                f"At most {self._per_minute} extractions per minute; retry in {retry} s.",
                retry_after_s=retry,
            )
        window.append(now)
        self._day_count += 1
        if len(self._hits) > MAX_TRACKED_KEYS:
            self._forget_idle(now)

    def _forget_idle(self, now: float) -> None:
        for key in [k for k, w in self._hits.items() if not w or now - w[-1] >= WINDOW_S]:
            del self._hits[key]


@lru_cache(maxsize=1)
def get_limiter() -> ExtractLimiter:
    settings = get_settings()
    return ExtractLimiter(settings.extract_rate_per_minute, settings.extract_daily_cap)


def client_ip(request: Request) -> str:
    """The end user's IP. The web server forwards it in X-Forwarded-For (first entry);
    only callers holding the internal key reach this check, so the header is trusted."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"
