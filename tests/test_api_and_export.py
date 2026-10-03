"""Unit and integration tests for Excel export engine and FastAPI endpoints."""

import io
import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.api.routes import DEMO_COMPANIES
from app.export.excel_exporter import generate_company_csv, generate_company_excel
from app.main import app


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


def test_excel_export_generation():
    """Verify Excel exporter generates all 4 sheets with headers and data."""
    sample_company = DEMO_COMPANIES[0]  # TCS
    excel_buffer = generate_company_excel(sample_company)

    assert isinstance(excel_buffer, io.BytesIO)
    excel_buffer.seek(0)

    wb = openpyxl.load_workbook(excel_buffer)
    sheet_names = wb.sheetnames

    assert "Company Overview" in sheet_names
    assert "Financial Metrics" in sheet_names
    assert "Risk Factors" in sheet_names
    assert "Document Registry" in sheet_names

    # Check Overview sheet content
    ws_ov = wb["Company Overview"]
    assert "Tata Consultancy Services" in str(ws_ov["A1"].value)

    # Check Financial Metrics sheet headers
    ws_fin = wb["Financial Metrics"]
    headers = [cell.value for cell in ws_fin[1]]
    assert "Period" in headers
    assert "Revenue" in headers
    assert "Net Profit" in headers
    assert "Operating Margin" in headers

    # Verify rows exist
    assert ws_fin.max_row >= 4


def test_csv_export_generation():
    """Verify CSV string generation with valid header and values."""
    sample_company = DEMO_COMPANIES[0]
    csv_str = generate_company_csv(sample_company)

    assert "period,revenue,revenue_growth,net_profit" in csv_str
    assert "FY2024" in csv_str


def test_api_health_endpoint(client):
    """Test GET /api/health endpoint."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "mysql" in data
    assert "ollama" in data


def test_api_companies_endpoint(client):
    """Test GET /api/companies endpoint."""
    res = client.get("/api/companies")
    assert res.status_code == 200
    companies = res.json()
    assert len(companies) >= 3
    tcs = next((c for c in companies if c["ticker"] == "TCS"), None)
    assert tcs is not None
    assert "Tata Consultancy Services" in tcs["name"]


def test_api_company_detail_endpoint(client):
    """Test GET /api/companies/{id} endpoint."""
    res = client.get("/api/companies/1")
    assert res.status_code == 200
    detail = res.json()
    assert detail["id"] == 1
    assert len(detail["financial_data"]) > 0
    assert len(detail["risks"]) > 0
    assert len(detail["documents"]) > 0


def test_api_excel_download_endpoint(client):
    """Test GET /api/export/excel/{id} download response."""
    res = client.get("/api/export/excel/1")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment; filename=" in res.headers["content-disposition"]
    assert len(res.content) > 1000


def test_api_csv_download_endpoint(client):
    """Test GET /api/export/csv/{id} download response."""
    res = client.get("/api/export/csv/1")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert len(res.text) > 50


def test_api_pdf_download_endpoint(client):
    """Test GET /api/documents/{id}/download response."""
    res = client.get("/api/documents/101/download")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF-1.4")


def test_api_ask_graph_rag_endpoint(client):
    """Test POST /api/ask endpoint with Graph RAG."""
    res = client.post(
        "/api/ask",
        json={"question": "What was TCS revenue in FY2024?", "company_id": 1},
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "graph_nodes" in data
    assert "citations" in data
    assert "TCS" in str(data["graph_nodes"]) or "Tata" in str(data["graph_nodes"])
    assert len(data["answer"]) > 20


def test_api_ask_cross_company_comparison(client):
    """Test POST /api/ask cross-company comparison inquiry."""
    res = client.post(
        "/api/ask",
        json={"question": "Compare Apple and Microsoft profit margins"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["graph_nodes"]) >= 2
    assert "answer" in data
