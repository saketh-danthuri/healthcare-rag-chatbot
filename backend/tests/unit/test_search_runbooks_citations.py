"""Verify search_runbooks captures citations out-of-band, keyed by thread_id.

This guards the ToolNode context-propagation pitfall: the tool must receive the
injected RunnableConfig and record citations to the module registry so the
streaming endpoint can plumb them into the terminal event.
"""

import app.agent.tools as tools_mod
from app.agent.citation_context import pop_retrieval
from app.agent.tools import search_runbooks

_CITATIONS = [
    {"index": 1, "source_file": "CFT303.pdf", "section": "Recovery", "score": 0.9},
    {"index": 2, "source_file": "ATL101.pdf", "section": "Escalation", "score": 0.7},
]


def test_search_runbooks_records_citations_by_thread(monkeypatch):
    monkeypatch.setattr(
        tools_mod,
        "search_and_format",
        lambda query, top_k, filter_metadata: ("formatted context", _CITATIONS),
    )

    result = search_runbooks.invoke(
        {"query": "CFT303 failure"},
        config={"configurable": {"thread_id": "thread-abc"}},
    )

    assert isinstance(result, str)
    assert pop_retrieval("thread-abc") == _CITATIONS
    # pop is read-and-delete: a second pop yields nothing.
    assert pop_retrieval("thread-abc") == []


def test_no_thread_id_does_not_crash(monkeypatch):
    monkeypatch.setattr(
        tools_mod,
        "search_and_format",
        lambda query, top_k, filter_metadata: ("ctx", _CITATIONS),
    )

    # No configurable thread_id -> nothing recorded, no exception.
    result = search_runbooks.invoke({"query": "x"}, config={"configurable": {}})
    assert isinstance(result, str)
