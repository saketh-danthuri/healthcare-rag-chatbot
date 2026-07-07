"""
local_embeddings.py - On-device Text Embeddings
================================================
WHY: Replaces Azure OpenAI's text-embedding-3-small with a local
     sentence-transformers model (all-MiniLM-L6-v2, 384-dim). Runs on CPU,
     needs no API key, and the model is already cached on this machine (the
     topic-scope guardrail uses the same one).

Embeddings are L2-normalized so cosine similarity == dot product, which lines
up with the Chroma collection's "cosine" space.
"""

import logging
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """Load (and cache) the sentence-transformers embedding model."""
    settings = get_settings()
    logger.info(f"Loading local embedding model: {settings.local_embedding_model}")
    return SentenceTransformer(settings.local_embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts into normalized vectors (list of floats)."""
    if not texts:
        return []
    model = get_embedding_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.tolist()
