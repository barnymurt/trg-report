"""Settings loaded from environment / .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Override any of these via the .env file or environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[4] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Anthropic ────────────────────────────────────────────────────
    anthropic_api_key: str = Field(default="")
    anthropic_model_haiku: str = "claude-3-5-haiku-latest"
    anthropic_model_sonnet: str = "claude-3-5-sonnet-latest"
    anthropic_model_sonnet_thinking: str = "claude-3-5-sonnet-latest"
    anthropic_beta: str = "prompt-caching-2024-07-31"

    # ─── Local services ───────────────────────────────────────────────
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    tei_url: str = "http://localhost:8080"
    tei_model: str = "BAAI/bge-small-en-v1.5"
    tei_model_multilingual: str = "BAAI/bge-m3"
    reranker_url: str = "http://localhost:8081"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    whisper_url: str = "http://localhost:9000"
    whisper_model: str = "distil-whisper/distil-large-v3"
    kokoro_url: str = "http://localhost:8880"
    smollm2_url: str = "http://localhost:8000"
    smollm2_model: str = "HuggingFaceTB/SmolLM2-1.7B-Instruct"
    docling_url: str = "http://localhost:5001"

    # ─── Project classifier + faithfulness ────────────────────────────
    project_classifier_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    compression_model: str = "HuggingFaceTB/SmolLM2-1.7B-Instruct"
    faithfulness_model: str = (
        "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
    )

    # ─── Cost / token discipline ──────────────────────────────────────
    max_claude_tokens_per_response: int = 2000
    compression_target_tokens: int = 3000
    rerank_top_k: int = 20
    rerank_final_k: int = 5
    monthly_budget_usd: float = 50.0

    # ─── Audit + storage ──────────────────────────────────────────────
    audit_db_path: str = "./data/audit.db"
    document_store_path: str = "./data/documents"
    qdrant_storage_path: str = "./data/qdrant"
    backup_path: str = "./backups"

    # ─── Auth (single-user, token-based) ──────────────────────────────
    app_auth_token: str = ""
    app_username: str = ""

    # ─── Paths ────────────────────────────────────────────────────────
    @property
    def repo_root(self) -> Path:
        # settings.py lives at apps/agent/src/trg/config/settings.py
        # parents[0]=config, [1]=trg, [2]=src, [3]=agent, [4]=apps, [5]=repo
        return Path(__file__).resolve().parents[5]

    @property
    def data_dir(self) -> Path:
        path = self.repo_root / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def config_dir(self) -> Path:
        path = self.data_dir / "config"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def agents_config_path(self) -> Path:
        return self.config_dir / "agents.json"

    @property
    def whitelist_path(self) -> Path:
        return self.config_dir / "whitelist.json"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
