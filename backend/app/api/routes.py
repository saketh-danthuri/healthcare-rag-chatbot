"""
routes.py - API Endpoints
===========================
WHY: These are the HTTP endpoints that the frontend calls. Each endpoint
     maps to a specific user action in the chat UI.

ENDPOINTS:
  POST /api/chat          - Send a message, get agent response
  POST /api/chat/approve  - Approve a pending action
  POST /api/ingest        - Trigger document ingestion
  GET  /api/health        - Health check for Azure monitoring
  GET  /api/stats         - Retrieval system statistics
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.azure_auth import UserInfo, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])

# Permission roles governing PHI reveal on assistant output.
_VALID_ROLES = {"clinician", "general"}
_DEFAULT_ROLE = "general"  # Most restrictive: masked.


def _normalize_role(value: str | None) -> str:
    """Normalize a requested role to a known role, defaulting to most-restrictive."""
    role = (value or "").strip().lower()
    return role if role in _VALID_ROLES else _DEFAULT_ROLE


def _ndjson(obj: dict) -> str:
    """Serialize one NDJSON stream event (one JSON object per line)."""
    return json.dumps(obj, default=str) + "\n"


# --- Request/Response Models ---
# WHY Pydantic models: FastAPI auto-generates OpenAPI docs from these,
# validates input types, and provides clear error messages for bad requests.


class ChatRequest(BaseModel):
    """User sends a message to the chatbot."""

    message: str = Field(
        ..., min_length=1, max_length=5000, description="User's message"
    )
    session_id: str = Field(
        default="default", description="Session ID for conversation memory"
    )
    file_id: str | None = Field(
        default=None, description="ID of uploaded file to include as context"
    )
    role: str | None = Field(
        default=None,
        description="Permission role for output PHI reveal (clinician|general); "
        "the X-User-Role header takes precedence. Defaults to 'general' (masked).",
    )


class ChatResponse(BaseModel):
    """Agent's response to the user."""

    response: str = Field(description="The agent's text response")
    citations: list[dict] = Field(default_factory=list, description="Source citations")
    pending_action: dict | None = Field(
        default=None, description="Action awaiting user approval"
    )
    session_id: str = Field(description="Session ID")


class ActionApprovalRequest(BaseModel):
    """User approves or rejects a pending action.

    The action's parameters are sourced from the durable checkpoint (the
    paused graph state), so action_type/parameters here are accepted for
    backward compatibility but are not trusted as the source of truth.
    """

    session_id: str = Field(description="Conversation/session ID")
    action_type: str = Field(
        default="", description="Type of action (advisory; from the checkpoint)"
    )
    approved: bool = Field(description="True to approve, False to reject")
    parameters: dict = Field(default_factory=dict, description="Advisory parameters")


class ActionApprovalResponse(BaseModel):
    """Result of executing an approved action."""

    success: bool
    message: str
    result: dict | None = None


class ConversationSummary(BaseModel):
    """One row in a user's conversation list."""

    conversation_id: str
    title: str | None = None
    created_at: str
    updated_at: str
    status: str


class ConversationMessage(BaseModel):
    """One persisted message when rehydrating a conversation."""

    message_id: str
    role: str
    content: str | None = None
    citations: list[dict] | None = None
    tool_calls: object | None = None
    created_at: str


class CreateConversationResponse(BaseModel):
    """Result of creating a new server-side conversation."""

    conversation_id: str


class IngestResponse(BaseModel):
    """Results of document ingestion."""

    documents_loaded: int
    chunks_created: int
    chunks_indexed: int
    docs_path: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    search_connected: bool
    documents_indexed: int


class FileUploadResponse(BaseModel):
    """Response after uploading a file."""

    file_id: str
    filename: str
    size_bytes: int
    preview: str = Field(description="First 500 characters of the file")


# --- Memory-layer helpers ---


