"""
tools.py - Agent Tool Definitions
====================================
WHY: These are the "hands" of the agent - the actions it can take beyond
     just generating text. Each tool is a Python function decorated with
     LangChain's @tool decorator, which lets the LLM call them by name.

TOOLS:
  1. search_runbooks - RAG search (no approval needed)
  2. send_escalation_email - Send email (REQUIRES approval)
  3. query_database - Run SQL query (REQUIRES approval)

HUMAN-IN-THE-LOOP:
  Tools 2 and 3 don't execute directly. They return a "pending action"
  that the agent graph's interrupt node catches. The user must approve
  before execution proceeds.
"""

import logging
from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.agent.citation_context import record_retrieval
from app.retrieval.retriever import search_and_format

logger = logging.getLogger(__name__)


@tool
def search_runbooks(
    query: str,
    doc_type: str | None = None,
    config: RunnableConfig = None,
) -> str:
    """Search healthcare operations runbooks and knowledge base.

    Use this tool to find information about job failures, procedures,
    escalation paths, or any operational question. This searches across
    all runbook documents (ATL, CFT, RCR, CLM series), training materials,
    and knowledge base articles.

    Args:
        query: What to search for (e.g., "CFT303A not started by 3 AM",
               "CLMU load failure procedure", "escalation for COPS KPI")
        doc_type: Optional filter - "runbook", "training", or "knowledge"

    Returns:
        Retrieved context with source citations
    """
    # `config` is injected by LangChain/LangGraph (not exposed to the LLM); it
    # carries the thread_id we use to hand structured citations back to the
    # request handler out-of-band (tools can only return a string).
    filter_metadata = None
    if doc_type:
        filter_metadata = {"doc_type": doc_type}

    context, citations = search_and_format(
        query=query,
        top_k=5,
        filter_metadata=filter_metadata,
    )

    # Record citations out-of-band, keyed by conversation thread_id, so the
    # streaming endpoint can plumb them into the terminal event + grounding check.
    thread_id = (config or {}).get("configurable", {}).get("thread_id")
    if thread_id:
        record_retrieval(thread_id, citations)

    if not citations:
        return (
            "No relevant documents found for this query. "
            "Try rephrasing or using specific job IDs (e.g., CFT303A, ATL101Y)."
        )

    # Format for the LLM
    return context


@tool
def send_escalation_email(
    recipient: str,
    subject: str,
    issue_summary: str,
    runbook_reference: str = "",
    recommended_action: str = "",
) -> dict:
    """Send an escalation email to the appropriate team.

    IMPORTANT: This action requires human approval before execution.
    The email will NOT be sent until the user approves.

    Use this when a runbook procedure says to escalate (e.g., "Call COPS SME",
    "Reach out to MGFT team", "Email OSS team").

    Args:
        recipient: Email address to send to
        subject: Email subject line
        issue_summary: Description of the issue
        runbook_reference: Which runbook triggered this escalation
        recommended_action: What the recipient should do

    Returns:
        Dict with action details (for human approval)
    """
    # This doesn't actually send the email - it returns the action details
    # for the human-in-the-loop approval flow
    return {
        "action_type": "send_email",
        "requires_approval": True,
        "parameters": {
            "recipient": recipient,
            "subject": subject,
            "issue_summary": issue_summary,
            "runbook_reference": runbook_reference,
            "recommended_action": recommended_action,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }


def validate_readonly_sql(sql_query: str) -> str | None:
    """Validate that a SQL string is a safe read-only SELECT.

    Returns None if the query is allowed, or an error message string if it is
    blocked. Shared by the query_database tool (so the LLM gets immediate
    feedback) and the agent's execute_action node (so the check still runs even
    though the node executes the approved query directly, bypassing the tool
    body).
    """
    sql_upper = sql_query.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return (
            "Only SELECT queries are allowed. "
            "INSERT, UPDATE, DELETE, and DDL are blocked for safety."
        )

    dangerous_patterns = [
        "DROP",
        "DELETE",
        "INSERT",
        "UPDATE",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "EXEC",
        "EXECUTE",
        "--",
        ";--",
    ]
    for pattern in dangerous_patterns:
        if pattern in sql_upper:
            return (
                f"Query contains blocked keyword: {pattern}. "
                "Only read-only SELECT queries are allowed."
            )
    return None


@tool
def query_database(
    sql_query: str,
    description: str = "",
) -> dict:
    """Query the healthcare operations PostgreSQL database.

    IMPORTANT: This action requires human approval before execution.
    Only SELECT queries are allowed (no INSERT, UPDATE, DELETE).

    Use this to look up claims data, member information, job run history,
    or any operational data.

    Args:
        sql_query: The SQL SELECT query to execute
        description: Human-readable description of what this query does

    Returns:
        Dict with action details (for human approval)
    """
    # Validate it's a read-only query
    validation_error = validate_readonly_sql(sql_query)
    if validation_error:
        return {
            "action_type": "query_database",
            "error": validation_error,
        }

    return {
        "action_type": "query_database",
        "requires_approval": True,
        "parameters": {
            "sql_query": sql_query,
            "description": description,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }


@tool
def publish_to_confluence(
    title: str,
    summary: str,
    key_decisions: str,
    action_items: str,
    attendees: str,
    space_key: str = "",
    parent_page_id: str = "",
) -> dict:
    """Publish structured meeting notes to a Confluence page.

    IMPORTANT: This action requires human approval before execution.
    The page will NOT be created until the user approves.

    Use this after processing a meeting transcript. Analyze the transcript
    to generate structured notes with summary, key decisions, action items,
    and attendees, then call this tool to publish them to Confluence.

    Args:
        title: Page title (e.g., "Meeting Notes - Sprint Review 2026-03-29")
        summary: Executive summary of the meeting
        key_decisions: Key decisions made during the meeting (one per line)
        action_items: Action items with owners and deadlines (one per line)
        attendees: List of meeting attendees
        space_key: Confluence space key (optional, uses default if empty)
        parent_page_id: ID of parent page to nest under (optional)

    Returns:
        Dict with action details (for human approval)
    """
    return {
        "action_type": "publish_confluence",
        "requires_approval": True,
        "parameters": {
            "title": title,
            "summary": summary,
            "key_decisions": key_decisions,
            "action_items": action_items,
            "attendees": attendees,
            "space_key": space_key,
            "parent_page_id": parent_page_id,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }


# List of all tools available to the agent
ALL_TOOLS = [
    search_runbooks,
    send_escalation_email,
    query_database,
    publish_to_confluence,
]

# Tools that require human approval before execution
APPROVAL_REQUIRED_TOOLS = {
    "send_escalation_email",
    "query_database",
    "publish_to_confluence",
}
