"""
chunker.py - Section-Aware Document Chunker
=============================================
WHY: Raw documents are too large to embed as-is (embedding models have token
     limits, and large chunks dilute relevance). We need to split them into
     ~800 token chunks. But naive splitting (every N characters) breaks
     mid-sentence and loses context.

HOW THIS IS DIFFERENT:
  1. Runbooks have consistent sections (Purpose, General Info, Pre-Requisites,
     Job Steps, Failure Instructions). We split ON section boundaries first.
  2. If a section is still too large, we split on paragraph boundaries.
  3. Each chunk carries metadata about which section it came from - so the
     retriever can tell the LLM "this chunk is from the Failure Instructions
     section of ATL101Y".
  4. We add overlap between chunks so no information falls through the cracks.
"""

import logging
import re
from dataclasses import dataclass, field

from app.ingestion.loader import Document

logger = logging.getLogger(__name__)

# Default chunking parameters
DEFAULT_CHUNK_SIZE = 800  # tokens (roughly 4 chars per token)
DEFAULT_CHUNK_OVERLAP = 200  # tokens of overlap between chunks
CHARS_PER_TOKEN = 4  # rough estimate for English text

# Runbook section headers we look for (case-insensitive patterns)
SECTION_PATTERNS = [
    r"(?:^|\n)\s*\d+\.\s*Purpose",
    r"(?:^|\n)\s*\d+\.\s*General\s*Info",
    r"(?:^|\n)\s*\d+\.\s*Pre-?[Rr]equisites?",
    r"(?:^|\n)\s*\d+\.\s*Job\s*Steps?",
    r"(?:^|\n)\s*\d+\.\s*(?:Failure|Error)\s*(?:Instructions?|Procedures?)",
    r"(?:^|\n)\s*\d+\.\s*Escalation",
    r"(?:^|\n)\s*\d+\.\s*Recovery",
    r"(?:^|\n)#{1,3}\s+",  # Markdown headers
]


@dataclass
class Chunk:
    """A chunk of text ready for embedding, with full traceability metadata.

    WHY this structure:
    - content: the actual text to embed
    - metadata: everything needed to cite the source and filter during retrieval
    - chunk_id: unique identifier for deduplication in hybrid search
    """

    content: str
    metadata: dict = field(default_factory=dict)
    chunk_id: str = ""


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate. Good enough for chunking decisions."""
    return len(text) // CHARS_PER_TOKEN


def _identify_section(text: str) -> str:
    """Try to identify which runbook section a chunk belongs to.

    WHY: When the LLM cites "[Source: ATL101Y, Failure Instructions]",
    the ops team can immediately jump to the right section. Without this,
    they'd have to read the entire runbook to find the relevant part.
    """
    text_lower = text[:200].lower()  # Check only the beginning

    if "purpose" in text_lower:
        return "Purpose"
    if "general info" in text_lower:
        return "General Info"
    if "pre-requisite" in text_lower or "prerequisite" in text_lower:
        return "Pre-Requisites"
    if "job step" in text_lower:
        return "Job Steps"
    if "failure" in text_lower and (
        "instruction" in text_lower or "procedure" in text_lower
    ):
        return "Failure Instructions"
    if "escalation" in text_lower:
        return "Escalation"
    if "recovery" in text_lower:
        return "Recovery"

    return "General"


def _split_by_sections(text: str) -> list[tuple[str, str]]:
    """Split text on runbook section boundaries.

    Returns list of (section_name, section_text) tuples.
    If no sections are found (non-runbook docs), returns the full text
    as a single section.
    """
    # Build a combined regex to find all section boundaries
    combined_pattern = "|".join(SECTION_PATTERNS)
    splits = list(re.finditer(combined_pattern, text, re.IGNORECASE))

    if not splits:
        return [("General", text)]

    sections = []
    for i, match in enumerate(splits):
        start = match.start()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        section_text = text[start:end].strip()
        section_name = _identify_section(section_text)
        if section_text:
            sections.append((section_name, section_text))

    # Don't forget text before the first section header
    if splits[0].start() > 0:
        preamble = text[: splits[0].start()].strip()
        if preamble:
            sections.insert(0, ("Preamble", preamble))

    return sections


def _split_text_with_overlap(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into chunks of approximately chunk_size tokens with overlap.

    Strategy: Split on paragraph boundaries (double newline) first.
    If a paragraph is too long, split on sentence boundaries.
    If a sentence is too long, split on word boundaries.

    WHY overlap: Without overlap, a key fact at the boundary of two chunks
    might not appear fully in either chunk, making it unretrievable.
    200 tokens of overlap means ~50 words of context carry over.
    """
    max_chars = chunk_size * CHARS_PER_TOKEN
    overlap_chars = chunk_overlap * CHARS_PER_TOKEN

    # Split into paragraphs first
    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # If adding this paragraph would exceed chunk size
        if len(current_chunk) + len(para) + 1 > max_chars and current_chunk:
            chunks.append(current_chunk.strip())

            # Start new chunk with overlap from the end of the previous chunk
            if overlap_chars > 0 and len(current_chunk) > overlap_chars:
                current_chunk = current_chunk[-overlap_chars:] + "\n\n" + para
            else:
                current_chunk = para
        else:
            current_chunk = current_chunk + "\n\n" + para if current_chunk else para

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    # Handle case where a single paragraph is larger than chunk_size
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > max_chars * 1.5:
            # Split long chunk by sentences
            sentences = re.split(r"(?<=[.!?])\s+", chunk)
            sub_chunk = ""
            for sent in sentences:
                if len(sub_chunk) + len(sent) + 1 > max_chars and sub_chunk:
                    final_chunks.append(sub_chunk.strip())
                    sub_chunk = sent
                else:
                    sub_chunk = sub_chunk + " " + sent if sub_chunk else sent
            if sub_chunk.strip():
                final_chunks.append(sub_chunk.strip())
        else:
            final_chunks.append(chunk)

    return final_chunks


