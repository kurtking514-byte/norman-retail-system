"""
In-memory limiter for failed admin login attempts.

Failed attempts are counted per client IP and per username inside a sliding
window. Once a key reaches its limit, further attempts are refused (HTTP 429)
until the oldest failure falls out of the window. A successful login clears
the IP's failures.

The username limit is the one that can't be dodged by changing IP or spoofing
headers. The trade-off is that someone hammering the admin username can also
lock the real admin out until the window passes.

State lives in process memory, which fits the single-instance Render deploy
(WEB_CONCURRENCY=1). It resets on restart.
"""

import time
from collections import defaultdict, deque

WINDOW_SECONDS = 15 * 60
MAX_FAILURES_PER_IP = 5
MAX_FAILURES_PER_USERNAME = 10


class LoginRateLimiter:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        attempts = self._failures[key]
        cutoff = self._clock() - WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        return attempts

    def _retry_after(self, key: str, limit: int) -> int:
        attempts = self._prune(key)
        if len(attempts) < limit:
            return 0
        return max(1, int(attempts[0] + WINDOW_SECONDS - self._clock()) + 1)

    def retry_after(self, ip: str, username: str) -> int:
        """Seconds until another attempt is allowed, or 0 if allowed now."""
        return max(
            self._retry_after(f"ip:{ip}", MAX_FAILURES_PER_IP),
            self._retry_after(f"user:{username.lower()}", MAX_FAILURES_PER_USERNAME),
        )

    def record_failure(self, ip: str, username: str) -> None:
        now = self._clock()
        self._failures[f"ip:{ip}"].append(now)
        self._failures[f"user:{username.lower()}"].append(now)

    def record_success(self, ip: str) -> None:
        self._failures.pop(f"ip:{ip}", None)

    def reset(self) -> None:
        self._failures.clear()


login_limiter = LoginRateLimiter()
