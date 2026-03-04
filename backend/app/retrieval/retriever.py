"""
retriever.py - RAG Retrieval Orchestrator
===========================================
WHY: This module ties together hybrid search + re-ranking into a single
     `retrieve()` function that the agent calls. It also formats the results
     into a context string with citations that gets injected into the LLM prompt.

PIPELINE:
  User Query
    -> Azure AI Search hybrid (vector + BM25 + RRF in one call) -> 10 candidates
    -> Cross-Encoder Re-ranking -> 5 best results
    -> Format as context string with [Source: ...] citations
    -> Return to agent/LLM
"""

import logging

from app.retrieval.hybrid_search import SearchResult, hybrid_search
from app.retrieval.reranker import rerank

logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    top_k: int = 5,
    filter_metadata: dict | None = None,
    use_reranker: bool = True,
) -> list[SearchResult]:
    """Retrieve the most relevant document chunks for a query.

    This is the main function the agent calls. Full pipeline:
    1. Azure AI Search hybrid search -> 10 candidates
    2. Cross-encoder re-ranking -> top_k results
    3. Return with scores and metadata

    Args:
        query: User's question or search query
        top_k: Number of final results to return
        filter_metadata: Optional filters (e.g., {"doc_type": "runbook"})
        use_reranker: Whether to apply cross-encoder re-ranking

    Returns:
        List of SearchResult objects, scored and sorted by relevance
    """
    # Step 1: Hybrid search via Azure AI Search (vector + BM25 + RRF)
    candidates = hybrid_search(
        query=query,
        top_k=20,  # Nearest neighbors for vector search
        final_k=10,  # Results after RRF fusion
        filter_metadata=filter_metadata,
    )

    if not candidates:
        logger.warning(f"No results found for query: {query[:100]}")
        return []

    # Step 2: Re-rank with cross-encoder
    if use_reranker and len(candidates) > 1:
        results = rerank(query, candidates, top_k=top_k)
    else:
        results = candidates[:top_k]

    logger.info(
        f"Retrieved {len(results)} results for: {query[:80]}... "
        f"(top score: {results[0].score:.3f})"
    )

    return results


def format_context_for_llm(results: list[SearchResult]) -> str:
    """Format search results into a context string for the LLM prompt.

    WHY this format: The LLM needs to know:
    1. The actual content from the runbook
    2. Which file it came from (for citations)
    3. Which section it's from (Purpose, Failure Instructions, etc.)

    The numbered format makes it easy for the LLM to reference specific
    chunks in its response: "According to [Source 1: ATL101Y, Failure Instructions]..."
    """
    if not results:
        return "No relevant documents found."

    context_parts = []

    for i, result in enumerate(results, 1):
        source_file = result.metadata.get("source_file", "Unknown")
        section = result.metadata.get("section", "General")
        job_id = result.metadata.get("job_id", "")
        page = result.metadata.get("page_number", "")

        # Build a clean source citation
        source_label = f"{source_file}"
        if job_id:
            source_label = f"{job_id} - {source_file}"

        context_parts.append(
            f"--- Source {i}: [{source_label}, Section: {section}"
            f"{f', Page {page}' if page else ''}] ---\n"
            f"{result.content}\n"
        )

    return "\n".join(context_parts)


def search_and_format(
    query: str,
    top_k: int = 5,
    filter_metadata: dict | None = None,
) -> tuple[str, list[dict]]:
    """Convenience function: retrieve + format in one call.

    Returns both the formatted context string (for the LLM) and the raw
    citations list (for the frontend citation panel).

    Returns:
        Tuple of (context_string, citations_list)
    """
    results = retrieve(query, top_k, filter_metadata)
    context = format_context_for_llm(results)

    # Build citations for the frontend
    citations = []
    for i, result in enumerate(results, 1):
        citations.append(
            {
                "index": i,
                "source_file": result.metadata.get("source_file", "Unknown"),
                "section": result.metadata.get("section", "General"),
                "job_id": result.metadata.get("job_id", ""),
                "page_number": result.metadata.get("page_number", ""),
                "score": round(result.score, 3),
                "snippet": result.content[:200] + "..."
                if len(result.content) > 200
                else result.content,
            }
        )

    return context, citations
