"""Application configuration — loaded from environment / .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = Field(
        default="postgresql://vella:vella@localhost:5432/vella_ops",
        alias="DATABASE_URL",
    )

    # LLM providers
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # Extraction
    confidence_escalation_threshold: float = Field(default=0.70, alias="CONFIDENCE_ESCALATION_THRESHOLD")
    max_cost_per_document_usd: float = Field(default=5.0, alias="MAX_COST_PER_DOCUMENT_USD")

    # HITL governance
    hitl_auto_approve_threshold: float = Field(default=0.90, alias="HITL_AUTO_APPROVE_THRESHOLD")
    hitl_escalation_threshold: float = Field(default=0.70, alias="HITL_ESCALATION_THRESHOLD")
    hitl_review_sla_hours: int = Field(default=4, alias="HITL_REVIEW_SLA_HOURS")

    # Integrations
    quickbooks_client_id: str | None = Field(default=None, alias="QUICKBOOKS_CLIENT_ID")
    quickbooks_client_secret: str | None = Field(default=None, alias="QUICKBOOKS_CLIENT_SECRET")
    quickbooks_redirect_uri: str = Field(
        default="http://localhost:8000/api/v1/integrations/quickbooks/callback",
        alias="QUICKBOOKS_REDIRECT_URI",
    )
    plaid_client_id: str | None = Field(default=None, alias="PLAID_CLIENT_ID")
    plaid_secret: str | None = Field(default=None, alias="PLAID_SECRET")
    plaid_env: str = Field(default="sandbox", alias="PLAID_ENV")

    # Storage
    upload_dir: str = Field(default="data/uploads", alias="UPLOAD_DIR")
    processed_dir: str = Field(default="data/processed", alias="PROCESSED_DIR")
    chroma_persist_dir: str = Field(default="data/chroma", alias="CHROMA_PERSIST_DIR")

    # API
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    debug: bool = Field(default=False, alias="DEBUG")


settings = Settings()