async def _assert_conversation_owner(conversation_id: str, user_id: str) -> None:
    """Ensure conversation_id either doesn't exist yet or belongs to user_id.

    Prevents one user from posting into, resuming, or reading another user's
    conversation/thread. A not-yet-created conversation is allowed (it will be
    created on first write under this user). Best-effort: if the store is
    unavailable, we log and allow the request rather than hard-failing chat.
    """
    try:
        from app.persistence import conversations_repo as repo

        existing = await repo.get_conversation(conversation_id)
    except Exception as e:  # pragma: no cover - store unavailable
        logger.warning(f"Ownership check skipped (store unavailable): {e}")
        return

    if existing and existing["user_id"] != user_id:
        raise HTTPException(
            status_code=403,
            detail="This conversation belongs to another user.",
        )


async def _persist_turn(
    conversation_id: str,
    user_id: str,
    user_message: str,
    result: dict,
) -> None:
    """Write the user + assistant messages (and any pending-action audit row).

    Best-effort: persistence problems are logged but never fail the chat. The
    user message stored here is the raw typed text for clean display on
    rehydration; the PHI-masked variant is what the agent/checkpoint sees.
    """
    try:
        from app.persistence import conversations_repo as repo

        await repo.upsert_conversation(conversation_id, user_id)
        await repo.set_title_if_unset(conversation_id, user_message[:60])

        await repo.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=user_message,
        )

        pending = result.get("pending_action")
        await repo.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=result.get("response", ""),
            citations=result.get("citations") or None,
            tool_calls=pending,
        )

        if pending:
            await repo.record_pending_action(
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name=pending.get("tool_name", ""),
                tool_call_id=pending.get("tool_call_id"),
                arguments=pending.get("arguments", {}),
            )
    except Exception as e:  # pragma: no cover - best effort
        logger.warning(f"Persisting conversation turn failed: {e}")


# --- Endpoints ---


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    req: Request,
    current_user: UserInfo = Depends(get_current_user),
) -> ChatResponse:
    """Send a message to the AI agent and get a response.

    The agent will:
    1. Search relevant runbooks if it's an operational question
    2. Generate a response with citations
    3. Propose actions (email, DB query) if appropriate - these require approval

    The session_id maintains conversation context across multiple messages.
    """
    from app.agent.graph import chat
    from app.config.settings import get_settings as _get_chat_settings
    from app.guardrails import get_guardrails_pipeline

    conversation_id = request.session_id
    user_id = current_user.user_id

    # Reject attempts to post into a conversation owned by someone else.
    await _assert_conversation_owner(conversation_id, user_id)

    try:
        message = request.message

        # If a file was uploaded, inject its content into the message
        if request.file_id:
            settings = _get_chat_settings()
            file_path = Path(settings.upload_dir) / f"{request.file_id}.txt"
            if not file_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail=f"Uploaded file not found: {request.file_id}",
                )
            transcript = file_path.read_text(encoding="utf-8")
            message = (
                f"[UPLOADED MEETING TRANSCRIPT]\n{transcript}\n"
                f"[END TRANSCRIPT]\n\n{message}"
            )

        # Run pre-agent guardrails pipeline on the fully assembled message.
        # This may transform the message (PHI masking) or block it entirely
        # (rate limit, injection, out-of-scope). Raises HTTPException on BLOCK.
        ip_address = req.client.host if req.client else "unknown"
        pipeline = get_guardrails_pipeline()
        pipeline_result = await pipeline.run(
            message=message,
            user_id=current_user.user_id,
            ip_address=ip_address,
            session_id=request.session_id,
        )
        safe_message = pipeline_result.final_message  # PHI-masked if applicable

        result = await chat(
            message=safe_message,
            conversation_id=conversation_id,
            user_id=user_id,
        )

        # Record actual token usage for the cost checker's rolling window.
        # Use a rough estimate here; replace with actual token count if the
        # LLM response includes usage data.
        pipeline.record_post_run_usage(
            user_id=user_id,
            token_count=len(safe_message.split()) * 4 // 3,
        )

        # Persist the interaction to the queryable store (best-effort: a memory
        # write must never fail the chat itself). The durable agent state lives
        # in the checkpointer; this store is for listing/rehydration/audit.
        await _persist_turn(
            conversation_id=conversation_id,
            user_id=user_id,
            user_message=request.message,
            result=result,
        )

        return ChatResponse(
            response=result.get("response", ""),
            citations=result.get("citations", []),
            pending_action=result.get("pending_action"),
            session_id=result.get("conversation_id", conversation_id),
        )

    except HTTPException:
        raise  # Guardrail blocks and 404s propagate directly
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


