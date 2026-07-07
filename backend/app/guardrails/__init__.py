"""
guardrails/ - Pre-Agent Safety Pipeline
=========================================
7-layer composable guardrails that run before every message reaches the
LangGraph agent and Azure OpenAI.

Usage:
    from app.guardrails import get_guardrails_pipeline

    pipeline = get_guardrails_pipeline()
    result = await pipeline.run(
        message=message,
        user_id=current_user.user_id,
        ip_address=req.client.host,
        session_id=request.session_id,
    )
    safe_message = result.final_message  # PHI-masked if applicable
"""

from app.guardrails.models import GuardrailAction, GuardrailResult, PipelineResult
from app.guardrails.pipeline import GuardrailsPipeline, get_guardrails_pipeline

__all__ = [
    "GuardrailsPipeline",
    "get_guardrails_pipeline",
    "GuardrailResult",
    "PipelineResult",
    "GuardrailAction",
]
