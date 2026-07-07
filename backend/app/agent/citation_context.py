"""
citation_context.py - Out-of-band citation capture for the agent
=================================================================
WHY: LangChain tools must return a string, so `search_runbooks` cannot return
     the structured `citations` list `search_and_format()` produces. And a
     `contextvars.ContextVar` set inside the tool does NOT propagate back to the
     request handler: LangGraph's `ToolNode` runs the sync tool in a worker
     thread with a COPIED context, so writes there are invisible to the parent.

SOLUTION: A tiny module-level registry keyed by `thread_id` (== conversation_id).
     `search_runbooks` records the citations for its retrieval here; the
     streaming endpoint pops them after the turn completes to build the terminal
     event and run grounding verification.

CONCURRENCY: A single conversation turn is sequential (one retrieval at a time),
     so last-write-wins per thread_id is correct. Different conversations use
     different thread_ids and never collide. The endpoint pops (read + delete)
     in a `finally` block so entries never leak.
"""

import logging
import threading

logger = logging.getLogger(__name__)

# thread_id -> most recent retrieval's citations (list of citation dicts)
_REGISTRY: dict[str, list[dict]] = {}
_LOCK = threading.Lock()


def record_retrieval(thread_id: str, citations: list[dict]) -> None:
    """Record the citations produced by a retrieval for this conversation turn.

    Last-write-wins: if the agent searches more than once in a single turn, the
    most recent retrieval's citations are what the response is grounded against.
    """
    if not thread_id:
        return
    with _LOCK:
        _REGISTRY[thread_id] = list(citations or [])


def pop_retrieval(thread_id: str) -> list[dict]:
    """Return and remove the recorded citations for this conversation turn.

    Returns an empty list if the agent never searched (e.g. a direct answer).
    """
    if not thread_id:
        return []
    with _LOCK:
        return _REGISTRY.pop(thread_id, [])
