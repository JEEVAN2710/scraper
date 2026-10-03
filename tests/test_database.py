"""Unit and repository tests for MySQL database management and migrations."""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.config.settings import Settings
from app.database.connection import DatabaseManager
from app.database.migrations.runner import parse_sql_statements, run_migrations, EXPECTED_TABLES
from app.database.repositories import CompanyRepository, DocumentRepository, ProcessingLogRepository


def test_parse_sql_statements():
    """Verify that schema.sql is cleanly parsed into individual statements."""
    schema_path = Path(__file__).resolve().parent.parent / "app" / "database" / "migrations" / "schema.sql"
    assert schema_path.exists(), "schema.sql must exist"

    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    statements = parse_sql_statements(sql)
    assert len(statements) >= 7, f"Expected at least 7 statements (DB + tables), got {len(statements)}"

    # Check for CREATE DATABASE
    assert any("CREATE DATABASE IF NOT EXISTS" in s.upper() for s in statements)

    table_names_found = []
    for stmt in statements:
        for expected in EXPECTED_TABLES:
            if f"`{expected}`" in stmt:
                table_names_found.append(expected)

    assert set(table_names_found) == set(EXPECTED_TABLES)


def test_database_manager_singleton():
    """Verify DatabaseManager implements the singleton pattern."""
    settings = Settings()
    dm1 = DatabaseManager(settings)
    dm2 = DatabaseManager(settings)
    assert dm1 is dm2


def test_company_repository_queries():
    """Verify CompanyRepository executes parameterized SQL."""
    mock_db = MagicMock(spec=DatabaseManager)
    mock_cursor = MagicMock()
    mock_conn = MagicMock()

    # Context manager mock for get_cursor
    mock_db.get_cursor.return_value.__enter__.return_value = (mock_cursor, mock_conn)
    mock_cursor.lastrowid = 42
    mock_cursor.fetchone.return_value = {"id": 42, "name": "Apple Inc.", "ticker": "AAPL"}

    repo = CompanyRepository(db_manager=mock_db)

    # 1. Create
    cid = repo.create("Apple Inc.", "AAPL", "https://apple.com")
    assert cid == 42
    insert_call = mock_cursor.execute.call_args_list[-1]
    assert "INSERT INTO companies" in insert_call[0][0]
    assert insert_call[0][1] == ("Apple Inc.", "AAPL", "https://apple.com")

    # 2. Get by ticker
    comp = repo.get_by_ticker("AAPL")
    assert comp["ticker"] == "AAPL"
    ticker_call = mock_cursor.execute.call_args_list[-1]
    assert "WHERE ticker = %s" in ticker_call[0][0]
    assert ticker_call[0][1] == ("AAPL",)


def test_document_repository_duplicate_detection_hash():
    """Verify DocumentRepository performs parameterized lookup by SHA-256 hash."""
    mock_db = MagicMock(spec=DatabaseManager)
    mock_cursor = MagicMock()
    mock_conn = MagicMock()

    mock_db.get_cursor.return_value.__enter__.return_value = (mock_cursor, mock_conn)
    mock_cursor.fetchone.return_value = {
        "id": 101,
        "file_name": "tcs_q1_2024.pdf",
        "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }

    repo = DocumentRepository(db_manager=mock_db)
    sha_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    doc = repo.get_by_hash(sha_hash)

    assert doc is not None
    assert doc["id"] == 101
    assert doc["file_hash"] == sha_hash

    # Verify parameterized SQL was used to prevent SQL injection
    execute_call = mock_cursor.execute.call_args_list[-1]
    assert "SELECT * FROM documents WHERE file_hash = %s;" in execute_call[0][0]
    assert execute_call[0][1] == (sha_hash,)


def test_processing_log_repository():
    """Verify ProcessingLogRepository records audit logs with parameterized queries."""
    mock_db = MagicMock(spec=DatabaseManager)
    mock_cursor = MagicMock()
    mock_conn = MagicMock()

    mock_db.get_cursor.return_value.__enter__.return_value = (mock_cursor, mock_conn)
    mock_cursor.lastrowid = 1

    repo = ProcessingLogRepository(db_manager=mock_db)
    log_id = repo.log(
        document_id=101,
        stage="extraction",
        status="success",
        message="Extracted 12 pages successfully.",
    )
    assert log_id == 1
    call = mock_cursor.execute.call_args_list[-1]
    assert "INSERT INTO processing_logs" in call[0][0]
    assert call[0][1][0] == 101
    assert call[0][1][1] == "extraction"
    assert call[0][1][2] == "success"
