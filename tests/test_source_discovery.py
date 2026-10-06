"""Unit and integration tests for SourceDiscovery, AutomationService, deduplication, and API endpoint."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.models import AutomationRunResponse
from app.config.settings import Settings
from app.database.connection import DatabaseManager
from app.main import app
from app.pipeline.automation_service import AutomationService
from app.scraper.models import DiscoveredDocument, DownloadedDocument
from app.scraper.pdf_downloader import PDFDownloader
from app.scraper.source_discovery import (
    GenericWebProvider,
    ScreenerProvider,
    SourceDiscoveryRegistry,
)


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


def test_screener_provider_discovery():
    """Verify ScreenerProvider extracts annual reports and concall transcripts as DiscoveredDocuments."""
    mock_html = """
    <html>
    <body>
        <h1>Tata Consultancy Services Ltd</h1>
        <div class="documents">
            <a href="https://www.bseindia.com/xml-data/corpfiling/AttachHis/tcs_ar2024.pdf">Annual Report 2024</a>
        </div>
        <div class="concalls">
            <li>
                <div class="ink-600">Q1 FY25</div>
                <a href="https://example.com/tcs_transcript_q1.pdf">Transcript</a>
            </li>
        </div>
    </body>
    </html>
    """
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html
    mock_client.get.return_value = mock_response

    provider = ScreenerProvider()
    docs = provider.discover(
        source_url="https://www.screener.in/company/TCS/consolidated/",
        company_identifier="TCS",
        client=mock_client,
    )

    assert len(docs) == 2
    types = [d.document_type for d in docs]
    assert "ANNUAL_REPORT" in types
    assert "CONCALL_TRANSCRIPT" in types

    ar = next(d for d in docs if d.document_type == "ANNUAL_REPORT")
    assert ar.company_identifier == "TCS"
    assert "tcs_ar2024.pdf" in ar.url
    assert ar.source_name == "screener"


def test_generic_web_provider_discovery_and_filtering():
    """Verify GenericWebProvider filters out irrelevant links and classifies valid filings."""
    mock_html = """
    <html>
    <body>
        <h2>Investor Relations</h2>
        <ul>
            <li><a href="/reports/Annual_Report_FY24.pdf">Annual Report FY24</a></li>
            <li><a href="/financials/Q2_Results_2024.pdf">Q2 Financial Results 2024</a></li>
            <li><a href="/policies/privacy_policy.pdf">Privacy Policy</a></li>
            <li><a href="/careers/recruitment_form.pdf">Job Recruitment Guide</a></li>
        </ul>
    </body>
    </html>
    """
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = mock_html
    mock_client.get.return_value = mock_response

    provider = GenericWebProvider(source_type="investor_relations")
    docs = provider.discover(
        source_url="https://example.com/investors/",
        company_identifier="TEST",
        client=mock_client,
    )

    # Privacy policy and job form should be excluded
    assert len(docs) == 2
    urls = [d.url for d in docs]
    assert "https://example.com/reports/Annual_Report_FY24.pdf" in urls
    assert "https://example.com/financials/Q2_Results_2024.pdf" in urls
    assert not any("privacy" in u for u in urls)
    assert not any("recruitment" in u for u in urls)


def test_source_discovery_registry():
    """Verify registry resolves known source types and falls back gracefully."""
    registry = SourceDiscoveryRegistry()
    assert isinstance(registry.get_provider("screener"), ScreenerProvider)
    assert isinstance(registry.get_provider("company_website"), GenericWebProvider)
    assert isinstance(registry.get_provider("investor_relations"), GenericWebProvider)
    # Fallback
    assert isinstance(registry.get_provider("unknown_portal"), GenericWebProvider)


def test_automation_service_run_and_two_tier_deduplication(tmp_path):
    """Test full AutomationService workflow: discovery, URL deduplication, and SHA-256 deduplication."""
    mock_db = MagicMock(spec=DatabaseManager)
    cursor = MagicMock()
    conn = MagicMock()
    mock_db.get_cursor.return_value.__enter__.return_value = (cursor, conn)

    settings = Settings()
    settings.DOWNLOAD_DIR = tmp_path / "downloads"

    # Setup mock repositories inside service
    service = AutomationService(db_manager=mock_db, settings=settings)

    # 1. Setup mock data
    service.automation_repo.get_by_id = MagicMock(return_value={
        "id": 1,
        "company_id": 10,
        "name": "Daily TCS Sync",
        "source_id": None,
    })
    service.company_repo.get_by_id = MagicMock(return_value={
        "id": 10,
        "name": "Tata Consultancy Services Ltd",
        "ticker": "TCS",
    })
    service.source_repo.list_by_company = MagicMock(return_value=[{
        "id": 5,
        "source_type": "screener",
        "source_url": "https://www.screener.in/company/TCS/",
        "is_active": True,
    }])
    service.run_repo.create = MagicMock(return_value=101)
    service.run_repo.update_status = MagicMock()
    service.automation_repo.update_schedule = MagicMock()
    service.source_repo.update_polled = MagicMock()
    service.log_repo.log = MagicMock()

    # Create 3 candidate documents:
    # Cand 1: New URL, New SHA-256 (should download and store)
    # Cand 2: Duplicate URL (should skip immediately)
    # Cand 3: Different URL, but duplicate SHA-256 (should detect duplicate & delete staging)
    cand1 = DiscoveredDocument(
        url="https://example.com/doc1.pdf",
        source_url="https://example.com",
        title="Annual Report 2024",
        document_type="ANNUAL_REPORT",
    )
    cand2 = DiscoveredDocument(
        url="https://example.com/already_saved.pdf",
        source_url="https://example.com",
        title="Existing Report",
        document_type="ANNUAL_REPORT",
    )
    cand3 = DiscoveredDocument(
        url="https://example.com/mirror/doc1_mirror.pdf",
        source_url="https://example.com",
        title="Mirror Report",
        document_type="ANNUAL_REPORT",
    )

    mock_provider = MagicMock()
    mock_provider.discover.return_value = [cand1, cand2, cand3]
    service.registry.get_provider = MagicMock(return_value=mock_provider)

    # Tier 1 URL check behavior:
    # cand2 returns an existing document record; others return None
    def mock_get_by_url(company_id, file_url):
        if file_url == "https://example.com/already_saved.pdf":
            return {"id": 99, "file_url": file_url}
        return None
    service.doc_repo.get_by_url = MagicMock(side_effect=mock_get_by_url)

    # Downloader behavior
    mock_dl_file1 = tmp_path / "downloads" / "TCS_Annual_Report_2024_11111111.pdf"
    mock_dl_file1.write_bytes(b"%PDF-1.4 new unique content")

    mock_dl_file3 = tmp_path / "downloads" / "TCS_Mirror_Report_22222222.pdf"
    mock_dl_file3.write_bytes(b"%PDF-1.4 duplicate content")

    def mock_download(url, preferred_name, company_identifier):
        if "doc1.pdf" in url:
            return DownloadedDocument(
                url=url,
                local_path=str(mock_dl_file1),
                file_name=mock_dl_file1.name,
                file_size=len(mock_dl_file1.read_bytes()),
                sha256="1111111122222222333333334444444455555555666666667777777788888888",
            )
        elif "doc1_mirror.pdf" in url:
            return DownloadedDocument(
                url=url,
                local_path=str(mock_dl_file3),
                file_name=mock_dl_file3.name,
                file_size=len(mock_dl_file3.read_bytes()),
                sha256="3333333344444444555555556666666677777777888888889999999900000000",  # Duplicate hash
            )
        raise ValueError("Unexpected download URL")

    service.downloader.download = MagicMock(side_effect=mock_download)

    # Tier 2 SHA-256 check behavior:
    # cand1 hash returns None (new); cand3 hash returns existing record (duplicate)
    def mock_get_by_hash(sha256):
        if sha256.startswith("33333333"):
            return {"id": 88, "file_hash": sha256}
        return None
    service.doc_repo.get_by_hash = MagicMock(side_effect=mock_get_by_hash)
    service.doc_repo.create = MagicMock(return_value=201)

    # Execute
    result = service.run_automation(automation_id=1, trigger_type="manual")

    # Assertions
    assert result["run_id"] == 101
    assert result["status"] == "completed"
    assert result["documents_discovered"] == 3
    assert result["documents_downloaded"] == 1  # Only cand1 was newly downloaded & saved
    assert result["duplicates"] == 2            # cand2 (URL match) + cand3 (SHA-256 match)
    assert result["documents_failed"] == 0

    # Ensure cand1 was stored
    service.doc_repo.create.assert_called_once()
    assert service.doc_repo.create.call_args[1]["company_id"] == 10
    assert service.doc_repo.create.call_args[1]["file_hash"] == "1111111122222222333333334444444455555555666666667777777788888888"

    # Ensure duplicate file for cand3 was removed from disk
    assert not mock_dl_file3.exists()


def test_api_run_automation_endpoint(client):
    """Test POST /api/automations/{id}/run route handler."""
    mock_run_result = {
        "run_id": 42,
        "automation_id": 1,
        "company_id": 5,
        "status": "completed",
        "documents_discovered": 5,
        "documents_downloaded": 2,
        "duplicates": 3,
        "documents_failed": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": datetime.now().isoformat(),
        "message": "Completed successfully.",
    }

    with patch("app.api.routes.automation_service.run_automation", return_value=mock_run_result):
        resp = client.post("/api/automations/1/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == 42
        assert data["status"] == "completed"
        assert data["documents_downloaded"] == 2
        assert data["duplicates"] == 3


def test_api_run_automation_not_found(client):
    """Test POST /api/automations/{id}/run returns 404 when automation does not exist."""
    with patch(
        "app.api.routes.automation_service.run_automation",
        side_effect=ValueError("Automation with ID 999 not found."),
    ):
        resp = client.post("/api/automations/999/run")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
