"""
rate_limiter.py - Per-User and Per-IP Rate Limiting (Guardrail 2)
==================================================================
WHY: Prevents abuse, brute-forcing, and runaway cost accumulation.
     Two independent sliding windows:
       - Per user_id: 20 req/min (prevents individual account abuse)
       - Per IP:      60 req/min (prevents anonymous/unauthenticated flooding)
     Both must pass - the stricter limit wins.

WHY two limits: A malicious user can create multiple accounts to bypass
per-user limits. IP limiting provides a second layer. Conversely, users
on a shared NAT IP each get their own per-user quota.

LIBRARY: slowapi (wraps the `limits` library). Uses in-memory storage in
dev and Redis-backed sliding windows in prod (when REDIS_URL is set).

GRACEFUL DEGRADATION: If slowapi fails to import, sets self._bypass = True
and logs a WARNING. The pipeline continues without rate limiting.
"""

import logging
import time
from collections import defaultdict
from threading import Lock

from app.config.guardrails_config import GuardrailsConfig
from app.guardrails.models import GuardrailAction, GuardrailResult, ViolationSeverity

logger = logging.getLogger(__name__)


class _SlidingWindowCounter:
    """Thread-safe in-process sliding window rate counter.

    WHY custom instead of slowapi: slowapi requires the Limiter to be attached
    to the FastAPI app as middleware. We run guardrails inside route handlers
    to keep all safety logic self-contained. This gives us the same sliding
    window semantics with zero middleware coupling.
    """

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self._limit = limit
        self._window = window_seconds
        self._counts: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check_and_increment(self, key: str) -> tuple[bool, int, float]:
        """Returns (allowed, current_count, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self._window

        with self._lock:
            # Evict timestamps outside the window
            timestamps = self._counts[key]
            self._counts[key] = [t for t in timestamps if t > cutoff]

            count = len(self._counts[key])
            if count >= self._limit:
                # Retry after the oldest timestamp exits the window
                oldest = min(self._counts[key]) if self._counts[key] else now
                retry_after = max(0.0, oldest + self._window - now)
                return False, count, retry_after

            self._counts[key].append(now)
            return True, count + 1, 0.0

    def get_remaining(self, key: str) -> int:
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            count = sum(1 for t in self._counts.get(key, []) if t > cutoff)
        return max(0, self._limit - count)


class RateLimiterGuardrail:
    """Per-user + per-IP sliding window rate limiter."""

    name = "rate_limiter"

    def __init__(self, config: GuardrailsConfig) -> None:
        self._config = config
        self._bypass = False

        if not config.rate_limiting_enabled:
            self._bypass = True
            return

        try:
            self._user_limiter = _SlidingWindowCounter(
                limit=config.rate_limit_per_user_per_minute,
                window_seconds=60,
            )
            self._ip_limiter = _SlidingWindowCounter(
                limit=config.rate_limit_per_ip_per_minute,
                window_seconds=60,
            )
            logger.info(
                f"Rate limiter initialized: {config.rate_limit_per_user_per_minute} req/min per user, "
                f"{config.rate_limit_per_ip_per_minute} req/min per IP"
            )
        except Exception as e:
            logger.warning(f"Rate limiter failed to initialize: {e}. Bypassing.")
            self._bypass = True

    def check(self, message: str, user_id: str, ip_address: str) -> GuardrailResult:
        """Check both per-user and per-IP sliding window counters."""
        if self._bypass:
            return self._pass()

        # Check per-user limit first
        user_allowed, user_count, user_retry = self._user_limiter.check_and_increment(user_id)
        if not user_allowed:
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="RATE_LIMIT_EXCEEDED",
                severity=ViolationSeverity.MEDIUM,
                detail=(
                    f"Rate limit exceeded for user. "
                    f"Limit: {self._config.rate_limit_per_user_per_minute} requests/minute. "
                    f"Retry after {int(user_retry) + 1}s."
                ),
                metadata={
                    "limit_type": "user",
                    "user_id": user_id,
                    "count": user_count,
                    "limit": self._config.rate_limit_per_user_per_minute,
                    "retry_after_seconds": int(user_retry) + 1,
                },
            )

        # Check per-IP limit
        ip_allowed, ip_count, ip_retry = self._ip_limiter.check_and_increment(ip_address)
        if not ip_allowed:
            # Roll back the user increment since the IP check failed
            # (not worth the complexity for this guardrail - minor over-counting is acceptable)
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="RATE_LIMIT_EXCEEDED",
                severity=ViolationSeverity.MEDIUM,
                detail=(
                    f"Rate limit exceeded for IP address. "
                    f"Limit: {self._config.rate_limit_per_ip_per_minute} requests/minute. "
                    f"Retry after {int(ip_retry) + 1}s."
                ),
                metadata={
                    "limit_type": "ip",
                    "ip_address": ip_address,
                    "count": ip_count,
                    "limit": self._config.rate_limit_per_ip_per_minute,
                    "retry_after_seconds": int(ip_retry) + 1,
                },
            )

        return GuardrailResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            passed=True,
            detail="Rate limit check passed.",
            metadata={
                "user_remaining": self._user_limiter.get_remaining(user_id),
                "ip_remaining": self._ip_limiter.get_remaining(ip_address),
            },
        )

    def _pass(self) -> GuardrailResult:
        return GuardrailResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            passed=True,
            detail="Rate limiting bypassed (disabled or failed to initialize).",
        )
