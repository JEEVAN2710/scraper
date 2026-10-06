"""Tests for Multi-Quarter Operational Matrix, Sector Comparative Model, and Concall KPI Extractor."""

import io
from unittest.mock import MagicMock, patch
import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.database.repositories import (
    OperationalMetricRepository,
    sort_fiscal_periods,
)
from app.extraction.operational_kpi_extractor import OperationalKPIExtractor
from app.export.excel_exporter import generate_operational_matrix_excel
from app.main import app


client = TestClient(app)


def test_sort_fiscal_periods():
    """Verify fiscal quarters are sorted in exact chronological order across years."""
    raw = ["Q4 FY25", "Q1 FY24", "Q3 FY26", "Q1 FY27", "Q2 FY25", "Q3 FY24", "Q1 FY26", "Q4 FY24"]
    sorted_periods = sort_fiscal_periods(raw)
    expected = [
        "Q1 FY24",
        "Q3 FY24",
        "Q4 FY24",
        "Q2 FY25",
        "Q4 FY25",
        "Q1 FY26",
        "Q3 FY26",
        "Q1 FY27",
    ]
    assert sorted_periods == expected


def test_sort_fiscal_periods_with_screener_dates():
    """Verify fiscal sorting handles month year dates like 'Jun 2024' or 'Dec 2023'."""
    raw = ["Jun 2026", "Dec 2023", "Mar 2024", "Jun 2024", "Sep 2025"]
    sorted_p = sort_fiscal_periods(raw)
    assert sorted_p[0] == "Dec 2023" # Q3 FY24
    assert sorted_p[-1] == "Jun 2026" # Q1 FY27


def test_operational_kpi_extractor_regex_extraction():
    """Verify extraction of operational KPIs from representative concall transcript snippets."""
    mock_db = MagicMock()
    extractor = OperationalKPIExtractor(mock_db)

    sample_text = """
    We closed FY26 tall with 247 centers and nearly 175,000 seats across 18 cities,
    bringing our total capacity to around 147,000 operational seats pan-India as of September 2025.
    Our exit month occupancy stood at 74.0%, while centers operational for over 12 months achieved a robust 84% occupancy.
    Average client tenure is 36 months with an average lock-in period of 23 months.
    Our client base includes more than 3,400-plus active clients, with 44% of our clients operating across multiple centers.
    Overall 61% from 100-plus seat cohort.
    Our coworking and allied services segment grew 27% year-on-year to INR342 crores.
    Our Transform business, construction, and fit-out solutions delivered INR69 crores.
    """

    metrics = extractor.extract_metrics_from_text(sample_text, "Q2 FY26", company_id=1)
    metrics_by_name = {m["metric_name"]: m for m in metrics}

    assert ("Total Centers" in metrics_by_name or "Total Centers (Op+Fitout)" in metrics_by_name)
    tc_key = "Total Centers (Op+Fitout)" if "Total Centers (Op+Fitout)" in metrics_by_name else "Total Centers"
    assert metrics_by_name[tc_key]["numeric_value"] == 247.0

    assert "Operational Seats" in metrics_by_name
    assert metrics_by_name["Operational Seats"]["numeric_value"] == 147000.0

    assert ("Total Seats" in metrics_by_name or "Total Seats (Op+Fitout)" in metrics_by_name)
    ts_key = "Total Seats (Op+Fitout)" if "Total Seats (Op+Fitout)" in metrics_by_name else "Total Seats"
    assert metrics_by_name[ts_key]["numeric_value"] == 175000.0

    assert "Blended Occupancy %" in metrics_by_name
    assert metrics_by_name["Blended Occupancy %"]["numeric_value"] == 74.0

    assert ">12m Vintage Occ. %" in metrics_by_name
    assert metrics_by_name[">12m Vintage Occ. %"]["numeric_value"] == 84.0

    assert ("W. Avg Total Tenure" in metrics_by_name or "W. Avg Total Tenure (Mos)" in metrics_by_name)
    ten_key = "W. Avg Total Tenure (Mos)" if "W. Avg Total Tenure (Mos)" in metrics_by_name else "W. Avg Total Tenure"
    assert metrics_by_name[ten_key]["numeric_value"] == 36.0

    assert "Active Clients" in metrics_by_name
    assert metrics_by_name["Active Clients"]["numeric_value"] == 3400.0

    assert "% Multi-Center Clients" in metrics_by_name
    assert metrics_by_name["% Multi-Center Clients"]["numeric_value"] == 44.0

    assert "100+ Seats (Enterprise)" in metrics_by_name
    assert metrics_by_name["100+ Seats (Enterprise)"]["numeric_value"] == 61.0

    assert ("Co-working & Allied Revenue" in metrics_by_name or "Co-working & Allied Revenue (₹ Cr)" in metrics_by_name)
    cw_key = "Co-working & Allied Revenue (₹ Cr)" if "Co-working & Allied Revenue (₹ Cr)" in metrics_by_name else "Co-working & Allied Revenue"
    assert metrics_by_name[cw_key]["numeric_value"] == 342.0

    assert ("Construction & Fit-out Revenue" in metrics_by_name or "Construction & Fit-out Revenue (₹ Cr)" in metrics_by_name)
    fit_key = "Construction & Fit-out Revenue (₹ Cr)" if "Construction & Fit-out Revenue (₹ Cr)" in metrics_by_name else "Construction & Fit-out Revenue"
    assert metrics_by_name[fit_key]["numeric_value"] == 69.0


