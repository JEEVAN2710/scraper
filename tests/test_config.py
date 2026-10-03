"""Unit tests for configuration management."""

import os
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.config.settings import Settings


def test_default_settings():
    """Verify default configuration values."""
    settings = Settings()
    assert settings.APP_NAME == "Financial-AI-Assistant"
    assert settings.ENVIRONMENT == "development"
    assert settings.MYSQL_PORT == 3306
    assert settings.MYSQL_DATABASE == "financial_ai"
    assert settings.MYSQL_USER == "root"
    assert settings.MYSQL_POOL_SIZE == 5
    assert settings.OLLAMA_MODEL == "phi3:mini"
    assert settings.DOWNLOAD_DIR == Path("data/downloads")
    assert settings.PROCESSED_DIR == Path("data/processed")
    assert settings.EXPORT_DIR == Path("data/exports")
    assert settings.LOGS_DIR == Path("logs")


def test_custom_environment_settings(monkeypatch):
    """Verify settings loaded from environment overrides."""
    monkeypatch.setenv("APP_NAME", "Custom-Financial-AI")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_DATABASE", "custom_fin_db")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")

    settings = Settings()
    assert settings.APP_NAME == "Custom-Financial-AI"
    assert settings.MYSQL_PORT == 3307
    assert settings.MYSQL_DATABASE == "custom_fin_db"
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.OLLAMA_MODEL == "llama3.2:3b"


def test_invalid_log_level(monkeypatch):
    """Verify invalid log level raises validation error."""
    monkeypatch.setenv("LOG_LEVEL", "SUPER_VERBOSE")
    with pytest.raises(ValidationError):
        Settings()


def test_mysql_config_dict():
    """Verify MySQL configuration dictionary generation."""
    settings = Settings(
        MYSQL_HOST="127.0.0.1",
        MYSQL_PORT=3306,
        MYSQL_USER="test_user",
        MYSQL_PASSWORD="secret_password",
        MYSQL_DATABASE="test_db",
    )
    cfg_with_db = settings.get_mysql_config(include_database=True)
    assert cfg_with_db["host"] == "127.0.0.1"
    assert cfg_with_db["port"] == 3306
    assert cfg_with_db["user"] == "test_user"
    assert cfg_with_db["password"] == "secret_password"
    assert cfg_with_db["database"] == "test_db"

    cfg_without_db = settings.get_mysql_config(include_database=False)
    assert "database" not in cfg_without_db


def test_directory_creation(tmp_path):
    """Verify ensure_directories creates required folders."""
    settings = Settings(
        DOWNLOAD_DIR=tmp_path / "downloads",
        PROCESSED_DIR=tmp_path / "processed",
        EXPORT_DIR=tmp_path / "exports",
        LOGS_DIR=tmp_path / "logs",
    )
    assert not settings.DOWNLOAD_DIR.exists()
    settings.ensure_directories()
    assert settings.DOWNLOAD_DIR.exists()
    assert settings.PROCESSED_DIR.exists()
    assert settings.EXPORT_DIR.exists()
    assert settings.LOGS_DIR.exists()
