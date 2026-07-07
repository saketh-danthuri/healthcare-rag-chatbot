"""
guardrails_config.py - Guardrails Thresholds and Feature Flags
================================================================
WHY separate from settings.py: Guardrail tuning (rate limits, thresholds,
     topic reference phrases) changes independently of core infrastructure
     settings (Azure endpoints, DB credentials). Keeping them separate lets
     security teams tune guardrails without touching production secrets.

All env vars use the GUARDRAIL_ prefix to prevent collisions with existing vars.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class GuardrailsConfig(BaseSettings):
    """Guardrails thresholds and feature flags, loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_prefix="GUARDRAIL_",
    )

    # --- Master switch ---
    enabled: bool = True

    # --- Per-guardrail feature flags ---
    input_validation_enabled: bool = True
    rate_limiting_enabled: bool = True
    cost_check_enabled: bool = True
    data_violation_enabled: bool = True
    phi_masking_enabled: bool = True
    injection_detection_enabled: bool = True
    topic_filter_enabled: bool = True

    # --- Input Validation ---
    max_newlines: int = 100  # Blocks newline-stuffed payloads
    max_urls: int = 10  # Blocks URL flooding (potential SSRF)
    max_repeated_chars: int = 50  # Blocks fuzzing / DoS via repeated chars

    # --- Rate Limiting ---
    rate_limit_per_user_per_minute: int = 20
    rate_limit_per_ip_per_minute: int = 60

    # --- Cost / Token Budget ---
    token_budget_per_request: int = 4096  # Max input tokens per single message
    token_budget_per_user_per_hour: int = 50000  # Rolling 1-hour budget per user
    token_budget_model: str = "gpt-4o-mini"  # tiktoken encoding to use

    # --- Data Violation ---
    blocked_keywords: list[str] = [
        "social security number",
        "credit card number",
        "cvv",
        "bank account number",
    ]
    content_policy_action: str = "block"  # "block" or "warn"

    # --- PHI / PII Masking ---
    presidio_language: str = "en"
    phi_entities_to_mask: list[str] = [
        "PERSON",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "US_SSN",
        "MEDICAL_LICENSE",
        "NRP",
        "LOCATION",
        "DATE_TIME",
        "IP_ADDRESS",
        "US_PASSPORT",
        "CREDIT_CARD",
        "IBAN_CODE",
        "US_BANK_NUMBER",
    ]
    phi_custom_patterns_file: str = ""  # Optional path to YAML with custom recognizers

    # --- Output PHI Masking (streamed assistant response) ---
    # The input pipeline masks the user's message for everyone. These flags govern
    # masking of the OUTPUT, which may surface PHI pulled from retrieved documents.
    # Masking is applied server-side per user role (clinician = unmasked,
    # general = masked) on every path that emits assistant text.
    output_masking_enabled: bool = True
    # Fail-closed: if Presidio/spaCy is unavailable, withhold raw output from
    # "general" users (emit a redaction notice) instead of leaking PHI.
    output_mask_fail_closed: bool = True
    # Redaction notice shown to "general" users when masking cannot run.
    output_mask_redaction_notice: str = "⟨output withheld: PHI masking unavailable⟩"

    # --- Prompt Injection ---
    injection_block_threshold: float = 0.85  # Score >= this -> BLOCK
    injection_warn_threshold: float = 0.60  # Score >= this -> WARN and continue
    injection_use_llm: bool = False  # Enable LLM-based second pass (slower)

    # --- Topic / Scope Filter ---
    topic_similarity_threshold: float = 0.20  # Min cosine sim to healthcare domain
    # Lowered from 0.35: short runbook queries like "What is CFT303E" score ~0.26
    # against the healthcare reference phrases and were being false-blocked.
    topic_embedding_model: str = "all-MiniLM-L6-v2"
    topic_block_action: str = "block"  # "block" or "warn"
    topic_reference_phrases: list[str] = [
        "healthcare claims operations job failure",
        "runbook procedure escalation troubleshooting",
        "healthcare operations batch job error",
        "claims processing pipeline failure",
        "medical billing operations issue",
        "ATL CFT RCR CLM batch job failure",
        "COPS team incident response runbook",
        "meeting transcript action items decisions",
        "operations team process documentation",
    ]


@lru_cache
def get_guardrails_config() -> GuardrailsConfig:
    """Singleton guardrails config - cached after first call."""
    return GuardrailsConfig()
