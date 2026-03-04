"""
state.py - Agent State Schema
===============================
WHY: LangGraph agents are stateful - they maintain context across multiple
     steps (search, reason, act, respond). This module defines the state
     schema that gets passed between nodes in the agent graph.

     Think of it as the agent's "working memory" for a single conversation turn.
"""

from dataclasses import dataclass
from typing import Annotated, Literal

from langgraph.graph.message import add_messages


@dataclass
class PendingAction:
    """Represents an action waiting for human approval.

    WHY: When the agent wants to send an email or run a DB query, it doesn't
    execute immediately. Instead, it creates a PendingAction and pauses.
    The human reviews it, approves or rejects, and the agent continues.
    """

    action_type: str  # "send_email", "query_database", "export_excel"
    parameters: dict  # Action-specific params (recipient, query, etc.)
    reason: str  # Why the agent wants to do this
    status: Literal["pending", "approved", "rejected"] = "pending"
    result: str | None = None  # Result after execution


class AgentState(dict):
    """State that flows through the LangGraph agent.

    WHY TypedDict-style with annotations:
    - `messages`: The full conversation history (LangGraph's add_messages
      reducer handles appending new messages automatically)
    - `retrieved_context`: RAG results from the latest search
    - `citations`: Source citations for the frontend to display
    - `pending_action`: When the agent needs human approval
    - `session_id`: Ties the state to a user session

    LangGraph automatically manages state persistence and updates between nodes.
    """

    # Conversation messages (user + assistant + tool calls)
    messages: Annotated[list, add_messages]

    # RAG retrieval results
    retrieved_context: str
    citations: list[dict]

    # Human-in-the-loop
    pending_action: PendingAction | None

    # Session tracking
    session_id: str


def create_initial_state(session_id: str = "default") -> dict:
    """Create a fresh agent state for a new conversation.

    WHY factory function: Ensures every new conversation starts clean.
    No stale context or pending actions from previous sessions.
    """
    return {
        "messages": [],
        "retrieved_context": "",
        "citations": [],
        "pending_action": None,
        "session_id": session_id,
    }
