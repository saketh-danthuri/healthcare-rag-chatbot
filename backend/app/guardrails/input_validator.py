"""
input_validator.py - Structural Input Validation (Guardrail 1)
================================================================
WHY first in the pipeline: These are cheap, zero-I/O checks that catch
     malformed or adversarial payloads before any ML or API calls happen.
     Pydantic's max_length catches size, but not structural attacks.

CHECKS:
  1. Null bytes / non-printable control characters  -> break tokenizers
  2. Excessive newlines                             -> padding attacks
  3. URL flooding                                   -> potential SSRF exfiltration
  4. Long repeated character runs                   -> fuzzing / DoS
  5. MIME data URIs                                 -> binary injection
  6. Unicode directional override characters        -> invisible text injection

No external dependencies - stdlib re only. This guardrail must never fail
to initialize due to a missing package.
"""

import re

from app.config.guardrails_config import GuardrailsConfig
from app.guardrails.models import GuardrailAction, GuardrailResult, ViolationSeverity

# Pre-compiled patterns for performance
_NULL_BYTE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_URL_RE = re.compile(r"https?://", re.IGNORECASE)
_MIME_URI_RE = re.compile(r"data:(?:image|application|audio|video)/", re.IGNORECASE)
# Unicode directional overrides used in "invisible text" injection attacks
_UNICODE_OVERRIDE_RE = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]"
)


class InputValidator:
    """Structural input validation - the first and cheapest guardrail.

    Never throws during check(). Returns BLOCK result instead of raising.
    """

    name = "input_validator"

    def __init__(self, config: GuardrailsConfig) -> None:
        self._config = config

    def check(self, message: str) -> GuardrailResult:
        """Run all structural checks. Short-circuits on first failure."""
        if not self._config.input_validation_enabled:
            return self._pass()

        # 1. Null bytes and non-printable control characters
        if _NULL_BYTE_RE.search(message):
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="CONTROL_CHARACTERS",
                severity=ViolationSeverity.HIGH,
                detail="Message contains null bytes or non-printable control characters.",
                metadata={"failed_check": "control_characters"},
            )

        # 2. Unicode directional override characters (invisible text injection)
        match = _UNICODE_OVERRIDE_RE.search(message)
        if match:
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="UNICODE_OVERRIDE",
                severity=ViolationSeverity.HIGH,
                detail="Message contains Unicode directional override characters.",
                metadata={"failed_check": "unicode_override", "char_ord": ord(match.group())},
            )

        # 3. MIME data URIs (binary injection attempt)
        if _MIME_URI_RE.search(message):
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="MIME_DATA_URI",
                severity=ViolationSeverity.MEDIUM,
                detail="Message contains MIME data URI which is not permitted.",
                metadata={"failed_check": "mime_data_uri"},
            )

        # 4. Excessive newlines (padding attacks)
        newline_count = message.count("\n")
        if newline_count > self._config.max_newlines:
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="EXCESSIVE_NEWLINES",
                severity=ViolationSeverity.MEDIUM,
                detail=f"Message contains {newline_count} newlines (limit: {self._config.max_newlines}).",
                metadata={"failed_check": "newlines", "count": newline_count, "limit": self._config.max_newlines},
            )

        # 5. URL flooding (SSRF / context exfiltration attempt)
        url_count = len(_URL_RE.findall(message))
        if url_count > self._config.max_urls:
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="URL_FLOODING",
                severity=ViolationSeverity.MEDIUM,
                detail=f"Message contains {url_count} URLs (limit: {self._config.max_urls}).",
                metadata={"failed_check": "url_count", "count": url_count, "limit": self._config.max_urls},
            )

        # 6. Long repeated character runs (fuzzing / DoS probing)
        repeated_match = re.search(r"(.)\1{" + str(self._config.max_repeated_chars) + r",}", message)
        if repeated_match:
            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.BLOCK,
                passed=False,
                violation_code="REPEATED_CHARS",
                severity=ViolationSeverity.LOW,
                detail="Message contains an abnormally long run of repeated characters.",
                metadata={"failed_check": "repeated_chars", "char": repr(repeated_match.group(1))},
            )

        return self._pass()

    def _pass(self) -> GuardrailResult:
        return GuardrailResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            passed=True,
            detail="All structural checks passed.",
        )
