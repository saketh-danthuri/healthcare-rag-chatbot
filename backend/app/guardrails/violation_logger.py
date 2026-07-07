"""
violation_logger.py - Structured PHI-Safe Audit Logging
=========================================================
WHY: Compliance requires an append-only audit trail of all guardrail
     violations. Logs must be:
       1. Structured (JSON) - queryable by SIEM tools
       2. PHI-safe - never log the actual sensitive value, only entity types
       3. Correlated - every log entry has session_id, user_id, and IP

THREE LOG DESTINATIONS (additive):
  1. Python logger 'guardrails.audit' -> JSON to stdout/file
     Configure this logger in your logging config to write to a separate
     audit.log file in production. Container log aggregators (e.g. Azure
     Monitor Logs) pick up stdout as structured events.

  2. Existing track_agent_action() in telemetry.py
     Piggybacks on App Insights at zero cost - no new instrumentation needed.

  3. (Optional) Add track_guardrail_run() calls for latency histograms.

PHI-SAFE RULE:
  - If PhiPiiMasker transformed the message: message_preview = "[REDACTED - PHI detected]"
  - Otherwise: message_preview = original_message[:100]
  - NEVER log the pre-masking message content when PHI was found
"""

import json
import logging
from datetime import datetime, timezone

from app.guardrails.models import (
    GuardrailAction,
    PipelineResult,
    ViolationEvent,
    ViolationSeverity,
)

# Dedicated structured audit logger - configure this separately in production
# e.g. logging.config.dictConfig with a FileHandler for 'guardrails.audit'
_audit_logger = logging.getLogger("guardrails.audit")


class ViolationLogger:
    """Writes PHI-safe structured violation events to the audit log."""

    @staticmethod
    def log_pipeline_result(
        result: PipelineResult,
        session_id: str,
        user_id: str,
        ip_address: str,
        original_message: str,
        masked_message: str | None,
    ) -> None:
        """Log all non-passing guardrail results from a pipeline run.

        Skips PASS results to keep audit log focused on events of interest.
        """
        # Determine PHI-safe message preview
        phi_was_detected = any(
            r.violation_code == "PHI_DETECTED" for r in result.violations
        )
        if phi_was_detected:
            message_preview = "[REDACTED - PHI detected, original not logged]"
        else:
            message_preview = original_message[:100]

        # Log events for BLOCK, WARN, and TRANSFORM actions
        for guardrail_result in result.violations:
            if guardrail_result.action == GuardrailAction.PASS:
                continue

            event = ViolationEvent(
                timestamp=datetime.now(timezone.utc),
                session_id=session_id,
                user_id=user_id,
                ip_address=ip_address,
                guardrail_name=guardrail_result.guardrail_name,
                action=guardrail_result.action,
                violation_code=guardrail_result.violation_code,
                severity=guardrail_result.severity,
                detail=guardrail_result.detail,
                metadata=guardrail_result.metadata,
                message_preview=message_preview,
            )
            ViolationLogger.log_violation(event)

        # Also log the overall pipeline outcome if it was blocked
        if result.blocked_by:
            _audit_logger.warning(
                json.dumps(
                    {
                        "event": "pipeline_blocked",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "session_id": session_id,
                        "user_id": user_id,
                        "ip_address": ip_address,
                        "blocked_by": result.blocked_by,
                        "pipeline_latency_ms": round(result.total_latency_ms, 2),
                    }
                )
            )

        # Track in App Insights via existing telemetry
        ViolationLogger._track_in_app_insights(result, session_id)

    @staticmethod
    def log_violation(event: ViolationEvent) -> None:
        """Write a single ViolationEvent as a JSON line to the audit logger."""
        _audit_logger.warning(
            json.dumps(event.model_dump(mode="json"), default=str)
        )

    @staticmethod
    def _track_in_app_insights(result: PipelineResult, session_id: str) -> None:
        """Piggyback on existing telemetry.track_agent_action() for App Insights."""
        try:
            from app.monitoring.telemetry import track_agent_action

            for r in result.violations:
                if r.action != GuardrailAction.PASS:
                    track_agent_action(
                        action_type=f"guardrail.{r.guardrail_name}",
                        status=r.action.value,
                    )
        except Exception:
            pass  # Telemetry failure must never affect request processing
