"""Unit and integration tests for V2 company cascade deletion, concall LLM analysis, and sector peer comparison."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.database.connection import DatabaseManager
from app.database.repositories import CompanyRepository
from app.extraction.transcript_analyzer import TranscriptAnalyzer
from app.main import app


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Create a mock DatabaseManager with cursor and connection context."""
    db = MagicMock(spec=DatabaseManager)
    cursor = MagicMock()
    conn = MagicMock()
    db.get_cursor.return_value.__enter__.return_value = (cursor, conn)
    return db, cursor, conn


def test_company_repository_delete(mock_db):
    """Test CompanyRepository.delete performs cascade deletion across all child tables."""
    db, cursor, _ = mock_db
    cursor.fetchall.return_value = [{"id": 10, "local_path": "data/downloads/report.pdf"}]
    cursor.rowcount = 1

    repo = CompanyRepository(db_manager=db)
    result = repo.delete(1, delete_files=False)

    assert result is True

    executed_queries = [call[0][0] for call in cursor.execute.call_args_list]
    joined_queries = " ".join(executed_queries)

    assert "DELETE FROM documents WHERE company_id" in joined_queries
    assert "DELETE FROM risk_factors WHERE company_id" in joined_queries
    assert "DELETE FROM financial_data WHERE company_id" in joined_queries
    assert "DELETE FROM companies WHERE id" in joined_queries


def test_api_delete_company(client):
    """Test DELETE /api/companies/{company_id} endpoint."""
    with patch.object(CompanyRepository, "get_by_id", return_value={"id": 1, "name": "TCS", "ticker": "TCS"}), \
         patch.object(CompanyRepository, "delete", return_value=True):
        resp = client.delete("/api/companies/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["company_id"] == 1


def test_api_rescrape_company(client):
    """Test POST /api/companies/{company_id}/rescrape endpoint."""
    dummy_scraped = {
        "success": True,
        "company_id": 1,
        "name": "Tata Consultancy Services",
        "ticker": "TCS",
        "currency": "INR",
        "metrics_count": 5,
        "risks_count": 4,
        "annual_reports": [{"file_name": "TCS_AR_2025.pdf"}],
        "concall_transcripts": [{"period": "Q1-FY25", "title": "Concall Transcript"}],
        "stages": ["Stage 1: Verified connection", "Stage 8: Completed"],
        "duration_seconds": 1.25,
    }

    with patch("app.api.routes.ingestion_pipeline.run_screener_ingestion", return_value=dummy_scraped):
        with patch.object(CompanyRepository, "get_by_id", return_value={"id": 1, "name": "TCS", "ticker": "TCS"}), \
             patch.object(CompanyRepository, "delete", return_value=True):
            resp = client.post("/api/companies/1/rescrape")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["company_id"] == 1


def test_api_sectors_endpoints(client):
    """Test GET /api/sectors and GET /api/sectors/{sector_name}/comparison endpoints."""
    resp = client.get("/api/sectors")
    assert resp.status_code == 200
    sectors = resp.json()
    assert isinstance(sectors, list)
    if len(sectors) >= 1:
        first_sector = sectors[0]
        assert "sector" in first_sector
        assert "company_count" in first_sector
        assert "companies" in first_sector

        sector_name = first_sector["sector"]
        detail_resp = client.get(f"/api/sectors/{sector_name}/comparison")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["sector"] == sector_name
        assert "peers" in detail
        assert "peer_count" in detail


def test_transcript_analyzer_json_parsing(mock_db):
    """Test TranscriptAnalyzer JSON parsing for clean and Markdown wrapped outputs."""
    db, _, _ = mock_db
    analyzer = TranscriptAnalyzer(db_manager=db)

    raw_json = '{"executive_summary": "Strong growth", "management_tone": "Optimistic"}'
    parsed, valid = analyzer._parse_json_response(raw_json)
    assert valid is True
    assert parsed["management_tone"] == "Optimistic"

    wrapped = '```json\n{"executive_summary": "Robust quarter", "management_tone": "Bullish"}\n```'
    parsed2, valid2 = analyzer._parse_json_response(wrapped)
    assert valid2 is True
    assert parsed2["management_tone"] == "Bullish"


def test_transcript_analyzer_deterministic_synthesis(mock_db):
    """Test TranscriptAnalyzer rule-based synthesis fallback."""
    db, _, _ = mock_db
    analyzer = TranscriptAnalyzer(db_manager=db)

    doc = {"report_period": "Q1-FY25", "file_name": "TCS_Concall.pdf"}
    chunks = [
        {"content": "TCS witnessed strong growth in digital services and record deal wins across all markets."},
        {"content": "Enterprise clients are cautious regarding discretionary spending due to inflation and macro headwinds."},
    ]

    analysis = analyzer._generate_deterministic_analysis(doc, chunks)
    assert "executive_summary" in analysis
    assert "forward_guidance" in analysis
    assert analysis["management_tone"] in ["Optimistic", "Cautious", "Neutral"]
    assert len(analysis["key_developments"]) > 0
    assert len(analysis["risk_headwinds"]) > 0


def test_api_analyze_concall_document(client):
    """Test POST /api/documents/{document_id}/analyze endpoint."""
    dummy_analysis = {
        "success": True,
        "document_id": 1,
        "model_used": "phi3:mini",
        "duration_seconds": 1.5,
        "analysis": {
            "executive_summary": "Strong quarterly performance driven by digital services.",
            "forward_guidance": "Management guided for 7-9% revenue growth in FY26.",
            "management_tone": "Bullish",
            "key_developments": ["Cloud contracts up 18%"],
            "risk_headwinds": ["Forex volatility"],
        },
        "cached": False,
    }

    with patch.object(TranscriptAnalyzer, "analyze_document", return_value=dummy_analysis):
        resp = client.post("/api/documents/1/analyze")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["document_id"] == 1
        assert "analysis" in data
        assert data["analysis"]["management_tone"] == "Bullish"


def test_favicon_endpoint(client):
    """Test GET /favicon.ico returns 200 with icon media type."""
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.headers["content-type"] in ["image/x-icon", "image/svg+xml", "image/vnd.microsoft.icon"]

