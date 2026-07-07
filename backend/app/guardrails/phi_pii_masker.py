"""
phi_pii_masker.py - PHI/PII Detection and Masking (Guardrail 5)
================================================================
WHY: HIPAA and general data privacy require that Protected Health Information
     (PHI) and Personally Identifiable Information (PII) never leave the
     application boundary in plaintext. This guardrail masks sensitive data
     BEFORE the message reaches Azure OpenAI.

LIBRARY: Microsoft Presidio - the healthcare industry standard for PHI
     detection, used internally by Azure Health Data Services.
     presidio-analyzer detects entities, presidio-anonymizer replaces them.

MASKING STRATEGY: Replace with typed placeholders.
     Input:  "John Smith's SSN is 123-45-6789, his DOB is 01/15/1980"
     Output: "<PERSON>'s SSN is <US_SSN>, his DOB is <DATE_TIME>"

PHI-SAFE LOGGING: Violation log records ONLY entity types and count,
     never the actual values. message_preview in audit log is replaced
     with a redaction notice when PHI is detected.

INITIALIZATION: Most expensive guardrail (~2-3s for spaCy model load).
     Must run at app startup (lifespan hook), not on first request.

GRACEFUL DEGRADATION: If presidio or spaCy is not installed, sets
self._bypass = True and logs a WARNING with install instructions.
Pipeline continues without PHI masking.

DOCKERFILE REQUIRED:
     RUN python -m spacy download en_core_web_lg
"""

import logging

from app.config.guardrails_config import GuardrailsConfig
from app.guardrails.models import GuardrailAction, GuardrailResult, ViolationSeverity

logger = logging.getLogger(__name__)


class PhiPiiMasker:
    """PHI/PII detection and masking using Microsoft Presidio + spaCy."""

    name = "phi_pii_masker"

    def __init__(self, config: GuardrailsConfig) -> None:
        self._config = config
        self._bypass = False
        self._analyzer = None
        self._anonymizer = None

        if not config.phi_masking_enabled:
            self._bypass = True
            return

        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine

            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()

            # Load custom recognizers if a file path is configured
            if config.phi_custom_patterns_file:
                self._load_custom_recognizers(config.phi_custom_patterns_file)

            logger.info(
                f"PHI/PII masker initialized with {len(config.phi_entities_to_mask)} entity types: "
                f"{', '.join(config.phi_entities_to_mask)}"
            )

        except ImportError as e:
            logger.warning(
                f"Presidio not installed ({e}). PHI masking disabled. "
                "Run: pip install presidio-analyzer presidio-anonymizer && "
                "python -m spacy download en_core_web_lg"
            )
            self._bypass = True
        except OSError as e:
            # spaCy model not downloaded
            logger.warning(
                f"spaCy model not found ({e}). PHI masking disabled. "
                "Run: python -m spacy download en_core_web_lg"
            )
            self._bypass = True
        except Exception as e:
            logger.warning(f"PHI masker failed to initialize: {e}. Bypassing.")
            self._bypass = True

    @property
    def is_active(self) -> bool:
        """True if the masker can actually mask (Presidio/spaCy loaded).

        False when bypassed (masking disabled or Presidio/spaCy unavailable),
        which the output masker uses to decide fail-closed behavior.
        """
        return not self._bypass

    def check(self, message: str) -> GuardrailResult:
        """Detect and mask PHI/PII entities in the message.

        If PHI is found: action=TRANSFORM, transformed_message=masked text.
        If no PHI found: action=PASS, original message unchanged.
        """
        if self._bypass:
            return self._pass()

        try:
            analysis_results = self._analyzer.analyze(
                text=message,
                entities=self._config.phi_entities_to_mask,
                language=self._config.presidio_language,
            )

            if not analysis_results:
                return self._pass()

            # Mask detected entities
            anonymized = self._anonymizer.anonymize(
                text=message,
                analyzer_results=analysis_results,
            )
            masked_text = anonymized.text

            # Collect entity types for logging (NOT the actual values)
            entity_types = list({r.entity_type for r in analysis_results})
            entity_count = len(analysis_results)

            logger.info(
                f"PHI masking applied: {entity_count} entities masked "
                f"({', '.join(entity_types)})"
            )

            return GuardrailResult(
                guardrail_name=self.name,
                action=GuardrailAction.TRANSFORM,
                passed=True,  # Masking means we can proceed - just with clean data
                transformed_message=masked_text,
                violation_code="PHI_DETECTED",
                severity=ViolationSeverity.HIGH,
                detail=(
                    f"Masked {entity_count} PHI/PII entities: {', '.join(entity_types)}. "
                    "Message will be processed with sensitive data replaced by placeholders."
                ),
                metadata={
                    "entity_types": entity_types,
                    "entity_count": entity_count,
                    # Do NOT include actual values or positions in metadata
                },
            )

        except Exception as e:
            logger.warning(f"PHI masking encountered an error: {e}. Passing through.")
            return self._pass()

    def _load_custom_recognizers(self, yaml_path: str) -> None:
        """Load custom PatternRecognizer definitions from a YAML file.

        YAML format:
          recognizers:
            - name: MRN_RECOGNIZER
              supported_entity: MEDICAL_RECORD_NUMBER
              patterns:
                - name: mrn_pattern
                  regex: "MRN[:\\s]?\\d{6,10}"
                  score: 0.85
        """
        try:
            import yaml
            from presidio_analyzer import PatternRecognizer
            from presidio_analyzer.pattern import Pattern

            with open(yaml_path) as f:
                data = yaml.safe_load(f)

            for rec_def in data.get("recognizers", []):
                patterns = [
                    Pattern(
                        name=p["name"],
                        regex=p["regex"],
                        score=p.get("score", 0.8),
                    )
                    for p in rec_def.get("patterns", [])
                ]
                recognizer = PatternRecognizer(
                    supported_entity=rec_def["supported_entity"],
                    patterns=patterns,
                    name=rec_def.get("name", rec_def["supported_entity"]),
                )
                self._analyzer.registry.add_recognizer(recognizer)
                logger.info(f"Loaded custom recognizer: {rec_def['supported_entity']}")

        except Exception as e:
            logger.warning(
                f"Failed to load custom PHI recognizers from {yaml_path}: {e}"
            )

    def _pass(self) -> GuardrailResult:
        return GuardrailResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            passed=True,
            detail="No PHI/PII detected (or masking bypassed).",
        )
