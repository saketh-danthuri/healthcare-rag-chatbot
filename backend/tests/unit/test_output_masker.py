"""Unit tests for OutputMasker: sentence-buffered, role-gated PHI masking.

The critical property: an entity split across streamed tokens must NEVER be
emitted raw for a "general" user. We drive the masker with a fake PhiPiiMasker
so assertions are deterministic and do not depend on Presidio.
"""

import pytest
from app.config.guardrails_config import GuardrailsConfig
from app.guardrails.models import GuardrailAction, GuardrailResult
from app.guardrails.output_masker import OutputMasker

_SSN = "123-45-6789"


class FakeMasker:
    """Masks a known SSN only when a unit contains the WHOLE value."""

    def __init__(self, active: bool = True) -> None:
        self._active = active

    @property
    def is_active(self) -> bool:
        return self._active

    def check(self, message: str) -> GuardrailResult:
        if _SSN in message:
            return GuardrailResult(
                guardrail_name="fake",
                action=GuardrailAction.TRANSFORM,
                passed=True,
                transformed_message=message.replace(_SSN, "<US_SSN>"),
            )
        return GuardrailResult(
            guardrail_name="fake", action=GuardrailAction.PASS, passed=True
        )


def _config(**overrides) -> GuardrailsConfig:
    base = {"output_masking_enabled": True, "output_mask_fail_closed": True}
    base.update(overrides)
    return GuardrailsConfig(**base)


async def _collect(masker: OutputMasker, tokens: list[str], role: str) -> list[str]:
    async def gen():
        for token in tokens:
            yield token

    return [unit async for unit in masker.stream_masked(gen(), role)]


# SSN straddles the boundary between token 1 and token 2.
_SPLIT_TOKENS = ["Patient SSN is 123-45-", "6789. Done."]


@pytest.mark.asyncio
async def test_general_masks_entity_split_across_tokens():
    masker = OutputMasker(FakeMasker(), _config())
    units = await _collect(masker, _SPLIT_TOKENS, "general")

    joined = "".join(units)
    assert _SSN not in joined  # raw SSN never crosses the wire
    assert "<US_SSN>" in joined
    # And no individual emitted delta leaks the raw value either.
    assert all(_SSN not in unit for unit in units)


@pytest.mark.asyncio
async def test_clinician_sees_raw_value():
    masker = OutputMasker(FakeMasker(), _config())
    units = await _collect(masker, _SPLIT_TOKENS, "clinician")
    assert _SSN in "".join(units)


@pytest.mark.asyncio
async def test_fail_closed_withholds_when_masker_inactive():
    masker = OutputMasker(
        FakeMasker(active=False), _config(output_mask_fail_closed=True)
    )
    units = await _collect(masker, _SPLIT_TOKENS, "general")

    joined = "".join(units)
    assert _SSN not in joined
    assert units == ["⟨output withheld: PHI masking unavailable⟩"]


@pytest.mark.asyncio
async def test_fail_open_passes_through_when_configured():
    masker = OutputMasker(
        FakeMasker(active=False), _config(output_mask_fail_closed=False)
    )
    units = await _collect(masker, _SPLIT_TOKENS, "general")
    assert _SSN in "".join(units)


@pytest.mark.asyncio
async def test_masking_disabled_passes_through_for_general():
    masker = OutputMasker(FakeMasker(), _config(output_masking_enabled=False))
    units = await _collect(masker, _SPLIT_TOKENS, "general")
    assert _SSN in "".join(units)


@pytest.mark.asyncio
async def test_trailing_buffer_is_flushed():
    masker = OutputMasker(FakeMasker(), _config())
    units = await _collect(masker, ["no terminator here"], "general")
    assert "".join(units) == "no terminator here"


@pytest.mark.asyncio
async def test_mask_text_whole_string_for_rehydration():
    masker = OutputMasker(FakeMasker(), _config())
    assert masker.mask_text(f"SSN {_SSN}.", "general") == "SSN <US_SSN>."
    assert masker.mask_text(f"SSN {_SSN}.", "clinician") == f"SSN {_SSN}."
