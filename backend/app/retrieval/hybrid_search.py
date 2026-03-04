"""
hybrid_search.py - Azure AI Search Hybrid Search
===================================================
WHY HYBRID SEARCH:
  Semantic search alone misses exact keyword matches. If someone asks about
  "CFT303A", pure semantic search might return chunks about similar-sounding
  but different jobs. BM25 keyword search catches exact matches.

  Azure AI Search handles this natively in a single API call:
  1. Vector search (cosine similarity on content_vector field)
  2. BM25 keyword search (full-text search on content field via en.lucene analyzer)
  3. Reciprocal Rank Fusion (RRF) - merges and re-ranks both result sets

  This replaces the previous ChromaDB + in-memory BM25 + manual RRF approach
  with one SDK call, dramatically simplifying the pipeline.
"""

import logging
from dataclasses import dataclass

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config.settings import get_settings
from app.ingestion.embedder import generate_embeddings, get_openai_client

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result with score and full metadata.

    WHY this structure: The retriever, re-ranker, and citation system all
    need access to the content, score, and source metadata. Having a clean
    dataclass keeps the pipeline type-safe.
    """

    content: str
    score: float
    metadata: dict
    chunk_id: str
    source: str  # always "hybrid" with Azure AI Search


def get_search_client() -> SearchClient:
    """Create an Azure AI Search client configured from settings."""
    settings = get_settings()
    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=AzureKeyCredential(settings.azure_search_api_key),
    )


def _build_odata_filter(filter_metadata: dict | None = None) -> str | None:
    """Convert a metadata filter dict to an OData filter expression.

    Examples:
        {"doc_type": "runbook"} -> "doc_type eq 'runbook'"
        {"doc_type": "runbook", "job_id": "CFT303A"} -> "doc_type eq 'runbook' and job_id eq 'CFT303A'"
    """
    if not filter_metadata:
        return None

    clauses = []
    for key, value in filter_metadata.items():
        if isinstance(value, str):
            clauses.append(f"{key} eq '{value}'")
        elif isinstance(value, int | float):
            clauses.append(f"{key} eq {value}")
        elif isinstance(value, bool):
            clauses.append(f"{key} eq {'true' if value else 'false'}")

    return " and ".join(clauses) if clauses else None


def hybrid_search(
    query: str,
    top_k: int = 20,
    final_k: int = 10,
    filter_metadata: dict | None = None,
) -> list[SearchResult]:
    """Run hybrid search: semantic + BM25 + RRF via Azure AI Search.

    This is the main search function used by the retriever. Azure AI Search
    does vector search, BM25, and Reciprocal Rank Fusion in a single API call.

    Args:
        query: User's search query
        top_k: How many nearest neighbors for vector search
        final_k: How many final results to return after fusion
        filter_metadata: Optional metadata filters (e.g., {"doc_type": "runbook"})

    Returns:
        Top final_k SearchResult objects from hybrid search
    """
    search_client = get_search_client()

    # Generate query embedding for vector search
    openai_client = get_openai_client()
    query_embedding = generate_embeddings([query], openai_client)[0]

    # Build OData filter if provided
    odata_filter = _build_odata_filter(filter_metadata)

    # Single API call: Azure AI Search does vector + BM25 + RRF internally
    results = search_client.search(
        search_text=query,  # Native BM25 full-text search
        vector_queries=[
            VectorizedQuery(
                vector=query_embedding,
                k_nearest_neighbors=top_k,
                fields="content_vector",
            )
        ],
        top=final_k,  # Azure does RRF internally and returns top results
        filter=odata_filter,
        select=[
            "chunk_id",
            "content",
            "source_file",
            "doc_type",
            "job_id",
            "section",
            "page_number",
            "folder",
            "source_path",
            "file_type",
            "chunk_index",
        ],
    )

    search_results = []
    for result in results:
        # Build metadata dict from Azure Search fields
        metadata = {
            "source_file": result.get("source_file", "Unknown"),
            "doc_type": result.get("doc_type", ""),
            "job_id": result.get("job_id", ""),
            "section": result.get("section", ""),
            "page_number": result.get("page_number", ""),
            "folder": result.get("folder", ""),
            "source_path": result.get("source_path", ""),
            "file_type": result.get("file_type", ""),
            "chunk_index": result.get("chunk_index", 0),
        }

        search_results.append(
            SearchResult(
                content=result["content"],
                score=result["@search.score"],
                metadata=metadata,
                chunk_id=result["chunk_id"],
                source="hybrid",
            )
        )

    logger.debug(f"Azure AI Search returned {len(search_results)} hybrid results")
    return search_results
