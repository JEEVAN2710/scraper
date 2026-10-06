"""Application settings and environment configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_FILE = str(Path(__file__).resolve().parent.parent.parent / ".env")


class Settings(BaseSettings):
    """Central configuration for Financial AI Assistant.

    Values are loaded from environment variables and an optional .env file.
    """

    model_config = SettingsConfigDict(
        env_file=(_ENV_FILE, ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = Field(default="Financial-AI-Assistant", description="Name of the application")
    ENVIRONMENT: str = Field(default="development", description="Runtime environment")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")

    # MySQL Configuration
    MYSQL_HOST: str = Field(default="localhost", description="MySQL server hostname or IP")
    MYSQL_PORT: int = Field(default=3306, description="MySQL port")
    MYSQL_DATABASE: str = Field(default="financial_ai", description="MySQL target database name")
    MYSQL_USER: str = Field(default="root", description="MySQL username")
    MYSQL_PASSWORD: str = Field(default="", description="MySQL password")
    MYSQL_POOL_SIZE: int = Field(default=5, ge=1, le=32, description="Connection pool size")
    MYSQL_POOL_NAME: str = Field(default="financial_ai_pool", description="Connection pool name")
    MYSQL_CONNECT_TIMEOUT: int = Field(default=10, description="Database connection timeout in seconds")

    # LLM Configuration & Model Switch
    LLM_ENABLED: bool = Field(
        default=True,
        description="Master switch to turn LLM on or off (true / false)",
    )
    LLM_PROVIDER: str = Field(
        default="ollama",
        description="Active LLM provider. Options: 'ollama' | 'disabled'",
    )

    # Ollama LLM Configuration (Phase 4)
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", description="Ollama API base URL")
    OLLAMA_MODEL: str = Field(default="phi3:mini", description="Ollama model identifier")
    OLLAMA_TIMEOUT: int = Field(default=90, description="Inference request timeout in seconds")
    OLLAMA_MAX_RETRIES: int = Field(default=3, description="Maximum retry count for LLM calls")

    # Storage Paths
    DOWNLOAD_DIR: Path = Field(default=Path("data/downloads"), description="Directory for raw PDFs")
    PROCESSED_DIR: Path = Field(default=Path("data/processed"), description="Directory for processed files")
    EXPORT_DIR: Path = Field(default=Path("data/exports"), description="Directory for generated reports")
    LOGS_DIR: Path = Field(default=Path("logs"), description="Directory for runtime log files")

    # Document Processing Parameters
    CHUNK_SIZE: int = Field(default=1000, description="Maximum characters per chunk")
    CHUNK_OVERLAP: int = Field(default=150, description="Character overlap between consecutive chunks")
    OCR_FALLBACK_MIN_WORDS: int = Field(default=20, description="Minimum word threshold to trigger OCR fallback")
    OCR_LANGUAGE: str = Field(default="eng", description="Tesseract OCR language code")

    # Document Discovery & Acquisition Parameters (Phase 3)
    DOWNLOAD_TIMEOUT: float = Field(default=45.0, description="Timeout in seconds for downloading documents")
    DOWNLOAD_MAX_SIZE_MB: int = Field(default=100, description="Maximum allowed PDF size in MB")
    DOWNLOAD_CHUNK_SIZE: int = Field(default=65536, description="Chunk size in bytes for streaming downloads")
    DISCOVERY_TIMEOUT: float = Field(default=25.0, description="Timeout in seconds for web source discovery")
    DISCOVERY_MAX_PDFS: int = Field(default=30, description="Maximum candidate PDFs to discover per source")

    # API Configuration (Phase 7)
    API_HOST: str = Field(default="0.0.0.0", description="FastAPI host")
    API_PORT: int = Field(default=8000, description="FastAPI port")

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_val = value.upper()
        if upper_val not in valid_levels:
            raise ValueError(f"Invalid LOG_LEVEL '{value}'. Allowed: {sorted(valid_levels)}")
        return upper_val

    @field_validator("LLM_PROVIDER")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        valid_providers = {"ollama", "disabled"}
        lower_val = value.lower()
        if lower_val not in valid_providers:
            raise ValueError(
                f"Invalid LLM_PROVIDER '{value}'. Allowed: {sorted(valid_providers)}"
            )
        return lower_val

    @property
    def llm_enabled(self) -> bool:
        """Returns True when LLM is turned on and provider is active."""
        return bool(self.LLM_ENABLED and self.LLM_PROVIDER != "disabled")

    @property
    def is_llm_enabled(self) -> bool:
        """Alias for llm_enabled."""
        return self.llm_enabled

    def ensure_directories(self) -> None:
        """Ensure all storage and logging directories exist on disk."""
        try:
            for path in [self.DOWNLOAD_DIR, self.PROCESSED_DIR, self.EXPORT_DIR, self.LOGS_DIR]:
                path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Failed to verify/create storage directory: %s", exc)
            raise

    def get_mysql_config(self, include_database: bool = True) -> Dict[str, Any]:
        """Return a dictionary of MySQL connection parameters."""
        config: Dict[str, Any] = {
            "host": self.MYSQL_HOST,
            "port": self.MYSQL_PORT,
            "user": self.MYSQL_USER,
            "password": self.MYSQL_PASSWORD,
            "connection_timeout": self.MYSQL_CONNECT_TIMEOUT,
        }
        if include_database:
            config["database"] = self.MYSQL_DATABASE
        return config


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of the application settings."""
    try:
        settings = Settings()
        settings.ensure_directories()
        return settings
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception("Failed to load application settings from environment: %s", exc)
        raise
