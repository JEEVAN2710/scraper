"""Unit tests for V2 database repositories and schema extensions."""

from datetime import datetime
from unittest.mock import MagicMock
import pytest

from app.database.connection import DatabaseManager
from app.database.repositories import (
    CompanyRepository,
    CompanySourceRepository,
    AutomationRepository,
    AutomationRunRepository,
    ExtractionRunRepository,
    DocumentRepository,
    ProcessingLogRepository,
    FinancialDataRepository,
    RiskFactorRepository,
    ChunkRepository,
)


@pytest.fixture
def mock_db():
    """Create a mock DatabaseManager with cursor and connection context."""
    db = MagicMock(spec=DatabaseManager)
    cursor = MagicMock()
    conn = MagicMock()
    db.get_cursor.return_value.__enter__.return_value = (cursor, conn)
    return db, cursor, conn


def test_company_repository_v2_features(mock_db):
    """Test V2 active toggle and tracking tier on CompanyRepository."""
    db, cursor, _ = mock_db
    cursor.rowcount = 1
    cursor.lastrowid = 10

    repo = CompanyRepository(db_manager=db)

    # 1. Create with tracking tier and active flag
    cid = repo.create("Tata Motors", "TATAMOTORS", "https://tatamotors.com", tracking_tier="priority")
    assert cid == 10
    exec_call = cursor.execute.call_args_list[-1]
    assert "tracking_tier" in exec_call[0][0]
    assert exec_call[0][1][-1] == "priority"

    # 2. Set active
    assert repo.set_active(10, False) is True
    active_call = cursor.execute.call_args_list[-1]
    assert "UPDATE companies SET is_active = %s WHERE id = %s" in active_call[0][0]
    assert active_call[0][1] == (False, 10)

    # 3. Set tracking tier
    assert repo.set_tracking_tier(10, "priority") is True
    tier_call = cursor.execute.call_args_list[-1]
    assert "UPDATE companies SET tracking_tier = %s WHERE id = %s" in tier_call[0][0]
    assert tier_call[0][1] == ("priority", 10)


def test_company_source_repository_crud(mock_db):
    """Test full CRUD operations on CompanySourceRepository."""
    db, cursor, _ = mock_db
    cursor.lastrowid = 5
    cursor.rowcount = 1
    cursor.fetchone.return_value = {
        "id": 5,
        "company_id": 1,
        "source_type": "screener",
        "source_url": "https://www.screener.in/company/TCS/",
        "is_active": 1,
    }
    cursor.fetchall.return_value = [
        {"id": 5, "company_id": 1, "source_type": "screener"},
        {"id": 6, "company_id": 1, "source_type": "investor_relations"},
    ]

    repo = CompanySourceRepository(db_manager=db)

    # 1. Create
    sid = repo.create(
        company_id=1,
        source_type="screener",
        source_url="https://www.screener.in/company/TCS/",
    )
    assert sid == 5
    assert "INSERT INTO company_sources" in cursor.execute.call_args_list[-1][0][0]

    # 2. Get by ID
    source = repo.get_by_id(5)
    assert source["id"] == 5
    assert source["source_type"] == "screener"

    # 3. List by company
    sources = repo.list_by_company(1, active_only=True)
    assert len(sources) == 2
    assert "is_active = TRUE" in cursor.execute.call_args_list[-1][0][0]

    # 4. Update polled
    now = datetime(2026, 10, 3, 12, 0, 0)
    assert repo.update_polled(5, last_polled_at=now) is True
    assert cursor.execute.call_args_list[-1][0][1] == (now, 5)

    # 5. Set active
    assert repo.set_active(5, False) is True
    assert cursor.execute.call_args_list[-1][0][1] == (False, 5)

    # 6. Delete
    assert repo.delete(5) is True
    assert "DELETE FROM company_sources WHERE id = %s;" in cursor.execute.call_args_list[-1][0][0]


def test_automation_repository_scheduling(mock_db):
    """Test AutomationRepository creation, due-job lookup, and scheduling updates."""
    db, cursor, _ = mock_db
    cursor.lastrowid = 15
    cursor.rowcount = 1
    cursor.fetchall.return_value = [
        {"id": 15, "name": "Daily TCS Sync", "schedule_type": "interval", "next_run_at": datetime(2026, 10, 3, 9, 0, 0)}
    ]

    repo = AutomationRepository(db_manager=db)

    # 1. Create automation
    aid = repo.create(
        company_id=1,
        name="Daily TCS Sync",
        schedule_type="interval",
        schedule_expression="24h",
        source_id=5,
    )
    assert aid == 15
    assert "INSERT INTO automations" in cursor.execute.call_args_list[-1][0][0]

    # 2. List due automations
    ref_time = datetime(2026, 10, 3, 10, 0, 0)
    due_jobs = repo.list_due(current_time=ref_time)
    assert len(due_jobs) == 1
    assert "next_run_at <= %s" in cursor.execute.call_args_list[-1][0][0]
    assert cursor.execute.call_args_list[-1][0][1] == (ref_time,)

    # 3. Update schedule
    next_run = datetime(2026, 10, 4, 9, 0, 0)
    assert repo.update_schedule(15, last_run_at=ref_time, next_run_at=next_run) is True
    assert "UPDATE automations SET" in cursor.execute.call_args_list[-1][0][0]


