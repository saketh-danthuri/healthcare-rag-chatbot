"""Persistence layer for the memory subsystem.

Holds the shared psycopg async pool (reused by the LangGraph checkpointer and
the repositories) and the queryable interactions/audit store.
"""
