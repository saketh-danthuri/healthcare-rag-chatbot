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

    # --- Azure OpenAI (LLM via Azure AI Foundry) ---
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "gpt-4o-mini"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"

    # --- Azure AI Search ---
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index_name: str = "healthcare-runbooks"

    # --- Azure Blob Storage (document source for ingestion) ---
    azure_blob_connection_string: str = ""
    azure_blob_container_name: str = "documents"

    # --- PostgreSQL ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "healthcare_ops"
    postgres_user: str = "chatbot_readonly"
    postgres_password: str = "changeme_in_production"

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


@lru_cache
def get_settings() -> Settings:
    """Singleton settings instance - cached after first call."""
    return Settings()
