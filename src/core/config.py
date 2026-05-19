"""Configuration settings for Teplodar ingestion pipeline."""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    # Database
    database_path: Path = Field(default="base/teplodar.db")

    # Input files
    yandex_yml_path: Path = Field(default="yandex_yml_base.xml")

    # HTTP client settings
    http_timeout: int = Field(default=30)
    http_retry_attempts: int = Field(default=3)
    rate_limit_delay: float = Field(default=1.0)
    max_concurrent_requests: int = Field(default=3)

    # User agent for scraping
    user_agent: str = Field(default="TeplodarKnowledgeBot/0.1 (+contact@example.com)")

    # PDF storage
    pdf_storage_path: Path = Field(default="base/pdfs/")

    # Logging
    log_level: str = Field(default="INFO")

    # RAG settings
    embedding_model_name: str = Field(default="intfloat/multilingual-e5-base")
    embedding_dim: int = Field(default=768)
    chunk_size_tokens: int = Field(default=400)
    chunk_overlap_tokens: int = Field(default=80)
    top_k: int = Field(default=8)
    index_version: str = Field(default="e5-base-v1")
    device: str = Field(default="cpu")  # 'cpu' or 'cuda'
    batch_size_embedding: int = Field(default=32)
    pdf_dedup_threshold: float = Field(default=0.92)
    product_boost: float = Field(default=0.05)

    # Telegram bot
    bot_token: str = Field(default="")
    operator_chat_id: int = Field(default=0)

    # Claude CLI OAuth (token stored in data/.claude_token.json, shared with ArkadiyJarvis)
    claude_code_oauth_token: str = Field(default="")
    claude_refresh_token: str = Field(default="")
    claude_cli_path: str = Field(default="claude")
    # Final-answer model. Sonnet ~3-5s vs Opus ~15-20s for ~200 tokens, with
    # near-equivalent quality on Russian RAG. Empty string = CLI's own default.
    claude_model: str = Field(default="claude-sonnet-4-5")
    # Intent extraction / reformulation — Haiku is plenty fast.
    claude_reformulation_model: str = Field(default="claude-haiku-4-5-20251001")
    # Cross-process upper bound on concurrent Claude CLI subprocesses.
    # Bot + admin + eval workers all share this cap via a file-lock pool —
    # protects the Pro OAuth account from 429-storm under traffic spikes.
    claude_cli_max_concurrent: int = Field(default=4)
    claude_cli_slots_dir: Path = Field(default=Path("/tmp/teplodar_claude_slots"))

    def __post_init__(self):
        """Ensure directories exist."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.pdf_storage_path.mkdir(parents=True, exist_ok=True)


settings = Settings()
