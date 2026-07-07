"""
pool.py - Shared psycopg3 async connection pool
=================================================
WHY A SHARED POOL: The LangGraph Postgres checkpointer (AsyncPostgresSaver) and
the interactions repositories both talk to the same Postgres. One pool, created
once at startup and closed at shutdown, keeps the total connection count bounded
(critical when the app runs as multiple replicas) instead of opening a fresh
connection per request.

WHY psycopg3 (not asyncpg): langgraph-checkpoint-postgres is built on psycopg3
and requires connections configured with autocommit=True and row_factory=
dict_row. The ops-data path (tool_executors.execute_database_query) keeps using
asyncpg separately and is untouched.
"""

import logging

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Module-level singleton. Created in main.py's lifespan via open_pool(), read
# everywhere else via get_pool().
_pool: AsyncConnectionPool | None = None


async def open_pool(max_size: int = 20) -> AsyncConnectionPool:
    """Create and open the shared pool. Call once during app startup.

    Connections are configured for the checkpointer's requirements:
      - autocommit=True          (the saver manages its own transactions)
      - row_factory=dict_row     (rows come back as dicts)
      - prepare_threshold=None   (DISABLE prepared statements; required so the
        checkpointer's multi-statement setup() and our multi-statement
        schema.sql don't hit "cannot insert multiple commands into a prepared
        statement". Also what transaction-mode poolers like PgBouncer need.)
    """
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings()
    _pool = AsyncConnectionPool(
        conninfo=settings.memory_postgres_dsn,
        max_size=max_size,
        open=False,  # opening in __init__ is deprecated; open explicitly below
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            "prepare_threshold": None,
        },
    )
    await _pool.open(wait=True)
    logger.info("Memory Postgres pool opened (max_size=%d)", max_size)
    return _pool


def get_pool() -> AsyncConnectionPool:
    """Return the shared pool. Raises if open_pool() was not called first."""
    if _pool is None:
        raise RuntimeError(
            "Memory Postgres pool is not initialized. "
            "open_pool() must run in the app lifespan before use."
        )
    return _pool


async def close_pool() -> None:
    """Close the shared pool. Call once during app shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Memory Postgres pool closed")


async def apply_schema() -> None:
    """Apply the idempotent interactions/audit DDL (schema.sql)."""
    from pathlib import Path

    schema_sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    pool = get_pool()
    async with pool.connection() as conn:
        await conn.execute(schema_sql)
    logger.info("agent_memory schema applied")
