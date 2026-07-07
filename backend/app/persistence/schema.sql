-- ============================================================
-- schema.sql - Interactions / audit store for the memory layer
-- ============================================================
-- WHY THIS EXISTS (and how it differs from the checkpointer):
--   The LangGraph Postgres checkpointer stores opaque, serialized agent
--   runtime state (the "checkpoints"/"checkpoint_blobs"/"checkpoint_writes"
--   tables it creates via .setup()). That is how the AGENT resumes a thread.
--   These tables are the clean, queryable system of record for HUMANS and
--   AUDITORS: listing a user's conversations, rehydrating history on a fresh
--   device, and a compliance trail of every approval-required action.
--
-- KEYING / SCALE:
--   user_id is the top-level partition key on every table, and the leading
--   column of the per-user indexes, so "list my conversations" and per-user
--   retention are O(that user's data), not O(all data). conversation_id is
--   TEXT and IS the LangGraph thread_id (accepts the existing client
--   "session-<uuid>" ids directly), so there is no id-mapping layer.
--
-- This file is idempotent (IF NOT EXISTS everywhere) and is applied on startup
-- in main.py's lifespan, right after the checkpointer's own .setup().

CREATE SCHEMA IF NOT EXISTS agent_memory;

-- One row per logical conversation. conversation_id == LangGraph thread_id.
CREATE TABLE IF NOT EXISTS agent_memory.conversations (
    conversation_id  TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    title            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_message_at  TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'active',   -- active | archived
    summary          TEXT                              -- reserved for Phase 3 summarization
);
CREATE INDEX IF NOT EXISTS idx_conv_user_updated
    ON agent_memory.conversations (user_id, updated_at DESC);

-- Full, queryable message log (mirrors what the agent saw/produced).
CREATE TABLE IF NOT EXISTS agent_memory.messages (
    message_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  TEXT NOT NULL
                       REFERENCES agent_memory.conversations(conversation_id)
                       ON DELETE CASCADE,
    user_id          TEXT NOT NULL,                    -- denormalized for fast per-user queries
    role             TEXT NOT NULL,                    -- user | assistant | tool | system
    content          TEXT,
    citations        JSONB,                            -- Citation[] from the retriever
    tool_calls       JSONB,                            -- proposed/pending tool call(s) on assistant msgs
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    seq              BIGINT GENERATED ALWAYS AS IDENTITY
);
CREATE INDEX IF NOT EXISTS idx_msg_conv_seq
    ON agent_memory.messages (conversation_id, seq);

-- Compliance audit trail for approval-required actions.
CREATE TABLE IF NOT EXISTS agent_memory.action_audit (
    action_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  TEXT NOT NULL
                       REFERENCES agent_memory.conversations(conversation_id)
                       ON DELETE CASCADE,
    user_id          TEXT NOT NULL,
    tool_name        TEXT NOT NULL,                    -- send_escalation_email | query_database | publish_to_confluence
    tool_call_id     TEXT,                             -- ties back to the LLM tool call / checkpoint
    arguments        JSONB NOT NULL,                   -- proposed args (already PHI-masked by guardrails)
    decision         TEXT NOT NULL,                    -- pending | approved | rejected
    decided_by       TEXT,                             -- user_id of the approver
    decided_at       TIMESTAMPTZ,
    execution_result JSONB,                            -- result returned by the executor
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_conv
    ON agent_memory.action_audit (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_user
    ON agent_memory.action_audit (user_id, created_at DESC);
