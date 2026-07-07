"""
local_ragas.py - Local Embeddings adapter for RAGAS
===================================================
RAGAS expects a LangChain ``Embeddings`` object. This thin adapter routes both
document and query embedding through our on-device sentence-transformers model
so the quality gate runs with no cloud dependency.
"""

from langchain_core.embeddings import Embeddings

from app.retrieval.local_embeddings import embed_texts


class LocalEmbeddings(Embeddings):
    """LangChain Embeddings backed by local sentence-transformers."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(list(texts))

    def embed_query(self, text: str) -> list[float]:
        return embed_texts([text])[0]