def chunk_document(
    doc: Document,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Chunk a single document into embedding-ready pieces.

    Pipeline:
    1. If it's a runbook, split by section headers first
    2. Within each section, split by size with overlap
    3. Attach metadata (source, section, job_id) to each chunk
    """
    chunks = []
    doc_type = doc.metadata.get("doc_type", "general")

    if doc_type == "runbook":
        # Section-aware chunking for runbooks
        sections = _split_by_sections(doc.content)
        for section_name, section_text in sections:
            text_chunks = _split_text_with_overlap(
                section_text, chunk_size, chunk_overlap
            )
            for i, text in enumerate(text_chunks):
                chunk_id = (
                    f"{doc.metadata.get('source_file', 'unknown')}__{section_name}__{i}"
                )
                chunks.append(
                    Chunk(
                        content=text,
                        metadata={
                            **doc.metadata,
                            "section": section_name,
                            "chunk_index": i,
                        },
                        chunk_id=chunk_id,
                    )
                )
    else:
        # Simple chunking for non-runbook docs (training, knowledge)
        text_chunks = _split_text_with_overlap(doc.content, chunk_size, chunk_overlap)
        for i, text in enumerate(text_chunks):
            chunk_id = f"{doc.metadata.get('source_file', 'unknown')}__{i}"
            chunks.append(
                Chunk(
                    content=text,
                    metadata={
                        **doc.metadata,
                        "section": _identify_section(text),
                        "chunk_index": i,
                    },
                    chunk_id=chunk_id,
                )
            )

    return chunks


def chunk_all_documents(
    documents: list[Document],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Chunk ALL loaded documents, ready for embedding.

    This is the main entry point called after load_all_documents().

    Args:
        documents: List of Document objects from the loader
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap between consecutive chunks in tokens

    Returns:
        List of Chunk objects ready for embedding and indexing
    """
    all_chunks = []

    for doc in documents:
        doc_chunks = chunk_document(doc, chunk_size, chunk_overlap)
        all_chunks.extend(doc_chunks)

    logger.info(
        f"Chunked {len(documents)} documents into {len(all_chunks)} chunks "
        f"(avg {len(all_chunks) / max(len(documents), 1):.1f} chunks/doc)"
    )

    return all_chunks
