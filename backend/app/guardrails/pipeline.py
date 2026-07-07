"""
pipeline.py - Guardrails Pipeline Orchestrator
================================================
WHY: A single point of entry that runs all 7 guardrails in the correct sequence,
     manages the working message (possibly transformed by PHI masking), and
     handles graceful degradation when individual guardrails fail.

SEQUENCE (intentional ordering - cheapest checks first, ML models last):
  1. InputValidator          - structural checks (no I/O, stdlib only)
  2. RateLimiterGuardrail    - reject abusive clients before any processing
  3. CostChecker             - reject oversized requests before transformation
  4. DataViolationChecker    - policy checks on original message text
  5. PhiPiiMasker            - TRANSFORM: all subsequent guardrails see masked msg
  6. PromptInjectionDetector - injection on masked message (PHI in injection context)
  7. TopicScopeFilter        - final semantic check on the clean masked message

FAIL-FAST: Any BLOCK action terminates the pipeline immediately and raises
HTTP 400/429. TRANSFORM updates the working message. WARN logs and continues.

GRACEFUL DEGRADATION: If any guardrail fails during __init__, it is set to None
and skipped. A WARNING is logged. The pipeline never raises during startup.

SINGLETON: Use get_guardrails_pipeline() to get the single instance initialized
at app startup. All guardrail ML models (spaCy, sentence-transformers) are
loaded once - not on the first request.
"""

import logging
import time

from fastapi import HTTPException

from app.config.guardrails_config import get_guardrails_config
from app.guardrails.cost_checker import CostChecker
from app.guardrails.data_violation_checker import DataViolationChecker
from app.guardrails.input_validator import InputValidator
from app.guardrails.models import GuardrailAction, PipelineResult
from app.guardrails.phi_pii_masker import PhiPiiMasker
from app.guardrails.prompt_injection_detector import PromptInjectionDetector
from app.guardrails.rate_limiter import RateLimiterGuardrail
from app.guardrails.topic_scope_filter import TopicScopeFilter
from app.guardrails.violation_logger import ViolationLogger

logger = logging.getLogger(__name__)


