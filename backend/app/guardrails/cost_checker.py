"""
cost_checker.py - Token Budget Enforcement (Guardrail 3)
==========================================================
WHY: Without budget enforcement, a single malicious or runaway user can
     exhaust the Azure OpenAI quota for everyone else.

TWO LIMITS:
  1. Per-request: blocks oversized single messages before they hit the LLM
  2. Per-user rolling 1-hour: prevents sustained high-volume usage

LIBRARY: tiktoken - the exact BPE tokenizer used by gpt-4o-mini.
     Counting locally is instant and free. Never use the API to count tokens
     (that costs tokens to count tokens).

ROLLING WINDOW: In-memory dict of user_id -> list of (timestamp, count).
     For multi-instance prod deployments, swap for Redis ZADD/ZRANGEBYSCORE.

GRACEFUL DEGRADATION: If tiktoken fails to import, sets self._bypass = True
and logs a WARNING. Pipeline continues without cost checking.
"""

import logging
import time
from threading import Lock

from app.config.guardrails_config import GuardrailsConfig
from app.guardrails.models import GuardrailAction, GuardrailResult, ViolationSeverity

logger = logging.getLogger(__name__)


class CostChecker:
    """Token budget enforcement using tiktoken's exact BPE tokenizer."""

    name = "cost_checker"

    def __init__(self, config: GuardrailsConfig) -> None:
        self._config = config
        self._bypass = False
        self._enc = None
        self._usage: dict[str, list[tuple[float, int]]] = {}  # user_id -> [(ts, tokens)]
        self._lock = Lock()

        if not config.cost_check_enabled:
            self._bypass = True
            return

        try:
            import tiktoken
            # cl100k_base is the encoding for gpt-4o-mini and gpt-4o
            self._enc = tiktoken.get_encoding("cl100k_base")
            logger.info(
                f"Cost checker initialized: {config.token_budget_per_request} tokens/request, "
                f"{config.token_budget_per_user_per_hour} tokens/user/hour"
            )
        except ImportError:
            logger.warning(
                "tiktoken not installed. Cost checking disabled. "
                "Run: pip install tiktoken==0.8.0"
            )
            self._bypass = True
        except Exception as e:
            logger.warning(f"Cost checker failed to initialize: {e}. Bypassing.")
            self._bypass = True

    def count_tokens(self, text: str) -> int:
        """Return exact token count using cl100k_base BPE encoding."""
        if self._enc is None:
            # Rough fallback: ~1.3 tokens per word
            return int(len(text.split()) * 1.3)
        return len(self._enc.encode(text))

    def _get_hourly_usage(self, user_id: str) -> int:
        """Return the rolling 1-hour token count for a user."""
        cutoff = time.monotonic() - 3600
        with self._lock:
            entries = self._usage.get(user_id, [])
            # Evict expired entries in place
            valid = [(ts, count) for ts, count in entries if ts > cutoff]
            self._usage[user_id] = valid
            return sum(count for _, count in valid)

    def check(self, message: str, user_id: str) -> GuardrailResult:
        """Check per-request and per-user hourly token budgets."""
        if self._bypass:
            return self._pass()

        token_count = self.count_tokens(message)

        # 1. Per-request limit
        if token_count > self._config.token_budget_per_request:
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="TOKEN_BUDGET_EXCEEDED",
                severity=ViolationSeverity.MEDIUM,
                detail=(
                    f"Message contains {token_count:,} tokens which exceeds the "
                    f"per-request limit of {self._config.token_budget_per_request:,}. "
                    "Please shorten your message."
                ),
                metadata={
                    "message_tokens": token_count,
                    "per_request_limit": self._config.token_budget_per_request,
                },
            )

        # 2. Per-user hourly limit
        hourly_tokens = self._get_hourly_usage(user_id)
        if hourly_tokens + token_count > self._config.token_budget_per_user_per_hour:
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="HOURLY_TOKEN_BUDGET_EXCEEDED",
                severity=ViolationSeverity.MEDIUM,
                detail=(
                    f"Hourly token budget exceeded. "
                    f"Used: {hourly_tokens:,}, Limit: {self._config.token_budget_per_user_per_hour:,}. "
                    "Please try again in an hour."
                ),
                metadata={
                    "message_tokens": token_count,
                    "user_hourly_tokens": hourly_tokens,
                    "user_hourly_limit": self._config.token_budget_per_user_per_hour,
                },
            )

        return GuardrailResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            passed=True,
            detail="Token budget check passed.",
            metadata={
                "message_tokens": token_count,
                "user_hourly_tokens": hourly_tokens,
                "user_hourly_remaining": self._config.token_budget_per_user_per_hour - hourly_tokens - token_count,
            },
        )

    def record_usage(self, user_id: str, token_count: int) -> None:
        """Record actual token usage after a successful LLM call.

        Called from the pipeline's post-run hook with the real token count
        (from the LLM response, not the pre-flight estimate).
        """
        if self._bypass or token_count <= 0:
            return
        with self._lock:
            if user_id not in self._usage:
                self._usage[user_id] = []
            self._usage[user_id].append((time.monotonic(), token_count))

    def _pass(self) -> GuardrailResult:
        return GuardrailResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            passed=True,
            detail="Cost checking bypassed (disabled or failed to initialize).",
        )
