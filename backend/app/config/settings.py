"""
settings.py - Centralized Configuration
========================================
WHY: Every config value lives here (loaded from env vars via pydantic-settings).
     No hardcoded secrets or magic strings scattered across the codebase.
     Pydantic validates types at startup - if AZURE_OPENAI_API_KEY is missing,
     the app fails fast with a clear error instead of crashing mid-request.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),  # Check both backend/.env and project root .env
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Local LLM (Ollama via its OpenAI-compatible API) ---
    # WHY Ollama: runs entirely on this machine, no cloud account/keys needed.
    # We talk to it through its OpenAI-compatible endpoint (/v1) so we can reuse
    # the standard langchain_openai.ChatOpenAI / openai clients unchanged.
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_api_key: str = "ollama"  # placeholder; Ollama ignores the value
    ollama_chat_model: str = "llama3.2"  # tool-calling capable, ~2GB, CPU-friendly

    # --- Local embeddings (sentence-transformers, runs on-device) ---
    local_embedding_model: str = "all-MiniLM-L6-v2"  # 384-dim
    embedding_dim: int = 384

    # --- Local vector store (ChromaDB, persisted to disk) ---
    chroma_persist_dir: str = str(
        Path(__file__).resolve().parent.parent.parent.parent / "chroma-data"
    )
    chroma_collection_name: str = "healthcare-runbooks"

    # --- Azure OpenAI (legacy/optional — unused in local mode) ---
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "gpt-4o-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    # --- Azure AI Search (legacy/optional — unused in local mode) ---
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index_name: str = "healthcare-runbooks"

    # --- Azure Blob Storage (document source for ingestion) ---
    azure_blob_connection_string: str = ""
    azure_blob_container_name: str = "documents"

    # --- PostgreSQL (operations data — read-only role) ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "healthcare_ops"
    postgres_user: str = "chatbot_readonly"
    postgres_password: str = "changeme_in_production"

    # --- Memory PostgreSQL (durable agent state + interactions store) ---
    # The memory layer needs a READ-WRITE role. Keep it separate from the
    # read-only ops role above. If any memory_* var is blank, the
    # corresponding postgres_* value is reused (handy when one DB/role serves
    # both, e.g. local dev). The checkpointer uses a libpq (psycopg) DSN, NOT
    # the SQLAlchemy "+asyncpg" DSN used for ops queries.
    memory_postgres_host: str = ""
    memory_postgres_port: int = 0
    memory_postgres_db: str = ""
    memory_postgres_user: str = ""
    memory_postgres_password: str = ""

    # --- Confluence ---
    confluence_base_url: str = ""
    confluence_api_token: str = ""
    confluence_user_email: str = ""
    confluence_default_space_key: str = ""

    # --- File Upload ---
    upload_dir: str = str(Path(__file__).resolve().parent.parent / "uploads")
    max_upload_size_mb: int = 10

    # --- Email (Escalation) ---
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    escalation_default_to: str = ""

    # --- Azure Entra ID (Auth) ---
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""

    # --- Monitoring ---
    applicationinsights_connection_string: str = ""

    # --- Document Paths ---
    docs_base_path: str = str(
        Path(__file__).resolve().parent.parent.parent.parent / "Docs"
    )

    # --- Optional: Redis (for prod rate limiting across multiple instances) ---
    redis_url: str = ""  # e.g. "redis://localhost:6379/0" — empty = in-memory

    # --- Optional: Azure Content Safety (enhances DataViolationChecker) ---
    azure_content_safety_endpoint: str = ""  # empty = use regex-only checker
    azure_content_safety_key: str = ""

    # --- App ---
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173,https://healthcare-ops.azurestaticapps.net"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def memory_postgres_dsn(self) -> str:
        """libpq DSN for the memory layer (psycopg3 / LangGraph checkpointer).

        Falls back to the ops postgres_* values for any blank memory_* var so a
        single local Postgres can serve both during development. Note the scheme
        is plain ``postgresql://`` (psycopg3), NOT ``postgresql+asyncpg://``.
        """
        host = self.memory_postgres_host or self.postgres_host
        port = self.memory_postgres_port or self.postgres_port
        db = self.memory_postgres_db or self.postgres_db
        user = self.memory_postgres_user or self.postgres_user
        password = self.memory_postgres_password or self.postgres_password
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"


@lru_cache
def get_settings() -> Settings:
    """Singleton settings instance - cached after first call."""
    return Settings()
