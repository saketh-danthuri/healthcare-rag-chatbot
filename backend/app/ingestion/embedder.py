"""
embedder.py - Embedding & Azure AI Search Indexing
=====================================================
WHY: After chunking, each chunk needs to be converted to a vector (embedding)
     and stored in Azure AI Search for hybrid retrieval. This module handles:
     1. Generating embeddings via Azure OpenAI's text-embedding-3-small model
     2. Uploading chunks into Azure AI Search with their vectors and metadata
     3. Managing the search index schema

WHY Azure OpenAI embeddings (not local):
  - text-embedding-3-small is cheap ($0.02/1M tokens)
  - 1536 dimensions, excellent for retrieval
  - Consistent quality vs. local models that vary by hardware
  - ~160 docs = ~5000 chunks = ~2M tokens = ~$0.04 total cost to embed everything
"""

import logging
import re
import time

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from openai import AzureOpenAI

from app.config.settings import get_settings
from app.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)

# Batch size for embedding API calls
# WHY 50 (not 100): Azure free tier has aggressive rate limits (~60K tokens/min).
# Smaller batches with a short delay between them avoids 429 errors.
EMBEDDING_BATCH_SIZE = 50
EMBEDDING_DELAY_SECONDS = 2  # Pause between batches to respect rate limits

# Batch size for Azure Search uploads (max 1000 per batch)
# Using 100 to avoid SSL connection drops on long uploads
SEARCH_UPLOAD_BATCH_SIZE = 100
SEARCH_UPLOAD_DELAY_SECONDS = 1  # Small delay between upload batches


def get_openai_client() -> AzureOpenAI:
    """Create an Azure OpenAI client configured from settings."""
    settings = get_settings()
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def get_search_client() -> SearchClient:
    """Create an Azure AI Search client configured from settings."""
    settings = get_settings()
    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


def get_search_index_client() -> SearchIndexClient:
    """Create an Azure AI Search index management client."""
    settings = get_settings()
    return SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


def _sanitize_key(raw_key: str) -> str:
    """Sanitize a string for use as an Azure Search document key.

    Azure Search keys must be URL-safe: [A-Za-z0-9_-] only.
    We replace any disallowed character with an underscore.
    """
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw_key)


def generate_embeddings(
    texts: list[str],
    client: AzureOpenAI | None = None,
) -> list[list[float]]:
    """Generate embeddings for a list of texts using Azure OpenAI.

    Batches requests to stay within API limits and adds retry logic.

    Args:
        texts: List of text strings to embed
        client: Optional pre-configured OpenAI client

    Returns:
        List of embedding vectors (each is a list of 1536 floats)
    """
    if not client:
        client = get_openai_client()

    settings = get_settings()
    all_embeddings = []

    total_batches = (len(texts) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE

    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        batch_num = i // EMBEDDING_BATCH_SIZE + 1
        logger.info(f"Embedding batch {batch_num}/{total_batches} ({len(batch)} texts)")

        response = client.embeddings.create(
            input=batch,
            model=settings.azure_openai_embedding_deployment,
        )

        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

        # Rate limit delay between batches (Azure free tier is strict)
        if batch_num < total_batches:
            time.sleep(EMBEDDING_DELAY_SECONDS)

    return all_embeddings


def index_chunks(
    chunks: list[Chunk],
    search_client: SearchClient | None = None,
    openai_client: AzureOpenAI | None = None,
) -> int:
    """Embed and index all chunks into Azure AI Search.

    This is the main function called during ingestion. It:
    1. Generates embeddings for all chunk contents
    2. Uploads documents to Azure AI Search (merge_or_upload = upsert)
    3. Returns the number of chunks indexed

    WHY merge_or_upload: If you re-run ingestion after adding new docs,
    existing chunks are updated in place instead of creating duplicates.
    The chunk_id ensures idempotency.
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

    if not search_client:
        search_client = get_search_client()

    if not openai_client:
        openai_client = get_openai_client()

    # Extract texts for embedding
    texts = [chunk.content for chunk in chunks]

    # Generate embeddings
    logger.info(f"Generating embeddings for {len(texts)} chunks...")
    embeddings = generate_embeddings(texts, openai_client)

    # Prepare documents for Azure AI Search upload
    documents = []
    for chunk, embedding in zip(chunks, embeddings):
        # Azure Search keys must be URL-safe
        safe_key = _sanitize_key(chunk.chunk_id)

        doc = {
            "chunk_id": safe_key,
            "content": chunk.content,
            "content_vector": embedding,
            "source_file": str(chunk.metadata.get("source_file", "")),
            "doc_type": str(chunk.metadata.get("doc_type", "")),
            "job_id": str(chunk.metadata.get("job_id", "")),
            "section": str(chunk.metadata.get("section", "")),
            "page_number": int(chunk.metadata.get("page_number", 0))
            if chunk.metadata.get("page_number")
            else 0,
            "folder": str(chunk.metadata.get("folder", "")),
            "source_path": str(chunk.metadata.get("source_path", "")),
            "file_type": str(chunk.metadata.get("file_type", "")),
            "chunk_index": int(chunk.metadata.get("chunk_index", 0))
            if chunk.metadata.get("chunk_index")
            else 0,
        }
        documents.append(doc)

    # Upload in batches with retry logic
    total_indexed = 0
    for i in range(0, len(documents), SEARCH_UPLOAD_BATCH_SIZE):
        batch = documents[i : i + SEARCH_UPLOAD_BATCH_SIZE]
        batch_num = i // SEARCH_UPLOAD_BATCH_SIZE + 1

        # Retry up to 3 times per batch
        for attempt in range(3):
            try:
                result = search_client.merge_or_upload_documents(documents=batch)
                succeeded = sum(1 for r in result if r.succeeded)
                total_indexed += succeeded
                logger.debug(
                    f"Indexed batch {batch_num}: {total_indexed}/{len(documents)} ({succeeded} succeeded)"
                )
                break
            except Exception as e:
                if attempt < 2:
                    logger.warning(
                        f"Upload batch {batch_num} failed (attempt {attempt + 1}/3): {e}. Retrying..."
                    )
                    time.sleep(SEARCH_UPLOAD_DELAY_SECONDS * (attempt + 1))
                else:
                    logger.error(
                        f"Upload batch {batch_num} failed after 3 attempts: {e}"
                    )

        # Small delay between batches to avoid connection issues
        if i + SEARCH_UPLOAD_BATCH_SIZE < len(documents):
            time.sleep(SEARCH_UPLOAD_DELAY_SECONDS)

    logger.info(f"Indexed {total_indexed} chunks into Azure AI Search")
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