@router.post("/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    req: Request,
    x_user_role: str | None = Header(None, alias="X-User-Role"),
    current_user: UserInfo = Depends(get_current_user),
) -> StreamingResponse:
    """Stream the agent's response as NDJSON, PHI-masked per user role.

    Emits one JSON object per line:
      {"type":"start","session_id","role"}
      {"type":"delta","text"}          # already masked; repeated
      {"type":"final","citations","unverified_citations","pending_action","response"}
      {"type":"error","detail"}        # on mid-stream failure

    Blocking pre-work (ownership, file injection, input guardrails) runs BEFORE
    the stream opens, so a guardrail BLOCK is a normal HTTP 400/429. Role comes
    from the X-User-Role header (falling back to the body's `role`), defaulting
    to the most-restrictive 'general'. The masking decision is server-side; a
    'general' client never receives raw PHI over the wire.
    """
    from app.agent.citation_context import pop_retrieval
    from app.agent.citation_verifier import verify_citations
    from app.agent.graph import (
        get_turn_snapshot,
        snapshot_last_answer,
        snapshot_pending_action,
        stream_chat,
    )
    from app.config.settings import get_settings as _get_chat_settings
    from app.guardrails import get_guardrails_pipeline
    from app.guardrails.output_masker import get_output_masker

    conversation_id = request.session_id
    user_id = current_user.user_id
    role = _normalize_role(x_user_role or request.role)

    # Reject attempts to post into a conversation owned by someone else.
    await _assert_conversation_owner(conversation_id, user_id)

    message = request.message

    # If a file was uploaded, inject its content into the message.
    if request.file_id:
        settings = _get_chat_settings()
        file_path = Path(settings.upload_dir) / f"{request.file_id}.txt"
        if not file_path.exists():
            raise HTTPException(
                status_code=404, detail=f"Uploaded file not found: {request.file_id}"
            )
        transcript = file_path.read_text(encoding="utf-8")
        message = (
            f"[UPLOADED MEETING TRANSCRIPT]\n{transcript}\n"
            f"[END TRANSCRIPT]\n\n{message}"
        )

    # Run pre-agent input guardrails BEFORE opening the stream so a BLOCK is a
    # normal HTTP error (400/429), not a mid-stream failure.
    ip_address = req.client.host if req.client else "unknown"
    pipeline = get_guardrails_pipeline()
    pipeline_result = await pipeline.run(
        message=message,
        user_id=user_id,
        ip_address=ip_address,
        session_id=conversation_id,
    )
    safe_message = pipeline_result.final_message  # PHI-masked input

    async def gen() -> AsyncIterator[str]:
        accumulated: list[str] = []
        streamed_any = False
        try:
            yield _ndjson(
                {"type": "start", "session_id": conversation_id, "role": role}
            )

            masker = get_output_masker()
            token_stream = stream_chat(
                message=safe_message,
                conversation_id=conversation_id,
                user_id=user_id,
            )
            async for unit in masker.stream_masked(token_stream, role):
                if not unit:
                    continue
                streamed_any = True
                accumulated.append(unit)
                yield _ndjson({"type": "delta", "text": unit})

            # Post-stream: read durable state for pending action + raw answer.
            snapshot = await get_turn_snapshot(conversation_id)
            pending = snapshot_pending_action(snapshot)
            raw_answer = snapshot_last_answer(snapshot)

            # Fallback: the model produced an answer but streamed no content
            # (e.g. Ollama returned it whole). Emit it as one masked delta.
            if not streamed_any and raw_answer:
                fallback = masker.mask_text(raw_answer, role)
                accumulated.append(fallback)
                yield _ndjson({"type": "delta", "text": fallback})

            # Grounding: verify inline [Source N] refs against retrieved sources.
            # (Markers are identical in raw and masked text; verify on raw.)
            retrieved = pop_retrieval(conversation_id)
            annotated, unverified = verify_citations(raw_answer, retrieved)

            yield _ndjson(
                {
                    "type": "final",
                    "session_id": conversation_id,
                    "citations": annotated,
                    "unverified_citations": unverified,
                    "pending_action": pending,
                    "response": "".join(accumulated),
                }
            )

            # Post-turn bookkeeping (best-effort). Persist the RAW answer at rest
            # (masking is applied at display time), with annotated citations.
            pipeline.record_post_run_usage(
                user_id=user_id,
                token_count=len(safe_message.split()) * 4 // 3,
            )
            await _persist_turn(
                conversation_id=conversation_id,
                user_id=user_id,
                user_message=request.message,
                result={
                    "response": raw_answer,
                    "citations": annotated,
                    "pending_action": pending,
                },
            )
        except Exception as e:  # pragma: no cover - defensive stream guard
            logger.error(f"Streaming chat error: {e}", exc_info=True)
            yield _ndjson({"type": "error", "detail": "Chat processing failed."})
        finally:
            # Ensure the citation registry never leaks for this thread.
            pop_retrieval(conversation_id)

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # defeat proxy buffering of the stream
        },
    )