class GuardrailsPipeline:
    """Composes all 7 guardrails into a sequential pipeline."""

    def __init__(self) -> None:
        config = get_guardrails_config()
        self._config = config
        self._guardrails: list = []
        self._cost_checker: CostChecker | None = None

        if not config.enabled:
            logger.warning(
                "GuardrailsPipeline: ALL guardrails disabled via GUARDRAIL_ENABLED=false. "
                "Set GUARDRAIL_ENABLED=true to enable."
            )
            return

        # Initialize each guardrail independently - failure of one never blocks others
        self._add(InputValidator, config)
        self._add(RateLimiterGuardrail, config)

        cost_checker = self._add(CostChecker, config)
        if cost_checker is not None:
            self._cost_checker = cost_checker  # Keep ref for record_post_run_usage()

        self._add(DataViolationChecker, config)
        self._add(PhiPiiMasker, config)
        self._add(PromptInjectionDetector, config)
        self._add(TopicScopeFilter, config)

        active = [g.name for g in self._guardrails]
        logger.info(
            f"GuardrailsPipeline ready: {len(active)} guardrail(s) active: {', '.join(active)}"
        )

    def _add(self, cls: type, config) -> object | None:
        """Initialize one guardrail, skip on any exception."""
        try:
            instance = cls(config)
            self._guardrails.append(instance)
            return instance
        except Exception as e:
            logger.warning(
                f"Guardrail {cls.__name__} failed to initialize: {e}. Skipping."
            )
            return None

    async def run(
        self,
        message: str,
        user_id: str,
        ip_address: str,
        session_id: str,
    ) -> PipelineResult:
        """Run all active guardrails in sequence.

        Args:
            message:    The fully assembled user message (post file-injection)
            user_id:    From UserInfo.user_id (or "anonymous" in dev mode)
            ip_address: Client IP from Request.client.host
            session_id: From ChatRequest.session_id (for audit logging)

        Returns:
            PipelineResult with allowed=True and final_message (possibly PHI-masked).

        Raises:
            HTTPException(400): on BLOCK from any guardrail
            HTTPException(429): on rate limit exceeded
        """
        if not self._guardrails:
            return PipelineResult(
                allowed=True,
                final_message=message,
                violations=[],
                total_latency_ms=0.0,
            )

        start = time.monotonic()
        working_message = message
        violations = []
        masked_message: str | None = None

        for guardrail in self._guardrails:
            try:
                # Dispatch with appropriate arguments per guardrail type
                if isinstance(guardrail, RateLimiterGuardrail):
                    result = guardrail.check(working_message, user_id, ip_address)
                elif isinstance(guardrail, CostChecker):
                    result = guardrail.check(working_message, user_id)
                elif isinstance(guardrail, PromptInjectionDetector):
                    result = await guardrail.check_async(working_message)
                else:
                    result = guardrail.check(working_message)

                violations.append(result)

                # Apply transformation (PHI masking updates the working message)
                if (
                    result.action == GuardrailAction.TRANSFORM
                    and result.transformed_message
                ):
                    masked_message = result.transformed_message
                    working_message = result.transformed_message
                    logger.debug(
                        f"Guardrail {guardrail.name}: message transformed (PHI masked)"
                    )

                # Fail-fast on BLOCK
                if result.action == GuardrailAction.BLOCK:
                    latency = (time.monotonic() - start) * 1000
                    pipeline_result = PipelineResult(
                        allowed=False,
                        final_message=working_message,
                        violations=violations,
                        blocked_by=guardrail.name,
                        total_latency_ms=latency,
                    )
                    ViolationLogger.log_pipeline_result(
                        pipeline_result,
                        session_id,
                        user_id,
                        ip_address,
                        message,
                        masked_message,
                    )
                    status_code = (
                        429 if "RATE_LIMIT" in (result.violation_code or "") else 400
                    )
                    raise HTTPException(
                        status_code=status_code,
                        detail=result.detail,
                    )

                # Log WARN events immediately (don't wait for pipeline end)
                if result.action == GuardrailAction.WARN:
                    logger.warning(
                        f"Guardrail {guardrail.name} warning: "
                        f"{result.violation_code} - {result.detail}"
                    )

            except HTTPException:
                raise  # Re-raise HTTP exceptions directly
            except Exception as e:
                # Guardrail crashed during check() - bypass this guardrail
                logger.warning(
                    f"Guardrail {guardrail.name} raised during check(): {e}. "
                    "Bypassing this guardrail for this request."
                )

        latency = (time.monotonic() - start) * 1000
        pipeline_result = PipelineResult(
            allowed=True,
            final_message=working_message,
            violations=violations,
            blocked_by=None,
            total_latency_ms=latency,
        )

        # Log any non-PASS results (WARN, TRANSFORM)
        ViolationLogger.log_pipeline_result(
            pipeline_result,
            session_id,
            user_id,
            ip_address,
            message,
            masked_message,
        )

        logger.debug(f"Guardrails pipeline passed in {latency:.1f}ms")
        return pipeline_result

    def record_post_run_usage(self, user_id: str, token_count: int) -> None:
        """Record actual token usage after a successful LLM response.

        Call this from the route handler after chat() returns to update
        the cost checker's rolling window with real token spend.
        """
        if self._cost_checker is not None:
            self._cost_checker.record_usage(user_id, token_count)

    def get_phi_masker(self) -> PhiPiiMasker | None:
        """Return the already-warmed PhiPiiMasker instance, or None if absent.

        Reused by the output masker so the ~2-3s spaCy model load happens once.
        Returns None if PHI masking was disabled or failed to initialize.
        """
        for guardrail in self._guardrails:
            if isinstance(guardrail, PhiPiiMasker):
                return guardrail
        return None


# Module-level singleton - initialized once during lifespan startup
_pipeline: GuardrailsPipeline | None = None


def get_guardrails_pipeline() -> GuardrailsPipeline:
    """Return the singleton GuardrailsPipeline, initializing it on first call."""
    global _pipeline
    if _pipeline is None:
        _pipeline = GuardrailsPipeline()
    return _pipeline
