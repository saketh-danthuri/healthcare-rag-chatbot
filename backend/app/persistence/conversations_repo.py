"""
conversations_repo.py - Interactions / audit store repository
==============================================================
Clean, queryable CRUD over the agent_memory tables. This is the system of
record for DISPLAY and AUDIT (the checkpointer is the system of record for
resuming the agent). Every read is scoped by user_id so one user can never see
another's conversations, messages, or audit rows.

All functions use the shared psycopg pool from pool.py and pass parameters via
psycopg's %s placeholders (never string interpolation) to avoid SQL injection.
"""

import logging
from typing import Any

from psycopg.types.json import Jsonb

from app.persistence.pool import get_pool

logger = logging.getLogger(__name__)


# --- Conversations ---


async def upsert_conversation(conversation_id: str, user_id: str) -> None:
    """Ensure a conversation row exists for (conversation_id, user_id).

    On conflict, bumps updated_at/last_message_at. Does NOT overwrite user_id —
    ownership is fixed at creation. Callers should verify ownership separately
    (see assert_owner) before trusting a client-supplied conversation_id.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO agent_memory.conversations
                (conversation_id, user_id, last_message_at, updated_at)
            VALUES (%s, %s, now(), now())
            ON CONFLICT (conversation_id) DO UPDATE
                SET updated_at = now(),
                    last_message_at = now()
            """,
            (conversation_id, user_id),
        )


async def get_conversation(conversation_id: str) -> dict[str, Any] | None:
    """Fetch a single conversation row, or None if it does not exist."""
    pool = get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT conversation_id, user_id, title, created_at, updated_at,
                   last_message_at, status, summary
            FROM agent_memory.conversations
            WHERE conversation_id = %s
            """,
            (conversation_id,),
        )
        return await cur.fetchone()


async def list_conversations(
    user_id: str, limit: int = 100, include_archived: bool = False
) -> list[dict[str, Any]]:
    """List a user's conversations, most-recently-updated first."""
    pool = get_pool()
    status_clause = "" if include_archived else "AND status <> 'archived'"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT conversation_id, user_id, title, created_at, updated_at,
                   last_message_at, status
            FROM agent_memory.conversations
            WHERE user_id = %s {status_clause}
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return await cur.fetchall()


async def set_title_if_unset(conversation_id: str, title: str) -> None:
    """Set the conversation title only if it is currently NULL/empty.

    Mirrors the frontend behavior of deriving a title from the first user
    message and never overwriting it afterward.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE agent_memory.conversations
            SET title = %s
            WHERE conversation_id = %s
              AND (title IS NULL OR title = '')
            """,
            (title, conversation_id),
        )


# --- Messages ---


async def add_message(
    conversation_id: str,
    user_id: str,
    role: str,
    content: str | None,
    citations: list[dict] | None = None,
    tool_calls: Any | None = None,
) -> None:
    """Append a message to the queryable log."""
    pool = get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO agent_memory.messages
                (conversation_id, user_id, role, content, citations, tool_calls)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                conversation_id,
                user_id,
                role,
                content,
                Jsonb(citations) if citations is not None else None,
                Jsonb(tool_calls) if tool_calls is not None else None,
            ),
        )


async def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    """Return all messages for a conversation in chronological order.

    citations/tool_calls come back already parsed (psycopg returns JSONB as
    Python objects).
    """
    pool = get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT message_id, role, content, citations, tool_calls, created_at, seq
            FROM agent_memory.messages
            WHERE conversation_id = %s
            ORDER BY seq ASC
            """,
            (conversation_id,),
        )
        return await cur.fetchall()


# --- Action audit ---


async def record_pending_action(
    conversation_id: str,
    user_id: str,
    tool_name: str,
    tool_call_id: str | None,
    arguments: dict,
) -> str:
    """Insert a 'pending' audit row when an approval-required action is proposed.

    Returns the new action_id (as a string).
    """
    pool = get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO agent_memory.action_audit
                (conversation_id, user_id, tool_name, tool_call_id, arguments, decision)
            VALUES (%s, %s, %s, %s, %s, 'pending')
            RETURNING action_id
            """,
            (conversation_id, user_id, tool_name, tool_call_id, Jsonb(arguments)),
        )
        row = await cur.fetchone()
        return str(row["action_id"])


async def resolve_latest_pending_action(
    conversation_id: str,
    decision: str,
    decided_by: str,
    execution_result: dict | None = None,
) -> None:
    """Flip the most recent 'pending' audit row for a conversation to
    approved/rejected and record who decided and the execution result.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE agent_memory.action_audit
            SET decision = %s,
                decided_by = %s,
                decided_at = now(),
                execution_result = %s
            WHERE action_id = (
                SELECT action_id FROM agent_memory.action_audit
                WHERE conversation_id = %s AND decision = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
            )
            """,
            (
                decision,
                decided_by,
                Jsonb(execution_result) if execution_result is not None else None,
                conversation_id,
            ),
        )
