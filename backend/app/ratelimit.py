"""Limits on the paid path (POST /api/extract) and the anonymous write paths.

- Per-IP sliding one-minute windows, in memory: extractions (EXTRACT_RATE_PER_MINUTE) and
  attempts (`ATTEMPTS_PER_MINUTE`). Production runs a single api instance, so one window sees
  every request; a restart forgets at most the last minute.
- The extraction daily budget (EXTRACT_DAILY_CAP) is counted in Postgres, not here, so scaling
  to zero does not reset it: `app.repository.extract_cache.reserve_run` reserves a slot in
  `daily_usage` before every paid run, failed runs included. `DailyBudget` below is only its
  stand-in while Postgres is unreachable, so an outage never lifts the cap.
- AI drafts ingested per UTC day (`LLM_DRAFTS_PER_DAY`) are counted from the `cases` table by
  the ingest route.
- `client_ip` decides whose window a request counts against.

The windows live on `app.state.limits` (one set per app), built by `make_limits`.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from app.config import Settings
from app.problems import ProblemError
from app.security import require_internal_key

WINDOW_S = 60.0
DAY_S = 86_400
MAX_TRACKED_KEYS = 10_000
ATTEMPTS_PER_MINUTE = 20  # a physician closes a case in minutes; a script closes it in ms
LLM_DRAFTS_PER_DAY = 20  # AI drafts published to the catalogue per UTC day

type Clock = Callable[[], float]


class RateLimited(Exception):
    def __init__(self, message: str, retry_after_s: int) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


def seconds_to_utc_midnight(now: float) -> int:
    return int(DAY_S - now % DAY_S)


def daily_budget_used_up(now: float | None = None) -> RateLimited:
    moment = time.time() if now is None else now
    return RateLimited(
        "The daily extraction budget is used up; try again tomorrow (UTC).",
        retry_after_s=seconds_to_utc_midnight(moment),
    )


class SlidingWindow:
    """At most `per_minute` calls per key in any 60 s. Rejected calls are not counted."""

    def __init__(self, per_minute: int, noun: str, clock: Clock = time.time) -> None:
        self._per_minute = per_minute
        self._noun = noun
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        now = self._clock()
        window = self._hits.setdefault(key, deque())
        while window and now - window[0] >= WINDOW_S:
            window.popleft()
        if len(window) >= self._per_minute:
            retry = max(1, math.ceil(WINDOW_S - (now - window[0])))
            raise RateLimited(
                f"At most {self._per_minute} {self._noun} per minute; retry in {retry} s.",
                retry_after_s=retry,
            )
        window.append(now)
        if len(self._hits) > MAX_TRACKED_KEYS:
            self._forget_idle(now)

    def _forget_idle(self, now: float) -> None:
        for key in [k for k, w in self._hits.items() if not w or now - w[-1] >= WINDOW_S]:
            del self._hits[key]


class DailyBudget:
    """In-memory day budget: the fallback while the Postgres counter cannot be reached."""

    def __init__(self, cap: int, clock: Clock = time.time) -> None:
        self._cap = cap
        self._clock = clock
        self._day = -1
        self._count = 0

    def take(self) -> None:
        now = self._clock()
        day = int(now // DAY_S)
        if day != self._day:
            self._day, self._count = day, 0
        if self._count >= self._cap:
            raise daily_budget_used_up(now)
        self._count += 1


@dataclass(frozen=True, slots=True)
class Limits:
    extract_per_ip: SlidingWindow
    extract_day_fallback: DailyBudget
    attempts_per_ip: SlidingWindow


def make_limits(settings: Settings) -> Limits:
    return Limits(
        extract_per_ip=SlidingWindow(settings.extract_rate_per_minute, "extractions"),
        extract_day_fallback=DailyBudget(settings.extract_daily_cap),
        attempts_per_ip=SlidingWindow(ATTEMPTS_PER_MINUTE, "attempts"),
    )


def get_limits(request: Request) -> Limits:
    limits: Limits = request.app.state.limits
    return limits


def _from_web_server(request: Request) -> bool:
    try:
        require_internal_key(request)  # open when no key is configured (local, tests)
    except ProblemError:
        return False
    return True


def client_ip(request: Request) -> str:
    """The address a per-IP window counts against.

    Cloud Run's front end appends the peer it saw to X-Forwarded-For, so the LAST entry is the
    real caller and anything before it is whatever the client sent. The web server is the one
    exception: it holds the internal key and forwards the browser's address as the first entry,
    so that entry is trusted only on a request carrying the key.
    """
    entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",")]
    entries = [e for e in entries if e]
    if entries:
        return entries[0] if _from_web_server(request) else entries[-1]
    return request.client.host if request.client else "unknown"
