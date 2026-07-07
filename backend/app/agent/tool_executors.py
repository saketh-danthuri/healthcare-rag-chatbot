"""
tool_executors.py - Actual Execution of Approved Actions
=========================================================
WHY SEPARATE FROM tools.py:
  tools.py defines what the agent CAN do (tool schemas for the LLM).
  This file contains the actual execution code that runs AFTER human approval.

  This separation enforces the human-in-the-loop pattern:
  1. Agent calls tool -> returns action details (tools.py)
  2. Human reviews and approves
  3. System executes the approved action (THIS FILE)
  4. Result returned to agent

  If someone bypasses the approval flow, the tools.py functions still
  only return descriptions, never execute side effects.
"""

import logging
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import yaml

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def _load_email_template() -> str:
    """Load the email template from prompts.yaml."""
    prompts_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
    with open(prompts_path) as f:
        prompts = yaml.safe_load(f)
    return prompts["prompts"]["escalation_email_template"]


async def execute_send_email(parameters: dict) -> dict:
    """Actually send an escalation email via SMTP.

    Only called AFTER human approval. Uses Gmail SMTP with app password.

    Args:
        parameters: Dict with recipient, subject, issue_summary, etc.

    Returns:
        Dict with success status and details
    """
    settings = get_settings()

    if not settings.smtp_username or not settings.smtp_password:
        return {
            "success": False,
            "error": "Email not configured. Set SMTP_USERNAME and SMTP_PASSWORD in .env",
        }

    try:
        import aiosmtplib

        # Build email from template
        template = _load_email_template()
        body = template.format(
            subject=parameters.get("subject", "Escalation"),
            issue_summary=parameters.get("issue_summary", "N/A"),
            runbook_reference=parameters.get("runbook_reference", "N/A"),
            recommended_action=parameters.get(
                "recommended_action", "Please investigate"
            ),
            user_name=parameters.get("user_name", "System"),
            timestamp=parameters.get("timestamp", datetime.now(UTC).isoformat()),
        )

        # Create email message
        msg = MIMEMultipart()
        msg["From"] = settings.smtp_username
        msg["To"] = parameters.get("recipient", settings.escalation_default_to)
        msg["Subject"] = parameters.get("subject", "Healthcare Ops Escalation")
        msg.attach(MIMEText(body, "plain"))

        # Send via SMTP
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            start_tls=True,
        )

        logger.info(f"Escalation email sent to {msg['To']}")
        return {
            "success": True,
            "message": f"Email sent to {msg['To']}",
            "subject": msg["Subject"],
        }

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return {"success": False, "error": str(e)}


async def execute_database_query(parameters: dict) -> dict:
    """Actually execute a SQL query against PostgreSQL.

    Only called AFTER human approval. Uses a read-only database connection.

    Args:
        parameters: Dict with sql_query and description

    Returns:
        Dict with query results or error
    """
    settings = get_settings()

    try:
        import asyncpg

        conn = await asyncpg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
        )

        try:
            # Execute the query with a timeout
            rows = await conn.fetch(
                parameters["sql_query"],
                timeout=30,
            )

            # Convert to list of dicts for JSON serialization
            results = [dict(row) for row in rows]

            # Limit results to prevent massive responses
            max_rows = 100
            truncated = len(results) > max_rows
            results = results[:max_rows]

            logger.info(
                f"DB query returned {len(results)} rows"
                f"{' (truncated)' if truncated else ''}"
            )

            return {
                "success": True,
                "row_count": len(results),
                "truncated": truncated,
                "results": results,
                "query": parameters["sql_query"],
            }
        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Database query failed: {e}")
        return {"success": False, "error": str(e)}


async def execute_publish_confluence(parameters: dict) -> dict:
    """Create a Confluence page with structured meeting notes.

    Uses Confluence REST API v1: POST /rest/api/content
    Auth: Basic auth with email:api_token (base64 encoded)
    Body format: Confluence Storage Format (XHTML-like)
    """
    settings = get_settings()

    if not settings.confluence_base_url or not settings.confluence_api_token:
        return {
            "success": False,
            "error": "Confluence not configured. Set CONFLUENCE_BASE_URL, "
            "CONFLUENCE_USER_EMAIL, and CONFLUENCE_API_TOKEN in .env",
        }

    try:
        import base64

        import httpx

        body_html = _build_confluence_body(parameters)
        space_key = (
            parameters.get("space_key") or settings.confluence_default_space_key
        )

        payload: dict = {
            "type": "page",
            "title": parameters["title"],
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": body_html,
                    "representation": "storage",
                }
            },
        }

        if parameters.get("parent_page_id"):
            payload["ancestors"] = [{"id": parameters["parent_page_id"]}]

        credentials = base64.b64encode(
            f"{settings.confluence_user_email}:{settings.confluence_api_token}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.confluence_base_url}/rest/api/content",
                json=payload,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30,
            )

        if response.status_code in (200, 201):
            result = response.json()
            page_url = (
                f"{settings.confluence_base_url}{result['_links']['webui']}"
            )
            logger.info(f"Confluence page created: {parameters['title']}")
            return {
                "success": True,
                "message": f"Confluence page created: {parameters['title']}",
                "page_url": page_url,
                "page_id": result["id"],
            }
        else:
            error_body = response.text
            logger.error(
                f"Confluence API error {response.status_code}: {error_body}"
            )
            return {
                "success": False,
                "error": f"Confluence API returned {response.status_code}: {error_body}",
            }

    except Exception as e:
        logger.error(f"Failed to publish to Confluence: {e}")
        return {"success": False, "error": str(e)}


def _build_confluence_body(parameters: dict) -> str:
    """Convert structured meeting notes to Confluence Storage Format."""
    return (
        "<h2>Meeting Summary</h2>"
        f"<p>{_escape_html(parameters.get('summary', ''))}</p>"
        "<h2>Attendees</h2>"
        f"<p>{_escape_html(parameters.get('attendees', ''))}</p>"
        "<h2>Key Decisions</h2>"
        f"{_text_to_confluence_list(parameters.get('key_decisions', ''))}"
        "<h2>Action Items</h2>"
        f"{_text_to_confluence_list(parameters.get('action_items', ''))}"
        "<hr/>"
        f"<p><em>Generated by Healthcare Ops AI Assistant on "
        f"{parameters.get('timestamp', '')}</em></p>"
    )


def _escape_html(text: str) -> str:
    """Escape HTML special characters and convert newlines to <br/>."""
    import html

    return html.escape(text).replace("\n", "<br/>")


def _text_to_confluence_list(text: str) -> str:
    """Convert newline-separated text to an HTML unordered list."""
    import html

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if not lines:
        return "<p>None</p>"
    items = "".join(
        f"<li>{html.escape(line.lstrip('- '))}</li>" for line in lines
    )
    return f"<ul>{items}</ul>"


# Map action types to their executor functions
ACTION_EXECUTORS = {
    "send_email": execute_send_email,
    "query_database": execute_database_query,
    "publish_confluence": execute_publish_confluence,
}


async def execute_approved_action(action_type: str, parameters: dict) -> dict:
    """Execute an approved action by dispatching to the right executor.

    This is the single entry point called after human approval.

    Args:
        action_type: Type of action ("send_email", "query_database")
        parameters: Action parameters (validated during tool call)

    Returns:
        Execution result dict
    """
    executor = ACTION_EXECUTORS.get(action_type)

    if not executor:
        return {"success": False, "error": f"Unknown action type: {action_type}"}

    logger.info(f"Executing approved action: {action_type}")
    return await executor(parameters)
