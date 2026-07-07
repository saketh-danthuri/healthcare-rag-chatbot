"""
embedder.py - Embedding & Local ChromaDB Indexing
===================================================
WHY: After chunking, each chunk needs to be converted to a vector (embedding)
     and stored in the local ChromaDB collection for hybrid retrieval. This
     module handles:
     1. Generating embeddings with a local sentence-transformers model
     2. Upserting chunks (vector + content + metadata) into ChromaDB

WHY local embeddings (not Azure):
  - Runs entirely on-device, no API key or network needed
  - all-MiniLM-L6-v2 is small (384-dim), fast on CPU, and already cached
  - Deterministic and free
"""

import logging
import re

from app.config.settings import get_settings
from app.ingestion.chunker import Chunk
from app.retrieval.local_embeddings import embed_texts
from app.retrieval.vector_store import get_collection

logger = logging.getLogger(__name__)

# Batch size for Chroma upserts (keeps memory bounded on large ingests).
UPSERT_BATCH_SIZE = 200


def _sanitize_key(raw_key: str) -> str:
    """Sanitize a string for use as a Chroma document id: [A-Za-z0-9_-] only."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw_key)


def generate_embeddings(texts: list[str], client=None) -> list[list[float]]:
    """Generate embeddings for a list of texts using the local model.

    The ``client`` argument is accepted for backwards compatibility with older
    callers but is ignored - embeddings are always produced on-device.
    """
    return embed_texts(texts)


def _clean_metadata(metadata: dict) -> dict:
    """Coerce chunk metadata into Chroma-safe scalars (str/int/float/bool).

    Chroma rejects None and nested values, so we normalize everything and drop
    empties to keep the store tidy.
    """
    cleaned: dict = {}
    for key in (
        "source_file",
        "doc_type",
        "job_id",
        "section",
        "folder",
        "source_path",
        "file_type",
    ):
        value = metadata.get(key)
        if value:
            cleaned[key] = str(value)

    for key in ("page_number", "chunk_index"):
        value = metadata.get(key)
        cleaned[key] = int(value) if value else 0

    return cleaned


def index_chunks(chunks: list[Chunk]) -> int:
    """Embed and index all chunks into the local ChromaDB collection.

    Uses upsert so re-running ingestion updates existing chunks in place
    (keyed by chunk_id) instead of creating duplicates.
    """
    if not chunks:
        logger.warning("No chunks to index")
        return 0

    # Deduplicate chunks by chunk_id (same doc can appear in Files and Files_1)
    seen_ids = set()
    unique_chunks = []
    for chunk in chunks:
        if chunk.chunk_id not in seen_ids:
            seen_ids.add(chunk.chunk_id)
            unique_chunks.append(chunk)
    if len(unique_chunks) < len(chunks):
        logger.info(
            f"Deduplicated: {len(chunks)} -> {len(unique_chunks)} chunks "
            f"({len(chunks) - len(unique_chunks)} duplicates removed)"
        )
    chunks = unique_chunks

    collection = get_collection()
    total_indexed = 0

    for i in range(0, len(chunks), UPSERT_BATCH_SIZE):
        batch = chunks[i : i + UPSERT_BATCH_SIZE]
        batch_num = i // UPSERT_BATCH_SIZE + 1

        texts = [c.content for c in batch]
        logger.info(f"Embedding batch {batch_num} ({len(batch)} chunks)...")
        embeddings = embed_texts(texts)

        ids = [_sanitize_key(c.chunk_id) for c in batch]
        documents = [c.content for c in batch]
        metadatas = [_clean_metadata(c.metadata) for c in batch]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        total_indexed += len(batch)
        logger.debug(f"Upserted batch {batch_num}: {total_indexed}/{len(chunks)}")

    logger.info(f"Indexed {total_indexed} chunks into ChromaDB")
    return total_indexed


def run_full_ingestion(docs_path: str | None = None) -> dict:
    """Run the complete ingestion pipeline: load -> chunk -> embed -> index.

    This is the top-level function you call to ingest all documents.
    Can be triggered via API endpoint or CLI.

    Returns:
        Dict with ingestion statistics
    """
    from app.ingestion.chunker import chunk_all_documents
    from app.ingestion.loader import load_all_documents

    settings = get_settings()
    path = docs_path or settings.docs_base_path

    # Step 1: Load documents from all formats
    logger.info(f"Step 1/3: Loading documents from {path}")
    documents = load_all_documents(path)

    # Step 2: Chunk documents
    logger.info("Step 2/3: Chunking documents")
    chunks = chunk_all_documents(documents)

    # Step 3: Embed and index
    logger.info("Step 3/3: Embedding and indexing chunks")
    indexed_count = index_chunks(chunks)

    stats = {
        "documents_loaded": len(documents),
        "chunks_created": len(chunks),
        "chunks_indexed": indexed_count,
        "docs_path": str(path),
    }

    logger.info(f"Ingestion complete: {stats}")
    return stats
