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

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


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


class ChatResponse(BaseModel):
    """Agent's response to the user."""

    response: str = Field(description="The agent's text response")
    citations: list[dict] = Field(default_factory=list, description="Source citations")
    pending_action: dict | None = Field(
        default=None, description="Action awaiting user approval"
    )
    session_id: str = Field(description="Session ID")


class ActionApprovalRequest(BaseModel):
    """User approves or rejects a pending action."""

    session_id: str = Field(description="Session ID")
    action_type: str = Field(description="Type of action (send_email, query_database)")
    approved: bool = Field(description="True to approve, False to reject")
    parameters: dict = Field(default_factory=dict, description="Action parameters")


class ActionApprovalResponse(BaseModel):
    """Result of executing an approved action."""

    success: bool
    message: str
    result: dict | None = None


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


# --- Endpoints ---


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """Send a message to the AI agent and get a response.

    The agent will:
    1. Search relevant runbooks if it's an operational question
    2. Generate a response with citations
    3. Propose actions (email, DB query) if appropriate - these require approval

    The session_id maintains conversation context across multiple messages.
    """
    from app.agent.graph import chat

    try:
        result = await chat(
            message=request.message,
            session_id=request.session_id,
        )

        return ChatResponse(
            response=result.get("response", ""),
            citations=result.get("citations", []),
            pending_action=result.get("pending_action"),
            session_id=result.get("session_id", request.session_id),
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


@router.post("/chat/approve", response_model=ActionApprovalResponse)
async def approve_action_endpoint(
    request: ActionApprovalRequest,
) -> ActionApprovalResponse:
    """Approve or reject a pending action (email, DB query).

    WHY separate endpoint: Human-in-the-loop requires a two-step flow:
    1. Agent proposes action -> returned in /chat response as pending_action
    2. User reviews and decides -> sent to THIS endpoint
    3. If approved, action executes and result is returned
    """
    from app.agent.tool_executors import execute_approved_action

    if not request.approved:
        return ActionApprovalResponse(
            success=True,
            message="Action rejected by user. The agent will continue without executing.",
        )

    try:
        result = await execute_approved_action(
            action_type=request.action_type,
            parameters=request.parameters,
        )

        if result.get("success"):
            return ActionApprovalResponse(
                success=True,
                message=result.get("message", "Action executed successfully"),
                result=result,
            )
        else:
            return ActionApprovalResponse(
                success=False,
                message=result.get("error", "Action failed"),
                result=result,
            )

    except Exception as e:
        logger.error(f"Action execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
        from app.ingestion.embedder import get_search_client

        search_client = get_search_client()
        # Quick connectivity test: count documents in the index
        results = search_client.search(search_text="*", top=0, include_total_count=True)
        doc_count = results.get_count() or 0
        search_ok = True
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
        from app.ingestion.embedder import get_search_client

        settings = _get_settings()
        search_client = get_search_client()

        # Count total documents in the index
        results = search_client.search(search_text="*", top=0, include_total_count=True)
        total_count = results.get_count() or 0

        return {
            "index_name": settings.azure_search_index_name,
            "total_chunks": total_count,
            "search_endpoint": settings.azure_search_endpoint,
        }
    except Exception as e:
        return {"error": str(e)}