@router.post("/chat/approve", response_model=ActionApprovalResponse)
async def approve_action_endpoint(
    request: ActionApprovalRequest,
    current_user: UserInfo = Depends(get_current_user),
) -> ActionApprovalResponse:
    """Approve or reject a pending action (email, DB query, Confluence publish).

    Human-in-the-loop, durably: the agent graph is PAUSED before the action
    (interrupt_before=["execute_action"]). This endpoint resumes that paused,
    checkpointed graph -- so the decision survives a server restart and a
    multi-day gap, the action runs exactly once, and the agent sees the result.
    The action's parameters come from the checkpoint, not from the request body.
    """
    from app.agent.graph import resume_action
    from app.persistence import conversations_repo as repo

    conversation_id = request.session_id
    user_id = current_user.user_id
    await _assert_conversation_owner(conversation_id, user_id)

    try:
        result = await resume_action(
            conversation_id=conversation_id,
            approved=request.approved,
            decided_by=user_id,
        )

        if result.get("status") == "no_pending_action":
            raise HTTPException(
                status_code=409,
                detail="No pending action to approve for this conversation.",
            )

        exec_result = result.get("execution_result")

        # Audit + persist the assistant's follow-up (best-effort).
        try:
            await repo.resolve_latest_pending_action(
                conversation_id=conversation_id,
                decision="approved" if request.approved else "rejected",
                decided_by=user_id,
                execution_result=exec_result,
            )
            if result.get("response"):
                await repo.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role="assistant",
                    content=result.get("response"),
                    citations=result.get("citations") or None,
                )
        except Exception as persist_err:  # pragma: no cover - best effort
            logger.warning(f"Audit/persist after approval failed: {persist_err}")

        if not request.approved:
            return ActionApprovalResponse(
                success=True,
                message="Action rejected. The agent continued without executing it.",
                result={"agent_response": result.get("response", "")},
            )

        succeeded = bool(exec_result and exec_result.get("success"))
        return ActionApprovalResponse(
            success=succeeded,
            message=(
                (exec_result or {}).get("message")
                or (exec_result or {}).get("error")
                or "Action executed."
            ),
            result={
                **(exec_result or {}),
                "agent_response": result.get("response", ""),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Action resume error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Conversation history / listing (server-backed memory) ---


@router.post("/conversations", response_model=CreateConversationResponse)
async def create_conversation_endpoint(
    current_user: UserInfo = Depends(get_current_user),
) -> CreateConversationResponse:
    """Create a new server-side conversation and return its id (== thread_id)."""
    from app.persistence import conversations_repo as repo

    conversation_id = f"conv-{uuid.uuid4()}"
    await repo.upsert_conversation(conversation_id, current_user.user_id)
    return CreateConversationResponse(conversation_id=conversation_id)


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations_endpoint(
    current_user: UserInfo = Depends(get_current_user),
) -> list[ConversationSummary]:
    """List the current user's conversations, most recent first."""
    from app.persistence import conversations_repo as repo

    rows = await repo.list_conversations(current_user.user_id)
    return [
        ConversationSummary(
            conversation_id=r["conversation_id"],
            title=r.get("title"),
            created_at=r["created_at"].isoformat(),
            updated_at=r["updated_at"].isoformat(),
            status=r["status"],
        )
        for r in rows
    ]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ConversationMessage],
)
async def get_conversation_messages_endpoint(
    conversation_id: str,
    x_user_role: str | None = Header(None, alias="X-User-Role"),
    current_user: UserInfo = Depends(get_current_user),
) -> list[ConversationMessage]:
    """Rehydrate a conversation's messages (ownership-checked).

    This is what lets a user return days later -- on any device -- and continue
    where they left off, since the durable agent state behind it persists too.

    Assistant text is stored RAW at rest; because PHI may live in it, it is
    masked here per user role at display time (clinician = unmasked, general =
    masked) -- the same server-side role gate the live stream enforces.
    """
    from app.guardrails.output_masker import get_output_masker
    from app.persistence import conversations_repo as repo

    await _assert_conversation_owner(conversation_id, current_user.user_id)
    role = _normalize_role(x_user_role)
    masker = get_output_masker()
    rows = await repo.get_messages(conversation_id)

    def _display_content(row: dict) -> str | None:
        content = row.get("content")
        # Only assistant text can contain retrieved PHI; user text is stored as
        # typed and left as-is.
        if content and row["role"] == "assistant":
            return masker.mask_text(content, role)
        return content

    return [
        ConversationMessage(
            message_id=str(r["message_id"]),
            role=r["role"],
            content=_display_content(r),
            citations=r.get("citations"),
            tool_calls=r.get("tool_calls"),
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)) -> FileUploadResponse:
    """Upload a meeting transcript (.txt) for the agent to process.

    The file is saved server-side and a file_id is returned. Pass this
    file_id in the next /chat request so the agent can read the transcript.
    """
    from app.config.settings import get_settings as _get_upload_settings

    settings = _get_upload_settings()

    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported")

    # Read content and validate size
    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB",
        )

    # Save to uploads directory
    file_id = str(uuid.uuid4())
    upload_path = Path(settings.upload_dir) / f"{file_id}.txt"
    upload_path.write_bytes(content)

    text_content = content.decode("utf-8", errors="replace")
    preview = text_content[:500]

    logger.info(f"File uploaded: {file.filename} ({len(content)} bytes) -> {file_id}")

    return FileUploadResponse(
        file_id=file_id,
        filename=file.filename,
        size_bytes=len(content),
        preview=preview,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_endpoint(docs_path: str | None = None) -> IngestResponse:
    """Trigger document ingestion pipeline.

    Loads all documents from the Docs folder, chunks them, generates
    embeddings, and indexes them in Azure AI Search.

    WHY an endpoint: So you can re-ingest after adding new runbooks
    without restarting the server. Also useful for CI/CD to verify
    ingestion works after code changes.
    """
    from app.ingestion.embedder import run_full_ingestion

    try:
        stats = run_full_ingestion(docs_path)
        return IngestResponse(**stats)

    except Exception as e:
        logger.error(f"Ingestion error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_endpoint() -> HealthResponse:
    """Health check endpoint for Azure monitoring and load balancers.

    WHY: Azure Container Apps pings this to know if the container is alive.
    Application Insights uses it for uptime monitoring. Returns details
    about the connected services.
    """
    try:
        from app.retrieval.vector_store import count_documents

        # Quick connectivity test: count chunks in the local Chroma collection
        doc_count = count_documents()
        search_ok = doc_count > 0
    except Exception:
        doc_count = 0
        search_ok = False

    return HealthResponse(
        status="healthy" if search_ok else "degraded",
        version="0.1.0",
        search_connected=search_ok,
        documents_indexed=doc_count,
    )


@router.get("/stats")
async def stats_endpoint() -> dict:
    """Get retrieval system statistics."""
    try:
        from app.config.settings import get_settings as _get_settings
        from app.retrieval.vector_store import count_documents

        settings = _get_settings()
        total_count = count_documents()

        return {
            "index_name": settings.chroma_collection_name,
            "total_chunks": total_count,
            "vector_store": "chromadb",
            "persist_dir": settings.chroma_persist_dir,
            "embedding_model": settings.local_embedding_model,
        }
    except Exception as e:
        return {"error": str(e)}
