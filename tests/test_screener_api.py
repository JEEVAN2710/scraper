"""API integration tests for Screener search and ingestion endpoints."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_screener_search(client):
    """Test POST /api/scrape/search endpoint."""
    mock_results = [
        {"id": 1489, "name": "Infosys Ltd", "ticker": "INFY", "url": "/company/INFY/consolidated/"}
    ]

    with patch("app.api.routes.scraper.search_company", return_value=mock_results):
        res = client.post("/api/scrape/search", json={"query": "INFY"})
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "INFY"
        assert data[0]["name"] == "Infosys Ltd"


def test_api_screener_search_get(client):
    """Test GET /api/scrape/search and /api/screener/search endpoints."""
    mock_results = [
        {"id": 1284789, "name": "AWFIS Space Solutions Ltd", "ticker": "AWFIS", "url": "/company/AWFIS/consolidated/"}
    ]

    with patch("app.api.routes.scraper.search_company", return_value=mock_results):
        res = client.get("/api/scrape/search?q=awfis")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AWFIS"
        assert data[0]["name"] == "AWFIS Space Solutions Ltd"

        res2 = client.get("/api/screener/search?q=awfis")
        assert res2.status_code == 200
        assert res2.json()[0]["ticker"] == "AWFIS"


def test_api_screener_ingest_mock(client):
    """Test POST /api/scrape/ingest endpoint with mock pipeline."""
    mock_ingestion_res = {
        "success": True,
        "company_id": 4,
        "document_id": 5,
        "name": "Infosys Ltd",
        "ticker": "INFY",
        "website": "https://www.infosys.com",
        "currency": "INR",
        "pdf_name": "INFY_Annual_Report.pdf",
        "file_hash": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "metrics_count": 4,
        "risks_count": 6,
        "chunks_count": 312,
        "stages": ["Scraped", "Downloaded", "Extracted", "Ingested"],
        "duration_seconds": 3.5,
        "error": None,
    }

    with patch("app.api.routes.ingestion_pipeline.run_screener_ingestion", return_value=mock_ingestion_res):
        res = client.post("/api/scrape/ingest", json={"query": "INFY"})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["ticker"] == "INFY"
        assert data["metrics_count"] == 4
        assert data["risks_count"] == 6
