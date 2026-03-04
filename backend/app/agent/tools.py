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

from langchain_core.tools import tool

from app.retrieval.retriever import search_and_format

logger = logging.getLogger(__name__)


@tool
def search_runbooks(query: str, doc_type: str | None = None) -> str:
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
    filter_metadata = None
    if doc_type:
        filter_metadata = {"doc_type": doc_type}

    context, citations = search_and_format(
        query=query,
        top_k=5,
        filter_metadata=filter_metadata,
    )

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
    sql_upper = sql_query.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return {
            "action_type": "query_database",
            "error": "Only SELECT queries are allowed. "
            "INSERT, UPDATE, DELETE, and DDL are blocked for safety.",
        }

    # Check for dangerous patterns
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
            return {
                "action_type": "query_database",
                "error": f"Query contains blocked keyword: {pattern}. "
                "Only read-only SELECT queries are allowed.",
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


# List of all tools available to the agent
ALL_TOOLS = [search_runbooks, send_escalation_email, query_database]

# Tools that require human approval before execution
APPROVAL_REQUIRED_TOOLS = {"send_escalation_email", "query_database"}
