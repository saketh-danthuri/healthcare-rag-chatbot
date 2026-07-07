"""
output_masker.py - Sentence-buffered, role-gated PHI masking for OUTPUT
========================================================================
WHY: The input pipeline masks the user's message for everyone, but the
     assistant's answer can surface PHI pulled from RETRIEVED documents. This
     masks the streamed output server-side, per user role, so no raw PHI ever
     crosses the wire for a "general" user.

STREAMING vs MASKING TENSION: Presidio/spaCy NER needs whole-text context, but
     streaming emits fragments. Masking a partial chunk risks splitting an
     entity across chunk boundaries (a name/SSN straddling two tokens would be
     missed). SOLUTION: sentence-buffered masking - accumulate tokens, flush
     only on a sentence/line boundary, mask that complete unit, THEN emit.

ROLE GATE:
  - clinician -> passthrough (sees unmasked PHI from retrieved docs)
  - general   -> each flushed unit masked with Presidio (default; most restrictive)

FAIL-CLOSED: if Presidio/spaCy is unavailable and the user is "general",
     withhold raw output entirely (emit a redaction notice) rather than leak
     PHI. Governed by GUARDRAIL_OUTPUT_MASK_FAIL_CLOSED (default True).

RESIDUAL RISK (documented): an entity spanning an abbreviation boundary (e.g.
     "Dr. Smith") or a single token longer than MAX_BUFFER with no whitespace
     may be split. Sentence-buffering makes this rare; whole-text input masking
     is unaffected.
"""

import logging
import re
from collections.abc import AsyncIterator

from app.config.guardrails_config import GuardrailsConfig, get_guardrails_config
from app.guardrails.models import GuardrailAction
from app.guardrails.phi_pii_masker import PhiPiiMasker

logger = logging.getLogger(__name__)

CLINICIAN = "clinician"
GENERAL = "general"

# A flushable unit ends at a sentence terminator followed by whitespace, or a
# newline. The trailing whitespace is left in the buffer (harmless leading space
# on the next unit). We deliberately do NOT anchor on end-of-string here so that
# a period that is merely the current tail (more tokens coming) does not flush
# prematurely; the trailing buffer is flushed whole at the end of the stream.
_FLUSH_RE = re.compile(r".*?(?:[.!?](?=\s)|\n)", re.DOTALL)

# Force-flush the buffer past this length even without a boundary, so a runaway
# sentence never stalls the stream. We cut at the last whitespace to avoid
# splitting a word (and thus an entity token) mid-way.
MAX_BUFFER = 400


class OutputMasker:
    """Masks streamed (and stored) assistant output per user role."""

    def __init__(self, masker: PhiPiiMasker | None, config: GuardrailsConfig) -> None:
        self._masker = masker
        self._config = config

    @property
    def _can_mask(self) -> bool:
        return self._masker is not None and self._masker.is_active

    async def stream_masked(
        self, token_iter: AsyncIterator[str], role: str
    ) -> AsyncIterator[str]:
        """Consume raw token deltas and yield masked, sentence-buffered units.

        Always drains `token_iter` to completion (even when withholding) so the
        underlying graph run finishes and a post-run state snapshot is valid.
        """
        # Fail-closed short-circuit: emit one notice, then drain silently.
        if self._should_withhold(role):
            yield self._config.output_mask_redaction_notice
            async for _ in token_iter:
                pass
            return

        buffer = ""
        async for token in token_iter:
            if not token:
                continue
            buffer += token
            units, buffer = self._extract_units(buffer, final=False)
            for unit in units:
                yield self._mask_unit(unit, role)

        # Flush whatever remains (the last, possibly-unterminated sentence).
        if buffer:
            yield self._mask_unit(buffer, role)

    def mask_text(self, text: str, role: str) -> str:
        """Mask a COMPLETE assistant text per role (whole-text; no buffering).

        Used by the conversation rehydration read path, where stored raw text is
        masked at display time for "general" users.
        """
        if not text or not self._config.output_masking_enabled or role == CLINICIAN:
            return text
        if not self._can_mask:
            if self._config.output_mask_fail_closed:
                return self._config.output_mask_redaction_notice
            return text
        return self._apply(text)

    # --- internals ---

    def _should_withhold(self, role: str) -> bool:
        return (
            self._config.output_masking_enabled
            and role != CLINICIAN
            and not self._can_mask
            and self._config.output_mask_fail_closed
        )

    def _extract_units(self, buffer: str, final: bool) -> tuple[list[str], str]:
        """Split off all complete sentence/line units; return (units, remainder)."""
        units: list[str] = []
        while True:
            match = _FLUSH_RE.match(buffer)
            if not match or match.end() == 0:
                break
            units.append(buffer[: match.end()])
            buffer = buffer[match.end() :]

        if not final and len(buffer) > MAX_BUFFER:
            cut = buffer.rfind(" ")
            if cut > 0:
                units.append(buffer[: cut + 1])
                buffer = buffer[cut + 1 :]

        return units, buffer

    def _mask_unit(self, unit: str, role: str) -> str:
        if not self._config.output_masking_enabled or role == CLINICIAN:
            return unit
        # general: fail-closed is handled upstream in stream_masked; here a
        # non-maskable state degrades open (only reached when fail_closed=False).
        if not self._can_mask:
            return unit
        return self._apply(unit)

    def _apply(self, text: str) -> str:
        result = self._masker.check(text)
        if (
            result.action == GuardrailAction.TRANSFORM
            and result.transformed_message is not None
        ):
            return result.transformed_message
        return text


# Module-level singleton, built lazily from the already-warmed pipeline masker.
_output_masker: OutputMasker | None = None


def get_output_masker() -> OutputMasker:
    """Return the singleton OutputMasker, reusing the pipeline's warmed masker."""
    global _output_masker
    if _output_masker is None:
        from app.guardrails.pipeline import get_guardrails_pipeline

        masker = get_guardrails_pipeline().get_phi_masker()
        _output_masker = OutputMasker(masker, get_guardrails_config())
        logger.info(
            "OutputMasker ready (masking=%s, active=%s, fail_closed=%s)",
            get_guardrails_config().output_masking_enabled,
            _output_masker._can_mask,
            get_guardrails_config().output_mask_fail_closed,
        )
    return _output_masker
