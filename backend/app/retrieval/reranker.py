"""
reranker.py - Cross-Encoder Re-ranking
========================================
WHY RE-RANKING:
  Hybrid search gives us ~10 candidates, but the order isn't perfect.
  Embedding-based search uses bi-encoders (encode query and doc separately),
  which are fast but miss fine-grained relevance signals.

  Cross-encoders see the query AND document TOGETHER, allowing them to
  capture nuanced interactions like:
  - "CFT303A not started" matches "If CFT303A has not completed by 3 AM"
  - Understanding that "CLMU load stuck" is about the same thing as
    "claims processing delay"

  The tradeoff: cross-encoders are ~100x slower than bi-encoders. That's
  why we only re-rank the top 10 candidates (not the whole corpus).

MODEL CHOICE:
  ms-marco-MiniLM-L-6-v2: A distilled cross-encoder that runs locally
  on CPU in ~50ms for 10 documents. No API cost, no network latency.
  Trained on MS MARCO passage ranking dataset.
"""

import logging

from app.retrieval.hybrid_search import SearchResult

logger = logging.getLogger(__name__)

# Lazy-loaded model (only loaded on first use to speed up startup)
_reranker_model = None


def _get_reranker_model():
    """Lazy-load the cross-encoder model.

    WHY lazy loading: The model takes ~2 seconds to load from disk.
    We don't want this to slow down app startup. Instead, it loads
    on the first search request and stays in memory for subsequent requests.
    """
    global _reranker_model

    if _reranker_model is None:
        from sentence_transformers import CrossEncoder

        logger.info("Loading cross-encoder re-ranker model...")
        _reranker_model = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            max_length=512,  # Truncate long docs to 512 tokens
        )
        logger.info("Cross-encoder model loaded successfully")

    return _reranker_model


def rerank(
    query: str,
    results: list[SearchResult],
    top_k: int = 5,
) -> list[SearchResult]:
    """Re-rank search results using a cross-encoder model.

    Takes the hybrid search results and re-scores each one by how relevant
    it truly is to the query. Returns the top_k most relevant results.

    Args:
        query: The user's search query
        results: List of SearchResult objects from hybrid search
        top_k: Number of top results to return after re-ranking

    Returns:
        Re-ranked list of top_k SearchResult objects
    """
    if not results:
        return []

    if len(results) <= 1:
        return results

    model = _get_reranker_model()

    # Create query-document pairs for the cross-encoder
    pairs = [(query, result.content) for result in results]

    # Score all pairs
    scores = model.predict(pairs)

    # Attach cross-encoder scores to results
    scored_results = []
    for result, ce_score in zip(results, scores):
        scored_results.append(
            SearchResult(
                content=result.content,
                score=float(ce_score),  # Replace hybrid score with CE score
                metadata=result.metadata,
                chunk_id=result.chunk_id,
                source="reranked",
            )
        )

    # Sort by cross-encoder score (descending)
    scored_results.sort(key=lambda x: x.score, reverse=True)

    logger.debug(
        f"Re-ranked {len(results)} results. "
        f"Top score: {scored_results[0].score:.3f}, "
        f"Bottom score: {scored_results[-1].score:.3f}"
    )

    return scored_results[:top_k]
