"""
topic_scope_filter.py - Healthcare Operations Topic/Scope Filter (Guardrail 7)
================================================================================
WHY: The chatbot is scoped to healthcare operations (runbook troubleshooting,
     claims processing, COPS team workflows). Off-topic queries waste LLM tokens
     and may expose unintended behavior. This guardrail keeps the bot on-domain.

APPROACH: Cosine similarity between the user message embedding and a set of
     reference phrases that define the healthcare operations domain. If the
     maximum similarity falls below the threshold, the query is out-of-scope.

WHY cosine similarity (not a fine-tuned classifier):
  - No labeled training data needed
  - Fully configurable by changing reference phrases in env/config
  - Transparent and auditable
  - Works immediately with zero training time

LIBRARY: sentence-transformers (already installed for re-ranking).
     Model: all-MiniLM-L6-v2 (80MB, 384-dim, ~5ms CPU inference per query).
     Reference phrase embeddings pre-computed at init time (cached in memory).

GRACEFUL DEGRADATION: If sentence-transformers fails to load, sets
self._bypass = True. Pipeline continues without topic filtering.
"""

import logging

import numpy as np

from app.config.guardrails_config import GuardrailsConfig
from app.guardrails.models import GuardrailAction, GuardrailResult, ViolationSeverity

logger = logging.getLogger(__name__)


class TopicScopeFilter:
    """Healthcare operations domain scope filter using semantic similarity."""

    name = "topic_scope_filter"

    def __init__(self, config: GuardrailsConfig) -> None:
        self._config = config
        self._bypass = False
        self._model = None
        self._reference_embeddings: np.ndarray | None = None
        self._reference_phrases: list[str] = []

        if not config.topic_filter_enabled:
            self._bypass = True
            return

        if not config.topic_reference_phrases:
            logger.warning("Topic filter has no reference phrases configured. Bypassing.")
            self._bypass = True
            return

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(config.topic_embedding_model)
            self._reference_phrases = list(config.topic_reference_phrases)

            # Pre-compute and L2-normalize reference embeddings (done once at startup)
            raw = self._model.encode(self._reference_phrases, convert_to_numpy=True)
            norms = np.linalg.norm(raw, axis=1, keepdims=True)
            self._reference_embeddings = raw / np.maximum(norms, 1e-10)

            logger.info(
                f"Topic scope filter initialized: model={config.topic_embedding_model}, "
                f"{len(self._reference_phrases)} reference phrases, "
                f"threshold={config.topic_similarity_threshold}"
            )

        except ImportError:
            logger.warning(
                "sentence-transformers not available. Topic scope filter disabled."
            )
            self._bypass = True
        except Exception as e:
            logger.warning(f"Topic scope filter failed to initialize: {e}. Bypassing.")
            self._bypass = True

    def check(self, message: str) -> GuardrailResult:
        """Compute cosine similarity of message against healthcare domain reference phrases."""
        if self._bypass or self._model is None or self._reference_embeddings is None:
            return self._pass()

        try:
            # Encode message and L2-normalize
            msg_vec = self._model.encode([message], convert_to_numpy=True)[0]
            norm = np.linalg.norm(msg_vec)
            if norm > 1e-10:
                msg_vec = msg_vec / norm

            # Cosine similarity = dot product of normalized vectors
            similarities = self._reference_embeddings @ msg_vec
            max_sim = float(np.max(similarities))
            best_idx = int(np.argmax(similarities))
            closest_phrase = self._reference_phrases[best_idx]

            if max_sim >= self._config.topic_similarity_threshold:
                return GuardrailResult(
                    guardrail_name=self.name,
                    action=GuardrailAction.PASS,
                    passed=True,
                    detail=f"Query is within healthcare operations scope (similarity: {max_sim:.3f}).",
                    metadata={
                        "max_similarity": max_sim,
                        "threshold": self._config.topic_similarity_threshold,
                        "closest_reference": closest_phrase,
                    },
                )

            # Out-of-scope
            action = (
                GuardrailAction.BLOCK
                if self._config.topic_block_action == "block"
                else GuardrailAction.WARN
            )

            return GuardrailResult(
                guardrail_name=self.name,
                action=action,
                passed=action == GuardrailAction.WARN,
                violation_code="OUT_OF_SCOPE",
                severity=ViolationSeverity.LOW,
                detail=(
                    f"Query does not appear to be related to healthcare operations "
                    f"(similarity: {max_sim:.3f}, threshold: {self._config.topic_similarity_threshold}). "
                    "This assistant is scoped to healthcare claims operations, runbooks, and related workflows."
                ),
                metadata={
                    "max_similarity": max_sim,
                    "threshold": self._config.topic_similarity_threshold,
                    "closest_reference": closest_phrase,
                    "all_similarities": {
                        phrase: float(sim)
                        for phrase, sim in zip(self._reference_phrases, similarities.tolist())
                    },
                },
            )

        except Exception as e:
            logger.warning(f"Topic scope filter error during check: {e}. Passing through.")
            return self._pass()

    def _pass(self) -> GuardrailResult:
        return GuardrailResult(
            guardrail_name=self.name,
            action=GuardrailAction.PASS,
            passed=True,
            detail="Topic scope check passed (or bypassed).",
        )
