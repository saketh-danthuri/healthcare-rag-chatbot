"""
telemetry.py - Azure Application Insights Monitoring
======================================================
WHY: You need visibility into how the chatbot is performing in production:
  - How many requests per minute? What's the latency?
  - Are LLM calls failing? How many tokens are we using (cost)?
  - Which runbooks are being searched most often?
  - Are users approving or rejecting agent actions?

HOW: OpenTelemetry is the industry standard for observability. It auto-
     instruments FastAPI (traces every request) and lets us add custom
     metrics. Azure Monitor/Application Insights collects everything and
     provides dashboards, alerts, and log queries.

WHAT WE TRACK:
  1. Request traces (auto): every API call with latency, status code
  2. LLM metrics (custom): token counts, latency, model used
  3. RAG metrics (custom): retrieval scores, result counts
  4. Agent metrics (custom): tool usage, approval rates
"""

import logging

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Module-level metric instruments (initialized in setup_telemetry)
_meter = None
_tracer = None
_llm_token_counter = None
_llm_latency_histogram = None
_rag_score_histogram = None
_action_counter = None


def setup_telemetry() -> None:
    """Initialize Azure Monitor OpenTelemetry integration.

    WHY called at startup: OpenTelemetry hooks into Python's logging and
    HTTP libraries at the module level. Doing this early ensures all
    subsequent requests are automatically traced.

    The 5GB/month free tier of Application Insights is more than enough
    for a personal project.
    """
    global _meter, _tracer, _llm_token_counter, _llm_latency_histogram
    global _rag_score_histogram, _action_counter

    settings = get_settings()

    if not settings.applicationinsights_connection_string:
        logger.info("Telemetry disabled (no App Insights connection string)")
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry import metrics, trace

        configure_azure_monitor(
            connection_string=settings.applicationinsights_connection_string,
        )

        _tracer = trace.get_tracer("healthcare-chatbot")
        _meter = metrics.get_meter("healthcare-chatbot")

        # Custom metrics
        _llm_token_counter = _meter.create_counter(
            "llm.tokens.total",
            description="Total LLM tokens used",
            unit="tokens",
        )

        _llm_latency_histogram = _meter.create_histogram(
            "llm.latency.ms",
            description="LLM call latency in milliseconds",
            unit="ms",
        )

        _rag_score_histogram = _meter.create_histogram(
            "rag.retrieval.score",
            description="RAG retrieval relevance scores",
        )

        _action_counter = _meter.create_counter(
            "agent.actions",
            description="Agent actions by type and status",
        )

        logger.info("Azure Monitor telemetry configured")

    except ImportError:
        logger.warning(
            "azure-monitor-opentelemetry not installed. "
            "Run: pip install azure-monitor-opentelemetry"
        )
    except Exception as e:
        logger.error(f"Failed to configure telemetry: {e}")


def track_llm_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
) -> None:
    """Record metrics for an LLM API call.

    Called after every Azure OpenAI call to track usage and cost.
    """
    if _llm_token_counter:
        _llm_token_counter.add(
            input_tokens + output_tokens,
            {"model": model, "direction": "total"},
        )
    if _llm_latency_histogram:
        _llm_latency_histogram.record(latency_ms, {"model": model})


def track_retrieval_score(score: float, source: str) -> None:
    """Record a retrieval relevance score."""
    if _rag_score_histogram:
        _rag_score_histogram.record(score, {"source": source})


def track_agent_action(
    action_type: str,
    status: str,  # "proposed", "approved", "rejected", "executed"
) -> None:
    """Record an agent action event."""
    if _action_counter:
        _action_counter.add(1, {"action_type": action_type, "status": status})
