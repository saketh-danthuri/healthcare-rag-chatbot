"""
hybrid_search.py - Local Hybrid Search (Chroma + BM25 + RRF)
=============================================================
WHY HYBRID SEARCH:
  Semantic search alone misses exact keyword matches. If someone asks about
  "CFT303A", pure vector search might return chunks about similar-sounding but
  different jobs. BM25 keyword search catches exact matches.

Azure AI Search used to do vector + BM25 + RRF server-side in one call. Running
fully local, we reproduce that here:
  1. Vector search over a local ChromaDB collection (cosine on 384-dim
     sentence-transformers embeddings).
  2. BM25 keyword search (rank_bm25) over the same corpus, held in memory.
  3. Reciprocal Rank Fusion (RRF) merges the two ranked lists.

The corpus for BM25 is pulled from Chroma once per process and cached (keyed by
the collection's document count so a re-ingest is picked up).
"""

import logging
import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.retrieval.local_embeddings import embed_texts
from app.retrieval.vector_store import get_collection

logger = logging.getLogger(__name__)

# RRF constant: larger => flatter weighting across ranks. 60 is the common default.
RRF_K = 60


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
    source: str  # always "hybrid"


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokenizer for BM25 (also splits IDs like CFT303A)."""
    return re.findall(r"[a-z0-9]+", text.lower())


# --- In-memory BM25 corpus cache -------------------------------------------
# Cached tuple: (count, ids, documents, metadatas, BM25Okapi). Rebuilt when the
# collection's document count changes (e.g., after re-ingestion).
_bm25_cache: dict = {}


def _load_corpus() -> tuple[list[str], list[str], list[dict], BM25Okapi | None]:
    """Load all chunks from Chroma and build (or reuse) the BM25 index."""
    collection = get_collection()
    count = collection.count()

    cached = _bm25_cache.get("data")
    if cached is not None and _bm25_cache.get("count") == count:
        return cached

    if count == 0:
        empty: tuple = ([], [], [], None)
        _bm25_cache["count"] = 0
        _bm25_cache["data"] = empty
        return empty

    data = collection.get(include=["documents", "metadatas"])
    ids = data.get("ids", [])
    documents = data.get("documents", []) or []
    metadatas = data.get("metadatas", []) or [{} for _ in ids]

    tokenized = [_tokenize(doc) for doc in documents]
    bm25 = BM25Okapi(tokenized) if tokenized else None

    result = (ids, documents, metadatas, bm25)
    _bm25_cache["count"] = count
    _bm25_cache["data"] = result
    logger.info(f"Built BM25 index over {len(ids)} chunks")
    return result


def _matches_filter(metadata: dict, filter_metadata: dict | None) -> bool:
    """True if metadata satisfies every key/value in the filter."""
    if not filter_metadata:
        return True
    return all(str(metadata.get(k, "")) == str(v) for k, v in filter_metadata.items())


def hybrid_search(
    query: str,
    top_k: int = 20,
    final_k: int = 10,
    filter_metadata: dict | None = None,
) -> list[SearchResult]:
    """Run hybrid search: vector (Chroma) + BM25 + Reciprocal Rank Fusion.

    Args:
        query: User's search query
        top_k: How many candidates to pull from each of vector and BM25
        final_k: How many final results to return after fusion
        filter_metadata: Optional metadata filters (e.g., {"doc_type": "runbook"})

    Returns:
        Top final_k SearchResult objects from hybrid search
    """
    ids, documents, metadatas, bm25 = _load_corpus()
    if not ids:
        logger.warning("Vector store is empty - no documents indexed yet")
        return []

    # Map chunk_id -> (content, metadata) for assembling results.
    by_id = {cid: (documents[i], metadatas[i] or {}) for i, cid in enumerate(ids)}

    # --- 1. Vector search via Chroma ---
    query_embedding = embed_texts([query])[0]
    vector_ranked: list[str] = []
    try:
        vres = get_collection().query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, len(ids)),
        )
        vector_ranked = vres.get("ids", [[]])[0]
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Vector query failed: {e}")

    # --- 2. BM25 keyword search ---
    bm25_ranked: list[str] = []
    if bm25 is not None:
        scores = bm25.get_scores(_tokenize(query))
        ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        bm25_ranked = [ids[i] for i in ranked_idx[:top_k] if scores[i] > 0]

    # --- 3. Reciprocal Rank Fusion ---
    rrf: dict[str, float] = {}
    for ranked in (vector_ranked, bm25_ranked):
        for rank, cid in enumerate(ranked):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)

    fused = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)

    results: list[SearchResult] = []
    for cid, score in fused:
        if cid not in by_id:
            continue
        content, metadata = by_id[cid]
        if not _matches_filter(metadata, filter_metadata):
            continue
        results.append(
            SearchResult(
                content=content,
                score=float(score),
                metadata=dict(metadata),
                chunk_id=cid,
                source="hybrid",
            )
        )
        if len(results) >= final_k:
            break

    logger.debug(f"Hybrid search returned {len(results)} results")
    return results
