"""
models.py - Shared Guardrail Data Models
==========================================
WHY: Every guardrail returns a GuardrailResult with a consistent shape.
     The pipeline uses these to decide whether to block, warn, or transform
     the message, and to log violations with a uniform audit trail.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class GuardrailAction(str, Enum):
    PASS = "pass"
    BLOCK = "block"          # Raise HTTP 400/429 immediately - pipeline stops here
    WARN = "warn"            # Log the event and continue
    TRANSFORM = "transform"  # Message was mutated (e.g. PHI masked)


class ViolationSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GuardrailResult(BaseModel):
    """Returned by every guardrail's .check() method."""

    guardrail_name: str
    action: GuardrailAction
    passed: bool                        # True = ok to proceed (PASS, WARN, TRANSFORM)
    transformed_message: str | None = None  # Set only when action=TRANSFORM
    violation_code: str | None = None   # e.g. "PHI_DETECTED", "RATE_LIMIT_EXCEEDED"
    severity: ViolationSeverity | None = None
    detail: str = ""                    # Human-readable reason (shown in HTTP error body)
    metadata: dict = {}                 # Extra data for logging (scores, match counts, etc.)


class PipelineResult(BaseModel):
    """Returned by GuardrailsPipeline.run()."""

    allowed: bool
    final_message: str                  # May be transformed from original (PHI masked)
    violations: list[GuardrailResult]   # All guardrail outcomes (pass + fail + warn)
    blocked_by: str | None = None       # Name of the guardrail that blocked the request
    total_latency_ms: float = 0.0


class ViolationEvent(BaseModel):
    """Written to the audit log for every non-passing result.

    PHI-safe: message_preview is ALWAYS taken AFTER PHI masking.
    If the masker itself triggered, this field is replaced with a redaction notice.
    """

    timestamp: datetime
    session_id: str
    user_id: str
    ip_address: str
    guardrail_name: str
    action: GuardrailAction
    violation_code: str | None
    severity: ViolationSeverity | None
    detail: str
    metadata: dict
    message_preview: str  # First 100 chars of message, redacted if PHI detected
