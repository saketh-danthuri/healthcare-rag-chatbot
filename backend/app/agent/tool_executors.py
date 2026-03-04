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


# Map action types to their executor functions
ACTION_EXECUTORS = {
    "send_email": execute_send_email,
    "query_database": execute_database_query,
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
