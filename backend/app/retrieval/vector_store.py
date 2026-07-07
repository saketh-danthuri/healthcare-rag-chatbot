"""
vector_store.py - Local ChromaDB Vector Store
==============================================
WHY: Replaces Azure AI Search with a local, on-disk ChromaDB collection.
     One place owns the client + collection so ingestion (writes) and
     retrieval (reads) agree on the persist directory, collection name, and
     distance metric.

The collection is persisted under `settings.chroma_persist_dir` so ingested
documents survive restarts. Distance metric is cosine to match the
L2-normalized embeddings from local_embeddings.py.
"""

import logging
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.ClientAPI:
    """Persistent ChromaDB client (cached per process)."""
    settings = get_settings()
    return chromadb.PersistentClient(
        path=settings.chroma_persist_dir,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_collection() -> chromadb.Collection:
    """Get-or-create the runbooks collection (cosine space)."""
    settings = get_settings()
    return get_chroma_client().get_or_create_collection(
        name=settings.chroma_collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def count_documents() -> int:
    """Number of chunks currently indexed (0 if the store is empty/unreachable)."""
    try:
        return get_collection().count()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not count Chroma documents: {e}")
        return 0
