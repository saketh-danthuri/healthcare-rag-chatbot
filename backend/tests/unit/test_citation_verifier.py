"""Unit tests for citation grounding verification."""

from app.agent.citation_verifier import verify_citations


def _retrieved(n: int) -> list[dict]:
    return [{"index": i, "source_file": f"doc{i}.pdf"} for i in range(1, n + 1)]


def test_hallucinated_source_is_flagged():
    retrieved = _retrieved(5)  # indices 1..5
    answer = "See the runbook [Source 9] for the escalation path."

    annotated, unverified = verify_citations(answer, retrieved)

    assert unverified == [9]
    # All retrieved sources remain verified; none was actually cited.
    assert all(c["verified"] is True for c in annotated)
    assert all(c["cited"] is False for c in annotated)


def test_valid_citation_marks_cited_and_no_unverified():
    retrieved = _retrieved(5)
    answer = "The fix is documented in [Source 3]."

    annotated, unverified = verify_citations(answer, retrieved)

    assert unverified == []
    assert annotated[2]["index"] == 3
    assert annotated[2]["cited"] is True
    # Others retrieved but not referenced.
    assert annotated[0]["cited"] is False


def test_mixed_valid_and_hallucinated():
    retrieved = _retrieved(3)
    answer = "Per [Source 2] and also [ SOURCE 7 ], restart the job."

    annotated, unverified = verify_citations(answer, retrieved)

    assert unverified == [7]
    assert annotated[1]["cited"] is True


def test_no_citations_in_answer():
    retrieved = _retrieved(2)
    annotated, unverified = verify_citations("A plain answer.", retrieved)

    assert unverified == []
    assert all(c["cited"] is False for c in annotated)


def test_empty_answer_and_no_retrieval():
    annotated, unverified = verify_citations("", [])
    assert annotated == []
    assert unverified == []