def test_automation_run_repository_state_machine(mock_db):
    """Test AutomationRunRepository status transitions and document metrics."""
    db, cursor, _ = mock_db
    cursor.lastrowid = 101
    cursor.rowcount = 1
    cursor.fetchone.return_value = {
        "id": 101,
        "automation_id": 15,
        "status": "pending",
        "documents_discovered": 0,
    }

    repo = AutomationRunRepository(db_manager=db)

    # 1. Create run
    run_id = repo.create(automation_id=15, trigger_type="scheduled")
    assert run_id == 101
    assert "status" in cursor.execute.call_args_list[-1][0][0]
    assert cursor.execute.call_args_list[-1][0][1] == (15, "scheduled")

    # 2. Update to running with discovered count
    repo.update_status(run_id, status="running", docs_discovered=3)
    update_call = cursor.execute.call_args_list[-1]
    assert "documents_discovered = %s" in update_call[0][0]

    # 3. Complete run with metrics
    repo.update_status(
        run_id,
        status="completed",
        docs_downloaded=3,
        docs_processed=3,
    )
    final_call = cursor.execute.call_args_list[-1]
    assert "status = %s" in final_call[0][0]
    assert "completed_at = %s" in final_call[0][0]


def test_extraction_run_repository_auditing(mock_db):
    """Test ExtractionRunRepository stores validation errors, token usage, and durations."""
    db, cursor, _ = mock_db
    cursor.lastrowid = 501
    cursor.fetchone.return_value = {
        "id": 501,
        "document_id": 10,
        "model_name": "qwen3:4b",
        "raw_response": '{"revenue": 1000}',
        "is_valid": 1,
    }

    repo = ExtractionRunRepository(db_manager=db)

    run_id = repo.create(
        document_id=10,
        model_name="qwen3:4b",
        raw_response='{"revenue": 1000}',
        prompt_tokens=450,
        completion_tokens=85,
        is_valid=True,
        validation_errors=None,
        duration_seconds=3.25,
    )
    assert run_id == 501
    insert_call = cursor.execute.call_args_list[-1]
    assert "INSERT INTO extraction_runs" in insert_call[0][0]
    assert insert_call[0][1][1] == "qwen3:4b"
    assert insert_call[0][1][5] is True


def test_document_repository_v2_extensions(mock_db):
    """Test DocumentRepository V2 metadata, status filtering, and density updates."""
    db, cursor, _ = mock_db
    cursor.lastrowid = 202
    cursor.rowcount = 1
    cursor.fetchall.return_value = [{"id": 202, "processing_status": "ai_extracting"}]

    repo = DocumentRepository(db_manager=db)

    # 1. Create with V2 metadata fields
    doc_id = repo.create(
        company_id=1,
        file_name="annual_report_2025.pdf",
        local_path="data/downloads/ar2025.pdf",
        file_hash="abc123def456",
        source_id=5,
        file_size_bytes=1048576,
        page_count=85,
        text_density_score=0.92,
    )
    assert doc_id == 202
    insert_call = cursor.execute.call_args_list[-1]
    assert "source_id" in insert_call[0][0]
    assert "text_density_score" in insert_call[0][0]

    # 2. List by status
    docs = repo.list_by_status("ai_extracting")
    assert len(docs) == 1
    assert "processing_status = %s" in cursor.execute.call_args_list[-1][0][0]

    # 3. Update technical metadata
    assert repo.update_metadata(202, page_count=90, text_density_score=0.95) is True
    update_call = cursor.execute.call_args_list[-1]
    assert "page_count = %s" in update_call[0][0]
    assert "text_density_score = %s" in update_call[0][0]


def test_processing_log_v2_extensions(mock_db):
    """Test ProcessingLogRepository logging with duration_ms and automation_run_id."""
    db, cursor, _ = mock_db
    cursor.lastrowid = 303
    cursor.fetchall.return_value = [{"id": 303, "stage": "document_discovery"}]

    repo = ProcessingLogRepository(db_manager=db)

    log_id = repo.log(
        stage="document_discovery",
        status="success",
        automation_run_id=101,
        duration_ms=450,
        message="Discovered 3 new filings",
    )
    assert log_id == 303
    call = cursor.execute.call_args_list[-1]
    assert "automation_run_id" in call[0][0]
    assert "duration_ms" in call[0][0]

    logs = repo.list_by_automation_run(101)
    assert len(logs) == 1
    assert "automation_run_id = %s" in cursor.execute.call_args_list[-1][0][0]
