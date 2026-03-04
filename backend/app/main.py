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
    logger.info(f"Azure OpenAI endpoint: {settings.azure_openai_endpoint[:30]}...")
    logger.info(f"Azure AI Search endpoint: {settings.azure_search_endpoint}")

    # Quick Azure AI Search connectivity check (non-blocking)
    try:
        from app.ingestion.embedder import get_search_client

        search_client = get_search_client()
        results = search_client.search(search_text="*", top=0, include_total_count=True)
        doc_count = results.get_count() or 0
        logger.info(f"Azure AI Search connected - {doc_count} documents indexed")
    except Exception as e:
        logger.warning(
            f"Could not connect to Azure AI Search at startup: {e}. "
            "Will attempt to connect on first request. "
            "Run POST /api/ingest to populate the search index."
        )

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