def test_operational_kpi_extractor_period_detection():
    """Verify fiscal quarter detection from concall filenames."""
    mock_db = MagicMock()
    extractor = OperationalKPIExtractor(mock_db)

    assert extractor.detect_period_from_text("", "AWFIS_Concall_May_2026.pdf") == "Q4 FY26"
    assert extractor.detect_period_from_text("", "AWFIS_Concall_Nov_2025.pdf") == "Q2 FY26"
    assert extractor.detect_period_from_text("", "AWFIS_Concall_Feb_2026.pdf") == "Q3 FY26"
    assert extractor.detect_period_from_text("", "AWFIS_Concall_Aug_2026.pdf") == "Q1 FY27"
    assert extractor.detect_period_from_text("", "TCS_Concall_Q3_FY25.pdf") == "Q3 FY25"


def test_generate_operational_matrix_excel():
    """Verify Excel model generator generates valid, structured multi-quarter workbook."""
    sample_matrix = {
        "company_id": 1,
        "company_name": "Awfis Space Solutions Ltd.",
        "ticker": "AWFIS",
        "periods": ["Q3 FY24", "Q4 FY24", "Q1 FY25", "Q2 FY25", "Q4 FY26"],
        "categories": [
            {
                "category": "Financials",
                "metrics": [
                    {
                        "name": "Revenue from Ops",
                        "unit": "₹ Cr",
                        "is_highlight": True,
                        "values": {"Q3 FY24": "₹221 Cr", "Q4 FY24": "₹232 Cr", "Q1 FY25": "₹258 Cr", "Q4 FY26": "₹410 Cr"},
                        "numeric_values": {"Q3 FY24": 221.0, "Q4 FY24": 232.0, "Q1 FY25": 258.0, "Q4 FY26": 410.0},
                    },
                    {
                        "name": "Reported PAT",
                        "unit": "₹ Cr",
                        "is_highlight": True,
                        "values": {"Q3 FY24": "₹-6 Cr", "Q4 FY24": "₹1 Cr", "Q1 FY25": "₹3 Cr", "Q4 FY26": "₹23 Cr"},
                        "numeric_values": {"Q3 FY24": -6.0, "Q4 FY24": 1.0, "Q1 FY25": 3.0, "Q4 FY26": 23.0},
                    },
                ],
            },
            {
                "category": "Capacity & Footprint",
                "metrics": [
                    {
                        "name": "Operational Seats",
                        "unit": "Seats",
                        "is_highlight": True,
                        "values": {"Q3 FY24": "87,349", "Q4 FY24": "95,200", "Q4 FY26": "156,000"},
                        "numeric_values": {"Q3 FY24": 87349.0, "Q4 FY24": 95200.0, "Q4 FY26": 156000.0},
                    },
                ],
            },
        ],
    }

    excel_buffer = generate_operational_matrix_excel(sample_matrix)
    assert isinstance(excel_buffer, io.BytesIO)
    content = excel_buffer.getvalue()
    assert len(content) > 1000

    # Load with openpyxl to verify workbook validity
    wb = openpyxl.load_workbook(io.BytesIO(content))
    assert "Operational Research Model" in wb.sheetnames
    ws = wb["Operational Research Model"]
    # Verify title and company banner exist
    found_company = any("Awfis" in str(ws.cell(row=r, column=1).value) for r in range(1, 10))
    assert found_company


def test_api_operational_matrix_endpoints():
    """Verify backend operational matrix API routes."""
    # Test sector matrix endpoint
    res = client.get("/api/sectors/all/operational-matrix")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "data" in data
    assert "global_periods" in data["data"]

    # Test sector excel export endpoint
    res_export = client.get("/api/export/excel/sector-matrix/all")
    assert res_export.status_code == 200
    assert "spreadsheetml.sheet" in res_export.headers.get("content-type", "")
    assert len(res_export.content) > 1000
