"""
main.py - FastAPI Application Entry Point
============================================
WHY: This is where everything comes together. FastAPI serves as the HTTP
     layer between the React frontend and the Python backend (RAG, agent, tools).

WHAT IT DOES AT STARTUP:
  1. Loads settings from .env
  2. Configures CORS (so the frontend can call the API)
  3. Registers API routes
  4. Verifies Azure AI Search connectivity
  5. Sets up monitoring (Application Insights)

WHAT IT DOES PER REQUEST:
  1. Validates the request (Pydantic models)
  2. Routes to the appropriate handler (/chat, /ingest, etc.)
  3. Returns JSON response with proper HTTP status codes
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config.settings import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - runs on startup and shutdown.

    WHY lifespan (not @app.on_event):
    FastAPI recommends lifespan for modern apps. It's cleaner and supports
    async initialization. The `yield` separates startup from shutdown.

    STARTUP: Verify Azure AI Search connectivity so we know the search index
    is reachable. If not, we log a warning but don't crash - the retriever
    will attempt to connect on the first request.
    """
    logger.info("Starting Healthcare RAG Chatbot...")
    settings = get_settings()
    logger.info(f"Docs path: {settings.docs_base_path}")
    logger.info(
        f"LLM (Ollama): {settings.ollama_base_url} model={settings.ollama_chat_model}"
    )
    logger.info(f"Vector store (Chroma): {settings.chroma_persist_dir}")

    # Create uploads directory for meeting transcript uploads
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Upload directory: {upload_dir}")

    # --- Memory layer: durable agent checkpointer + interactions store ---
    # Open the shared psycopg pool, set up the LangGraph Postgres checkpointer
    # and the agent_memory schema, then compile the agent graph against it. If
    # Postgres is unreachable, fall back to an in-memory checkpointer so the app
    # still runs (degraded: conversations won't persist across restarts).
    from app.agent.graph import init_agent, init_agent_in_memory

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from app.persistence.pool import apply_schema, open_pool

        pool = await open_pool()
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()  # idempotent; creates checkpoint tables
        await apply_schema()  # idempotent; creates agent_memory tables
        init_agent(checkpointer)
        app.state.memory_pool = pool
        logger.info("Memory layer initialized (Postgres checkpointer + store)")
    except Exception as e:
        logger.warning(
            f"Could not initialize Postgres memory layer: {e}. "
            "Falling back to in-memory checkpointer (no durable persistence)."
        )
        app.state.memory_pool = None
        init_agent_in_memory()

    # Quick local vector-store check (non-blocking)
    try:
        from app.retrieval.vector_store import count_documents

        doc_count = count_documents()
        logger.info(f"ChromaDB connected - {doc_count} document chunks indexed")
        if doc_count == 0:
            logger.warning(
                "Vector store is empty. Run `python scripts/ingest_local.py` "
                "or POST /api/ingest to index the Docs/ folder."
            )
    except Exception as e:
        logger.warning(f"Could not open ChromaDB at startup: {e}")

    # Initialize guardrails pipeline at startup to warm up ML models
    # (spaCy for PHI masking, sentence-transformers for topic filter).
    # Doing this here prevents cold-start latency on the first user request.
    try:
        from app.guardrails import get_guardrails_pipeline

        get_guardrails_pipeline()
        logger.info("Guardrails pipeline initialized successfully")

        # Warm the output masker (reuses the pipeline's already-loaded spaCy
        # model) so streamed-response PHI masking has no cold start.
        from app.guardrails.output_masker import get_output_masker

        get_output_masker()
    except Exception as e:
        logger.warning(f"Guardrails pipeline initialization warning: {e}")

    # Set up monitoring if configured
    if settings.applicationinsights_connection_string:
        try:
            from app.monitoring.telemetry import setup_telemetry

            setup_telemetry()
            logger.info("Application Insights telemetry configured")
        except Exception as e:
            logger.warning(f"Could not set up telemetry: {e}")

    yield  # App is running, handling requests

    # Shutdown
    logger.info("Shutting down Healthcare RAG Chatbot...")
    if getattr(app.state, "memory_pool", None) is not None:
        from app.persistence.pool import close_pool

        await close_pool()


# Create the FastAPI app
app = FastAPI(
    title="Healthcare Operations AI Chatbot",
    description=(
        "Agentic RAG chatbot for healthcare claims operations. "
        "Helps ops teams troubleshoot job failures, follow runbook procedures, "
        "and execute escalation actions."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
# WHY: The React frontend runs on a different port (3000) than the backend (8000).
# Without CORS, the browser blocks cross-origin API calls.
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(router)


# Root endpoint
@app.get("/")
async def root():
    return {
        "service": "Healthcare Operations AI Chatbot",
        "version": "0.1.0",
        "docs": "/docs",  # FastAPI auto-generated Swagger UI
    }
