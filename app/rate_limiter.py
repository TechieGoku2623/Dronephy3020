"""Simple in-memory fixed-window rate limiter for SaaS API protection."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import time


@dataclass
class RateLimitWindow:
    """Per-client request counter inside a one-minute window."""

    window_start_s: float
    count: int


class FixedWindowRateLimiter:
    """Enforces requests/minute limits keyed by tenant and principal."""

    def __init__(self, requests_per_minute: int) -> None:
        self._requests_per_minute = requests_per_minute
        self._windows: dict[str, RateLimitWindow] = {}
        self._lock = Lock()

    def consume(self, key: str) -> tuple[bool, int]:
        """
        Consume one quota unit.

        Returns:
            (allowed, remaining)
        """
        now = time()
        with self._lock:
            window = self._windows.get(key)
            if window is None or (now - window.window_start_s) >= 60.0:
                window = RateLimitWindow(window_start_s=now, count=0)
                self._windows[key] = window

            if window.count >= self._requests_per_minute:
                return False, 0

            window.count += 1
            remaining = max(0, self._requests_per_minute - window.count)
            return True, remaining

    @property
    def requests_per_minute(self) -> int:
        """Expose configured request rate limit."""
        return self._requests_per_minute
