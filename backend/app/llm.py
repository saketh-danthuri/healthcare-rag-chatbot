"""
llm.py - Local LLM Client Factory
=================================
WHY: One place to build LLM clients so every caller (agent graph, guardrail
     classifier, evaluation) points at the same local Ollama server.

We use Ollama's OpenAI-compatible API (`/v1`), which means we can keep using
the standard `langchain_openai.ChatOpenAI` and the `openai` SDK unchanged -
only the base_url and model name differ from the old Azure setup. No cloud
account, no API key, fully local.
"""

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI, OpenAI

from app.config.settings import get_settings


def get_chat_model(temperature: float = 0.1, max_tokens: int = 2048) -> ChatOpenAI:
    """LangChain chat model backed by the local Ollama server.

    Used by the LangGraph agent (with .bind_tools) and the RAGAS judge.
    """
    settings = get_settings()
    return ChatOpenAI(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
        model=settings.ollama_chat_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def get_openai_client() -> OpenAI:
    """Raw (sync) OpenAI SDK client pointed at the local Ollama server."""
    settings = get_settings()
    return OpenAI(base_url=settings.ollama_base_url, api_key=settings.ollama_api_key)


def get_async_openai_client() -> AsyncOpenAI:
    """Raw (async) OpenAI SDK client pointed at the local Ollama server."""
    settings = get_settings()
    return AsyncOpenAI(
        base_url=settings.ollama_base_url, api_key=settings.ollama_api_key
    )
