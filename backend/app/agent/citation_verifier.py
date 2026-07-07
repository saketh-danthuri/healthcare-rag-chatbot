"""
citation_verifier.py - Grounding check for inline [Source N] references
========================================================================
WHY: The LLM is instructed to cite retrieved context as `[Source N]`. Nothing
     stops it from citing a source number that was never retrieved (a
     hallucinated citation). This module parses the answer's inline references,
     compares them against what was ACTUALLY retrieved, annotates each retrieved
     citation with whether it was referenced, and flags any cited-but-not-
     retrieved source number as "unverified" so the UI can warn the user.

The `[Source N]` markers are not PHI, so this runs safely on the masked answer.
"""

import re

# Matches "[Source 3]", "[ source 3 ]", "[SOURCE 12]" etc. and captures the number.
_SOURCE_RE = re.compile(r"\[\s*source\s+(\d+)\s*\]", re.IGNORECASE)


def verify_citations(
    answer_text: str, retrieved: list[dict]
) -> tuple[list[dict], list[int]]:
    """Verify the answer's inline [Source N] references against retrieved sources.

    Args:
        answer_text: The (masked) assistant answer, possibly containing [Source N].
        retrieved:   Citation dicts from the retrieval (each has an "index").

    Returns:
        (annotated_citations, unverified_indices) where:
          - annotated_citations is `retrieved` with each dict gaining
            "verified": True (it was really retrieved) and
            "cited": bool (whether the answer referenced its index).
          - unverified_indices is the sorted list of [Source N] numbers that
            appear in the answer but were NOT retrieved (hallucinated refs).
    """
    cited_numbers = {int(n) for n in _SOURCE_RE.findall(answer_text or "")}
    retrieved_indices = {c.get("index") for c in retrieved}

    annotated: list[dict] = []
    for citation in retrieved:
        c = dict(citation)
        c["verified"] = True
        c["cited"] = c.get("index") in cited_numbers
        annotated.append(c)

    unverified = sorted(n for n in cited_numbers if n not in retrieved_indices)
    return annotated, unverified
