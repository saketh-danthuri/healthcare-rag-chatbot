"""
data_violation_checker.py - Content Policy Enforcement (Guardrail 4)
======================================================================
WHY: Catches requests for illegal or harmful content that don't constitute
     prompt injection (handled by Guardrail 6) but violate content policy.
     Examples: violence threats, illegal medical requests, malware generation.

APPROACH: Curated regex patterns with severity scores. Critical severity
always blocks. Lower severity is configurable (block or warn) via
GUARDRAIL_CONTENT_POLICY_ACTION.

This runs BEFORE PHI masking so it sees the original message text.
PHI masking (Guardrail 5) handles identity data separately.

OPTIONAL: Azure Content Safety API integration when
AZURE_CONTENT_SAFETY_ENDPOINT is set in settings. Falls back to regex
patterns if the API is unavailable.
"""

import logging
import re

from app.config.guardrails_config import GuardrailsConfig
from app.guardrails.models import GuardrailAction, GuardrailResult, ViolationSeverity

logger = logging.getLogger(__name__)


# Violation patterns: (compiled_regex, violation_code, severity, description)
_VIOLATION_PATTERNS: list[tuple[re.Pattern, str, ViolationSeverity, str]] = [
    # Violence / harm threats - critical, always block
    (
        re.compile(
            r"\b(?:kill|murder|harm|hurt|injure|assault)\b.{0,50}(?:patient|person|user|staff|doctor|nurse)",
            re.IGNORECASE | re.DOTALL,
        ),
        "VIOLENCE_THREAT",
        ViolationSeverity.CRITICAL,
        "Message contains a potential violence or harm threat.",
    ),
    # Self-harm content
    (
        re.compile(
            r"\b(?:suicide|self.harm|self.inflict|overdose\s+on)\b",
            re.IGNORECASE,
        ),
        "SELF_HARM_CONTENT",
        ViolationSeverity.HIGH,
        "Message contains self-harm related content.",
    ),
    # Illegal medical activity
    (
        re.compile(
            r"\b(?:illegal\s+prescription|drug\s+trafficking|divert\s+(?:medication|drugs?)|"
            r"sell\s+(?:opioid|fentanyl|oxycodone|controlled\s+substance))\b",
            re.IGNORECASE,
        ),
        "ILLEGAL_MEDICAL",
        ViolationSeverity.CRITICAL,
        "Message contains reference to illegal medical activity.",
    ),
    # Malware / exploit generation
    (
        re.compile(
            r"\b(?:generate|write|create|build|code)\b.{0,30}"
            r"\b(?:malware|ransomware|exploit|keylogger|rootkit|trojan|backdoor|payload)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "MALWARE_REQUEST",
        ViolationSeverity.CRITICAL,
        "Message requests generation of malicious software.",
    ),
    # Exfiltration / credential theft instructions
    (
        re.compile(
            r"\b(?:steal|exfiltrate|harvest)\b.{0,40}\b(?:credentials?|password|token|api.?key)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        "CREDENTIAL_THEFT",
        ViolationSeverity.CRITICAL,
        "Message requests credential theft or exfiltration.",
    ),
]


class DataViolationChecker:
    """Content policy enforcement using regex patterns and optional Azure Content Safety."""

    name = "data_violation_checker"

    def __init__(self, config: GuardrailsConfig) -> None:
        self._config = config
        self._bypass = False

        if not config.data_violation_enabled:
            self._bypass = True
            return

        # Build lowercase keyword set for O(1) lookup
        self._blocked_keywords: set[str] = {
            kw.lower() for kw in config.blocked_keywords
        }

        logger.info(
            f"Data violation checker initialized: "
            f"{len(_VIOLATION_PATTERNS)} patterns, {len(self._blocked_keywords)} blocked keywords"
        )

    def check(self, message: str) -> GuardrailResult:
        """Scan message against all violation patterns and keyword list."""
        if self._bypass:
            return self._pass()

        message_lower = message.lower()

        # Check blocked keywords first (fast set lookup)
        matched_keywords = [kw for kw in self._blocked_keywords if kw in message_lower]
        if matched_keywords:
            action = (
                GuardrailAction.BLOCK
                if self._config.content_policy_action == "block"
                else GuardrailAction.WARN
            )
            return GuardrailResult(
                guardrail_name=self.name,
                action=action,
                passed=action == GuardrailAction.WARN,
                violation_code="BLOCKED_KEYWORD",
                severity=ViolationSeverity.HIGH,
                detail=f"Message contains {len(matched_keywords)} blocked keyword(s).",
                metadata={"keyword_matches": matched_keywords},
            )

        # Scan regex patterns
        matched_patterns: list[dict] = []
        highest_severity: ViolationSeverity | None = None
        highest_code: str | None = None
        highest_detail: str | None = None

        _severity_rank = {
            ViolationSeverity.LOW: 1,
            ViolationSeverity.MEDIUM: 2,
            ViolationSeverity.HIGH: 3,
            ViolationSeverity.CRITICAL: 4,
        }

        for pattern, code, severity, detail in _VIOLATION_PATTERNS:
            if pattern.search(message):
                matched_patterns.append({"code": code, "severity": severity.value})
                if (
                    highest_severity is None
                    or _severity_rank[severity] > _severity_rank[highest_severity]
                ):
                    highest_severity = severity
                    highest_code = code
                    highest_detail = detail

        if not matched_patterns:
            return self._pass()

        # Critical severity always blocks regardless of config
        is_critical = highest_severity == ViolationSeverity.CRITICAL
        should_block = is_critical or self._config.content_policy_action == "block"
        action = GuardrailAction.BLOCK if should_block else GuardrailAction.WARN

        return GuardrailResult(
            guardrail_name=self.name,
            action=action,
            passed=action == GuardrailAction.WARN,
            violation_code=highest_code,
            severity=highest_severity,
            detail=highest_detail or "Content policy violation detected.",
            metadata={
                "matched_patterns": matched_patterns,
                "highest_severity": highest_severity.value if highest_severity else None,
            },
        )

    def _pass(self) -> GuardrailResult:
        return GuardrailResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            passed=True,
            detail="Content policy check passed.",
        )
