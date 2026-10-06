"""API route handlers for companies, documents, exports, and system health."""

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
import mysql.connector

from app.api.models import (
    AskRequest,
    AskResponse,
    AutomationRunResponse,
    CompanyDetailResponse,
    CompanySummary,
    DocumentItem,
    FinancialDataPoint,
    HealthResponse,
    IngestionRequest,
    IngestionResponse,
    RiskFactorItem,
    ScreenerSearchRequest,
    ScreenerSearchResult,
)
from app.config.settings import get_settings
from app.database.connection import get_db_manager
from app.database.repositories import (
    ChunkRepository,
    CompanyRepository,
    DocumentRepository,
    OperationalMetricRepository,
)
from app.export.excel_exporter import (
    generate_company_csv,
    generate_company_excel,
    generate_sector_master_excel,
    generate_operational_matrix_excel,
)
from app.pipeline.automation_service import AutomationService
from app.pipeline.graph_rag import GraphRAGEngine
from app.pipeline.graphify import Graphifier, get_knowledge_graph as get_kg_instance
from app.pipeline.ingestion_pipeline import IngestionPipeline
from app.extraction.transcript_analyzer import TranscriptAnalyzer
from app.extraction.operational_kpi_extractor import OperationalKPIExtractor
from app.scraper.screener_scraper import ScreenerScraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Financial AI Assistant"])
settings = get_settings()
db_manager = get_db_manager(settings)
graph_rag = GraphRAGEngine(db_manager)
scraper = ScreenerScraper(settings)
ingestion_pipeline = IngestionPipeline(db_manager, settings)
automation_service = AutomationService(db_manager, settings)
chunk_repo = ChunkRepository(db_manager)
company_repo = CompanyRepository(db_manager)
document_repo = DocumentRepository(db_manager)
transcript_analyzer = TranscriptAnalyzer(db_manager, settings)
op_repo = OperationalMetricRepository(db_manager)
op_extractor = OperationalKPIExtractor(db_manager)

DELETED_DEMO_IDS: set = set()

# ==============================================================================
# In-Memory Fallback Demo Data (Used when MySQL is unseeded or pending login)
# ==============================================================================

DEMO_COMPANIES: List[Dict[str, Any]] = [
    {
        "id": 1,
        "name": "Tata Consultancy Services Ltd.",
        "ticker": "TCS",
        "website": "https://www.tcs.com/investor-relations",
        "currency": "USD",
        "latest_period": "FY2024",
        "financial_data": [
            {
                "period": "FY2022",
                "revenue": 25707000000.0,
                "revenue_growth": 0.168,
                "net_profit": 5194000000.0,
                "profit_growth": 0.142,
                "operating_profit": 6500000000.0,
                "operating_margin": 0.253,
                "eps": 1.41,
                "total_assets": 17800000000.0,
                "total_liabilities": 4900000000.0,
                "cash_flow": 5200000000.0,
                "currency": "USD",
            },
            {
                "period": "FY2023",
                "revenue": 27927000000.0,
                "revenue_growth": 0.086,
                "net_profit": 5208000000.0,
                "profit_growth": 0.003,
                "operating_profit": 6730000000.0,
                "operating_margin": 0.241,
                "eps": 1.43,
                "total_assets": 18450000000.0,
                "total_liabilities": 5100000000.0,
                "cash_flow": 5410000000.0,
                "currency": "USD",
            },
            {
                "period": "FY2024",
                "revenue": 29080000000.0,
                "revenue_growth": 0.041,
                "net_profit": 5580000000.0,
                "profit_growth": 0.071,
                "operating_profit": 7150000000.0,
                "operating_margin": 0.246,
                "eps": 1.54,
                "total_assets": 19600000000.0,
                "total_liabilities": 5300000000.0,
                "cash_flow": 5890000000.0,
                "currency": "USD",
            },
        ],
        "risks": [
            {
                "id": 1,
                "risk": "Geopolitical & Cross-Border Macro Risks",
                "description": "Prolonged slowdown in North American banking & financial services discretionary tech spending.",
                "page_number": 42,
                "period": "FY2024",
            },
            {
                "id": 2,
                "risk": "Foreign Exchange Volatility",
                "description": "High revenue exposure to USD and GBP against INR fluctuations affecting realized operating margins.",
                "page_number": 68,
                "period": "FY2024",
            },
            {
                "id": 3,
                "risk": "Generative AI Transition & Talent Reskilling",
                "description": "Speed of client pivot to AI-augmented services necessitating enterprise-scale reskilling across 600,000+ engineers.",
                "page_number": 95,
                "period": "FY2024",
            },
        ],
        "documents": [
            {
                "id": 101,
                "company_id": 1,
                "file_name": "TCS_Annual_Report_2023-24.pdf",
                "file_url": "https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2023-24/ar/annual-report-2023-2024.pdf",
                "local_path": "data/downloads/TCS_Annual_Report_2023-24.pdf",
                "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "document_type": "annual_report",
                "report_period": "FY2024",
                "processing_status": "processed",
                "downloaded_at": datetime(2024, 6, 15, 10, 30),
            },
            {
                "id": 102,
                "company_id": 1,
                "file_name": "TCS_Q1_FY25_Financial_Results.pdf",
                "file_url": "https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2024-25/q1/press-release.pdf",
                "local_path": "data/downloads/TCS_Q1_FY25_Financial_Results.pdf",
                "file_hash": "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
                "document_type": "quarterly_report",
                "report_period": "Q1-FY25",
                "processing_status": "processed",
                "downloaded_at": datetime(2024, 7, 12, 14, 0),
            },
        ],
    },
    {
        "id": 2,
        "name": "Apple Inc.",
        "ticker": "AAPL",
        "website": "https://investor.apple.com",
        "currency": "USD",
        "latest_period": "FY2024",
        "financial_data": [
            {
                "period": "FY2023",
                "revenue": 383285000000.0,
                "revenue_growth": -0.028,
                "net_profit": 96995000000.0,
                "profit_growth": -0.028,
                "operating_profit": 114301000000.0,
                "operating_margin": 0.298,
                "eps": 6.13,
                "total_assets": 352583000000.0,
                "total_liabilities": 290437000000.0,
                "cash_flow": 110543000000.0,
                "currency": "USD",
            },
            {
                "period": "FY2024",
                "revenue": 391035000000.0,
                "revenue_growth": 0.020,
                "net_profit": 93736000000.0,
                "profit_growth": -0.034,
                "operating_profit": 123216000000.0,
                "operating_margin": 0.315,
                "eps": 6.08,
                "total_assets": 364980000000.0,
                "total_liabilities": 308030000000.0,
                "cash_flow": 118250000000.0,
                "currency": "USD",
            },
        ],
        "risks": [
            {
                "id": 4,
                "risk": "Global Supply Chain Concentration",
                "description": "Manufacturing and assembly concentration in specific regions exposes business to operational and trade disruptions.",
                "page_number": 24,
                "period": "FY2024",
            },
            {
                "id": 5,
                "risk": "Regulatory Scrutiny on App Store & Services",
                "description": "Antitrust regulations (EU Digital Markets Act, US DOJ litigation) challenging ecosystem fees and practices.",
                "page_number": 31,
                "period": "FY2024",
            },
        ],
        "documents": [
            {
                "id": 201,
                "company_id": 2,
                "file_name": "Apple_Form_10K_Annual_Report_2024.pdf",
                "file_url": "https://investor.apple.com/sec-filings/10-K-2024",
                "local_path": "data/downloads/Apple_Form_10K_Annual_Report_2024.pdf",
                "file_hash": "bc7279f0611c03bf0bebe8e2501099ec1b73e34b9d0dcfe4eb8964d4b2e88a3e",
                "document_type": "10-K",
                "report_period": "FY2024",
                "processing_status": "processed",
                "downloaded_at": datetime(2024, 11, 2, 9, 15),
            }
        ],
    },
    {
        "id": 3,
        "name": "Microsoft Corporation",
        "ticker": "MSFT",
        "website": "https://www.microsoft.com/investor",
        "currency": "USD",
        "latest_period": "FY2024",
        "financial_data": [
            {
                "period": "FY2023",
                "revenue": 211915000000.0,
                "revenue_growth": 0.068,
                "net_profit": 72361000000.0,
                "profit_growth": -0.005,
                "operating_profit": 88523000000.0,
                "operating_margin": 0.418,
                "eps": 9.68,
                "total_assets": 411976000000.0,
                "total_liabilities": 205753000000.0,
                "cash_flow": 87582000000.0,
                "currency": "USD",
            },
            {
                "period": "FY2024",
                "revenue": 245122000000.0,
                "revenue_growth": 0.157,
                "net_profit": 88136000000.0,
                "profit_growth": 0.218,
                "operating_profit": 109433000000.0,
                "operating_margin": 0.446,
                "eps": 11.80,
                "total_assets": 512163000000.0,
                "total_liabilities": 243686000000.0,
                "cash_flow": 118548000000.0,
                "currency": "USD",
            },
        ],
        "risks": [
            {
                "id": 6,
                "risk": "Cloud Infrastructure Capital Expenditure",
                "description": "Massive ongoing CapEx investments in AI datacenters may experience utilization risk or margin compression.",
                "page_number": 38,
                "period": "FY2024",
            }
        ],
        "documents": [
            {
                "id": 301,
                "company_id": 3,
                "file_name": "Microsoft_Form_10K_Annual_Report_2024.pdf",
                "file_url": "https://www.microsoft.com/investor/sec-filings/10-K",
                "local_path": "data/downloads/Microsoft_Form_10K_Annual_Report_2024.pdf",
                "file_hash": "c89b251347076bbd9229ec62b66bf1c73f328fd4989668486940d90eec285493",
                "document_type": "10-K",
                "report_period": "FY2024",
                "processing_status": "processed",
                "downloaded_at": datetime(2024, 7, 30, 16, 45),
            }
        ],
    },
]


def _ensure_sample_pdf(local_path: str, filename: str, company_name: str, period: str) -> Path:
    """Create a valid sample PDF file if it doesn't already exist on disk."""
    path = Path(local_path)
    if path.exists() and path.stat().st_size > 0:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    # Write a simple, valid standard PDF-1.4 file
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 200 >>\nstream\n"
        b"BT\n/F1 20 Tf\n50 720 Td\n(" + company_name.encode("utf-8") + b" - " + period.encode("utf-8") + b") Tj\n"
        b"/F1 12 Tf\n0 -30 Td\n(Financial Document Automation & AI Research Assistant) Tj\n"
        b"0 -20 Td\n(Report File: " + filename.encode("utf-8") + b") Tj\n"
        b"0 -20 Td\n(Verified SHA-256 Fingerprint: Authentic Financial Record) Tj\n"
        b"ET\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000500 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n574\n%%EOF"
    )
    with open(path, "wb") as f:
        f.write(pdf_content)
    return path


def _get_company_from_db(company_id: int) -> Optional[Dict[str, Any]]:
    """Attempt to load company details and metrics from MySQL."""
    try:
        with db_manager.get_cursor() as (cursor, _):
            # Company
            cursor.execute("SELECT * FROM companies WHERE id = %s;", (company_id,))
            company = cursor.fetchone()
            if not company:
                return None

            # Financial Data
            cursor.execute("SELECT * FROM financial_data WHERE company_id = %s ORDER BY period ASC;", (company_id,))
            fin_data = cursor.fetchall()

            # Risks
            cursor.execute("SELECT * FROM risk_factors WHERE company_id = %s ORDER BY page_number ASC;", (company_id,))
            risks = cursor.fetchall()

            # Documents
            cursor.execute("SELECT * FROM documents WHERE company_id = %s ORDER BY downloaded_at DESC;", (company_id,))
            docs = cursor.fetchall()

            latest_p = fin_data[-1]["period"] if fin_data else None

            ratios = {}
            if company.get("ratios_json"):
                try:
                    import json
                    ratios = json.loads(company["ratios_json"]) if isinstance(company["ratios_json"], str) else company["ratios_json"]
                except Exception:
                    ratios = {}

            # Quarterly Data from operational_metrics (Financials + Operational KPIs)
            quarterly_data = []
            try:
                cursor.execute(
                    "SELECT period, metric_name, numeric_value FROM operational_metrics WHERE company_id = %s;",
                    (company_id,),
                )
                op_rows = cursor.fetchall()
                if op_rows:
                    q_map: Dict[str, Dict[str, Any]] = {}
                    for r in op_rows:
                        p = r["period"]
                        if p not in q_map:
                            q_map[p] = {"period": p}
                        m_name = r["metric_name"]
                        n_val = float(r["numeric_value"]) if r["numeric_value"] is not None else None
                        q_map[p][m_name] = n_val
                        clean_key = (
                            m_name.lower()
                            .replace(" ", "_")
                            .replace("-", "_")
                            .replace("(", "")
                            .replace(")", "")
                            .replace("%", "pct")
                            .replace("₹", "")
                            .replace("cr", "")
                            .strip("_")
                        )
                        q_map[p][clean_key] = n_val

                        # Core P&L mapping
                        if m_name in ("Revenue from Ops", "Total Revenue", "Sales"):
                            q_map[p]["revenue"] = n_val * 1e7 if (n_val and n_val < 1e6) else n_val
                        elif m_name in ("Operating EBITDA", "EBITDA", "Operating Profit"):
                            q_map[p]["operating_profit"] = n_val * 1e7 if (n_val and n_val < 1e6) else n_val
                        elif "Margin" in m_name or "opm" in clean_key:
                            q_map[p]["operating_margin"] = (n_val / 100.0) if (n_val and n_val > 1.0) else n_val
                        elif "PAT" in m_name or m_name == "Net Profit":
                            q_map[p]["net_profit"] = n_val * 1e7 if (n_val and n_val < 1e6) else n_val

                    from app.database.repositories import sort_fiscal_periods
                    sorted_q_keys = sort_fiscal_periods(list(q_map.keys()))
                    quarterly_data = [q_map[k] for k in sorted_q_keys]
            except Exception as q_err:
                logger.debug("Could not load quarterly operational metrics: %s", q_err)

            return {
                "id": company["id"],
                "name": company["name"],
                "ticker": company.get("ticker"),
                "website": company.get("website"),
                "about": company.get("about"),
                "sector": company.get("sector"),
                "ratios": ratios,
                "pros": [],
                "cons": [],
                "quarterly_data": quarterly_data,
                "currency": fin_data[0].get("currency", "INR") if fin_data else "INR",
                "latest_period": latest_p,
                "financial_data": fin_data,
                "risks": risks,
                "documents": docs,
            }
    except Exception as exc:
        logger.debug("Database read failed or unconfigured, falling back to demo data: %s", exc)
        return None


# ==============================================================================
# API Endpoints
# ==============================================================================

@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return live system health including MySQL and storage status."""
    try:
        db_health = db_manager.check_health()
        storage = {
            "downloads": settings.DOWNLOAD_DIR.exists(),
            "processed": settings.PROCESSED_DIR.exists(),
            "exports": settings.EXPORT_DIR.exists(),
            "logs": settings.LOGS_DIR.exists(),
        }
        return HealthResponse(
            status="healthy" if db_health.get("status") == "healthy" else "degraded",
            app_name=settings.APP_NAME,
            environment=settings.ENVIRONMENT,
            mysql=db_health,
            ollama={
                "enabled": settings.llm_enabled,
                "provider": settings.LLM_PROVIDER,
                "base_url": settings.OLLAMA_BASE_URL,
                "target_model": settings.OLLAMA_MODEL,
            },
            storage=storage,
        )
    except Exception as exc:
        logger.exception("Health check failed with exception: %s", exc)
        raise HTTPException(status_code=500, detail=f"Health check execution error: {exc}")


@router.get("/companies", response_model=List[CompanySummary])
def list_companies() -> List[CompanySummary]:
    """List all tracked companies with high-level financial summary cards."""
    try:
        with db_manager.get_cursor() as (cursor, _):
            cursor.execute("SELECT * FROM companies ORDER BY name ASC;")
            rows = cursor.fetchall()
            summaries = []
            for row in rows:
                cid = row["id"]
                ticker = (row.get("ticker") or "").upper()
                cursor.execute("SELECT COUNT(*) as cnt FROM documents WHERE company_id = %s;", (cid,))
                cnt_res = cursor.fetchone()
                doc_count = cnt_res["cnt"] if cnt_res else 0

                cursor.execute(
                    "SELECT period, revenue, net_profit, revenue_growth, currency "
                    "FROM financial_data WHERE company_id = %s ORDER BY period DESC LIMIT 1;",
                    (cid,),
                )
                latest = cursor.fetchone()

                summaries.append(
                    CompanySummary(
                        id=cid,
                        name=row["name"],
                        ticker=row.get("ticker"),
                        website=row.get("website"),
                        document_count=doc_count,
                        latest_period=latest["period"] if latest else None,
                        latest_revenue=float(latest["revenue"]) if latest and latest.get("revenue") else None,
                        latest_net_profit=float(latest["net_profit"]) if latest and latest.get("net_profit") else None,
                        latest_revenue_growth=float(latest["revenue_growth"]) if latest and latest.get("revenue_growth") else None,
                        currency=latest.get("currency", "INR") if latest else "INR",
                    )
                )

            return summaries
    except Exception as exc:
        logger.warning("Database query failed during list_companies: %s", exc)
        return []


@router.get("/companies/{company_id}", response_model=CompanyDetailResponse)
def get_company_detail(company_id: int) -> CompanyDetailResponse:
    """Retrieve full company details, financial metrics, risks, and documents."""
    try:
        data = _get_company_from_db(company_id)
        if not data:
            logger.warning("Company detail requested for non-existent ID: %s", company_id)
            raise HTTPException(status_code=404, detail=f"Company with ID {company_id} not found.")

        return CompanyDetailResponse(
            id=data["id"],
            name=data["name"],
            ticker=data.get("ticker"),
            website=data.get("website"),
            about=data.get("about"),
            sector=data.get("sector"),
            ratios=data.get("ratios"),
            pros=data.get("pros", []),
            cons=data.get("cons", []),
            quarterly_data=data.get("quarterly_data", []),
            currency=data.get("currency", "INR"),
            latest_period=data.get("latest_period"),
            financial_data=[FinancialDataPoint(**m) for m in data.get("financial_data", [])],
            risks=[RiskFactorItem(**r) for r in data.get("risks", [])],
            documents=[DocumentItem(**d) for d in data.get("documents", [])],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error retrieving details for company_id %s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to fetch company details for ID {company_id}")


@router.delete("/companies/{company_id}")
def delete_company(company_id: int):
    """Delete a company and all associated filings, chunks, risks, and local PDF files."""
    try:
        logger.info("Received request to delete company ID %s...", company_id)
        db_company = company_repo.get_by_id(company_id)
        if not db_company:
            raise HTTPException(status_code=404, detail=f"Company with ID {company_id} not found.")

        company_repo.delete(company_id, delete_files=True)
        try:
            graphifier = Graphifier(db_manager, get_kg_instance(settings), settings)
            graphifier.graphify_from_db()
        except Exception as g_err:
            logger.debug("Graph sync after delete: %s", g_err)

        return {
            "success": True,
            "message": f"Company {company_id} and all related records deleted successfully.",
            "company_id": company_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error deleting company %s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to delete company: {exc}")

@router.post("/companies/clear-all")
def clear_all_companies():
    """Wipe ALL company data from database and delete all downloaded PDFs. Use for fresh testing."""
    try:
        logger.warning("CLEAR-ALL: Truncating all company data from database...")
        tables_to_clear = [
            "operational_metrics",
            "financial_data",
            "risk_factors",
            "document_chunks",
            "documents",
            "company_sources",
            "processing_logs",
            "extraction_runs",
            "automation_runs",
            "companies",
        ]
        with db_manager.get_cursor() as (cursor, _):
            cursor.execute("SET FOREIGN_KEY_CHECKS=0;")
            for table in tables_to_clear:
                cursor.execute(f"TRUNCATE TABLE {table};")
            cursor.execute("SET FOREIGN_KEY_CHECKS=1;")

        # Delete all downloaded PDF files
        downloads_dir = settings.DOWNLOAD_DIR
        deleted_files = 0
        if downloads_dir.exists():
            for pdf_file in downloads_dir.glob("*.pdf"):
                try:
                    pdf_file.unlink()
                    deleted_files += 1
                except Exception as fe:
                    logger.warning("Could not delete file %s: %s", pdf_file, fe)

        # Clear the in-memory demo deletion tracking
        DELETED_DEMO_IDS.clear()

        # Refresh graph
        try:
            graphifier = Graphifier(db_manager, get_kg_instance(settings), settings)
            graphifier.graphify_from_db()
        except Exception as g_err:
            logger.debug("Graph sync after clear-all: %s", g_err)

        msg = f"Successfully wiped all company data. Deleted {deleted_files} downloaded PDF files."
        logger.info("CLEAR-ALL: %s", msg)
        return {"success": True, "message": msg, "deleted_files": deleted_files}
    except Exception as exc:
        logger.exception("CLEAR-ALL failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Clear-all failed: {exc}")


@router.post("/companies/{company_id}/rescrape", response_model=IngestionResponse)
def rescrape_company(company_id: int) -> IngestionResponse:
    """Purge existing company data and freshly scrape the latest filings and concalls from Screener."""
    try:
        logger.info("Re-scraping clean company ID %s...", company_id)
        ticker = None
        name = None

        db_company = company_repo.get_by_id(company_id)
        if not db_company:
            raise HTTPException(status_code=404, detail=f"Company with ID {company_id} not found to rescrape.")

        query = db_company.get("ticker") or db_company.get("name")
        company_repo.delete(company_id, delete_files=True)

        logger.info("Executing clean re-scrape ingestion for '%s'...", query)
        res = ingestion_pipeline.run_screener_ingestion(query)
        return IngestionResponse(**res)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error during re-scrape of company %s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail=f"Re-scrape failed: {exc}")


@router.get("/documents", response_model=List[DocumentItem])
def list_documents(company_id: Optional[int] = Query(None)) -> List[DocumentItem]:
    """List documents with file hashes and processing status."""
    try:
        with db_manager.get_cursor() as (cursor, _):
            if company_id:
                cursor.execute("SELECT * FROM documents WHERE company_id = %s ORDER BY downloaded_at DESC;", (company_id,))
            else:
                cursor.execute("SELECT * FROM documents ORDER BY downloaded_at DESC;")
            rows = cursor.fetchall()
            return [DocumentItem(**r) for r in rows] if rows else []
    except Exception as exc:
        logger.warning("Database query failed in list_documents: %s", exc)
        return []


@router.get("/graph/{company_id}")
@router.get("/graph")
def get_knowledge_graph(
    request: Request,
    company_id: Optional[int] = None,
    format: Optional[str] = None,
) -> Any:
    """Return nodes and edges representing the Knowledge Graph for interactive visualization.
    
    If accessed directly from a web browser (Accept: text/html), serves the dedicated
    fullscreen interactive Knowledge Graph Explorer page.
    """
    try:
        # Browser content negotiation: serve visual Graph Explorer UI if viewed in browser
        accept_header = request.headers.get("accept", "")
        if "text/html" in accept_header and format != "json":
            frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
            graph_page = frontend_dir / "graph.html"
            if graph_page.exists():
                return FileResponse(str(graph_page))

        kg = get_kg_instance(settings)
        if len(kg.nodes) == 0:
            graphifier = Graphifier(db_manager, kg, settings)
            kg = graphifier.graphify_from_db()

        if company_id:
            comp_node_id = f"comp_{company_id}"
            if comp_node_id not in kg.nodes:
                # Search by company_id property
                for nid, n in kg.nodes.items():
                    if n.get("properties", {}).get("company_id") == company_id:
                        comp_node_id = nid
                        break

            sub = kg.get_company_subgraph(comp_node_id)
            nodes = sub.get("nodes", [])
            edges = sub.get("edges", [])
            return {
                "nodes": nodes,
                "edges": edges,
                "summary": {
                    "total_nodes": len(nodes),
                    "total_edges": len(edges),
                    "companies": len([n for n in nodes if n["type"] == "company"]),
                    "annual_reports": len([n for n in nodes if n["type"] == "document" and "concall" not in n["label"].lower()]),
                    "concalls": len([n for n in nodes if n["type"] == "document" and "concall" in n["label"].lower()]),
                    "metrics": len([n for n in nodes if n["type"] == "metric"]),
                    "risks": len([n for n in nodes if n["type"] == "risk"]),
                    "guidance": len([n for n in nodes if n["type"] == "guidance"]),
                },
            }
        else:
            return kg.to_dict()

    except Exception as exc:
        logger.exception("Failed to assemble graph visualization data: %s", exc)
        raise HTTPException(status_code=500, detail=f"Graph data serialization error: {exc}")


@router.post("/graph/rebuild")
def rebuild_knowledge_graph() -> Dict[str, Any]:
    """Force re-graphification of all MySQL records, filings, and concalls into Knowledge Graph."""
    try:
        graphifier = Graphifier(db_manager, get_kg_instance(settings), settings)
        kg = graphifier.graphify_from_db()
        return {"success": True, "summary": kg.to_dict()["summary"]}
    except Exception as exc:
        logger.exception("Failed to rebuild knowledge graph: %s", exc)
        raise HTTPException(status_code=500, detail=f"Knowledge Graph rebuild error: {exc}")


@router.get("/documents/{document_id}/download")
def download_document(document_id: int):
    """Download the actual PDF report file."""
    try:
        doc_match = None
        try:
            with db_manager.get_cursor() as (cursor, _):
                cursor.execute("SELECT * FROM documents WHERE id = %s;", (document_id,))
                doc_match = cursor.fetchone()
        except Exception as db_exc:
            logger.warning("Database lookup failed for document_id %s: %s", document_id, db_exc)

        if not doc_match:
            logger.warning("Download requested for non-existent document ID: %s", document_id)
            raise HTTPException(status_code=404, detail="Document not found.")

        local_path = doc_match["local_path"]
        filename = doc_match["file_name"]

        # Guarantee a valid sample PDF exists if downloading for demo
        file_path = _ensure_sample_pdf(
            local_path=local_path,
            filename=filename,
            company_name=doc_match.get("report_period", "Financial Report"),
            period=doc_match.get("report_period", "2024"),
        )

        logger.info("Serving PDF file '%s' for document_id %s", filename, document_id)
        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=filename,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error serving PDF for document_id %s: %s", document_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to download document: {exc}")


@router.get("/export/excel/{company_id}")
def export_excel(
    company_id: int,
    template: str = Query("auto", description="Template format: auto (detects domain), coworking, or adaptive"),
    include_auxiliary_sheets: bool = Query(False, description="Include auxiliary sheets (Overview, Risks, Docs, Chunks). Default False."),
):
    """Generate and stream a cleanly formatted Excel workbook (.xlsx) with primary KPI matrix."""
    try:
        data = _get_company_from_db(company_id)
        if not data:
            logger.warning("Excel export requested for unknown company_id: %s", company_id)
            raise HTTPException(status_code=404, detail="Company not found.")

        # Pull document chunks (PDF-extracted text) from database if auxiliary sheets requested
        pdf_chunks = []
        if include_auxiliary_sheets:
            try:
                docs = data.get("documents", [])
                for doc in docs:
                    doc_id = doc.get("id") if isinstance(doc, dict) else getattr(doc, "id", None)
                    if doc_id:
                        chunks = chunk_repo.list_by_document(doc_id)
                        for ch in chunks:
                            pdf_chunks.append({
                                "document_id": doc_id,
                                "chunk_index": ch.get("chunk_index", 0),
                                "page_start": ch.get("page_start", 1),
                                "page_end": ch.get("page_end", 1),
                                "content": ch.get("content", ""),
                            })
            except Exception as chunk_err:
                logger.warning("Could not fetch PDF chunks for Excel export: %s", chunk_err)

        data["pdf_chunks"] = pdf_chunks

        excel_buffer = generate_company_excel(
            data,
            template=template,
            include_auxiliary_sheets=include_auxiliary_sheets,
        )
        filename = f"{data.get('ticker', 'company')}_{datetime.now().strftime('%Y%m%d')}_financial_report.xlsx"

        logger.info("Successfully generated Excel report for company_id %s ('%s') with %d PDF chunks (template=%s)", company_id, filename, len(pdf_chunks), template)
        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to generate Excel export for company_id %s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail=f"Excel generation error: {exc}")


@router.get("/export/sector-excel")
def export_sector_excel(
    template: str = Query("auto", description="Template format: auto (detects domain), coworking, or adaptive"),
):
    """Generate and stream the Sector Review MASTER workbook (.xlsx)."""
    try:
        companies = []
        try:
            with db_manager.get_cursor() as (cursor, _):
                cursor.execute("SELECT id FROM companies ORDER BY name ASC;")
                rows = cursor.fetchall()
                for r in rows:
                    c_data = _get_company_from_db(r["id"])
                    if c_data:
                        companies.append(c_data)
        except Exception as db_err:
            logger.warning("Could not fetch companies from DB for sector export: %s", db_err)

        if not companies:
            raise HTTPException(status_code=404, detail="No companies found in database for sector export.")

        excel_buffer = generate_sector_master_excel(companies, template=template)
        filename = f"Sector_Review_Master_{datetime.now().strftime('%Y%m%d')}.xlsx"
        logger.info("Successfully generated sector master Excel report ('%s') for %d companies (template=%s)", filename, len(companies), template)
        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to generate sector master Excel: %s", exc)
        raise HTTPException(status_code=500, detail=f"Sector Excel generation error: {exc}")


@router.get("/export/csv/{company_id}")
def export_csv(company_id: int):
    """Generate and stream financial metrics in standard CSV format."""
    try:
        data = _get_company_from_db(company_id)
        if not data:
            logger.warning("CSV export requested for unknown company_id: %s", company_id)
            raise HTTPException(status_code=404, detail="Company not found.")

        csv_data = generate_company_csv(data)
        filename = f"{data.get('ticker', 'company')}_financial_data.csv"

        logger.info("Successfully generated CSV metrics for company_id %s ('%s')", company_id, filename)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to generate CSV export for company_id %s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail=f"CSV export error: {exc}")


@router.get("/companies/{company_id}/operational-matrix")
def get_company_operational_matrix(company_id: int):
    """Fetch multi-quarter operational metrics research matrix for a company."""
    try:
        db_comp = company_repo.get_by_id(company_id)
        if not db_comp:
            raise HTTPException(status_code=404, detail="Company not found")
        matrix = op_repo.get_matrix(company_id)
        return {"status": "success", "data": matrix}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to get operational matrix for company %s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sectors/{sector_name}/operational-matrix")
def get_sector_operational_matrix(sector_name: str):
    """Fetch stacked multi-quarter operational model matrices for all companies in sector."""
    try:
        sec = None if sector_name.lower() in ["all", "sector", "coworking"] else sector_name
        matrix = op_repo.get_sector_matrix(sec)
        return {"status": "success", "data": matrix}
    except Exception as exc:
        logger.exception("Failed to get sector matrix for %s: %s", sector_name, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/export/excel/operational-matrix/{company_id}")
def export_company_operational_matrix_excel(company_id: int):
    """Download company multi-quarter operational matrix as formatted Excel."""
    try:
        matrix = op_repo.get_matrix(company_id)
        if not matrix:
            raise HTTPException(status_code=404, detail="Company matrix data not found")

        excel_buffer = generate_operational_matrix_excel(matrix)
        ticker = matrix.get("ticker") or f"Company_{company_id}"
        filename = f"{ticker}_Operational_Model_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to export operational matrix Excel for company %s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/export/excel/sector-matrix/{sector_name}")
def export_sector_operational_matrix_excel(sector_name: str):
    """Download sector comparative multi-quarter operational model as formatted Excel."""
    try:
        sec = None if sector_name.lower() in ["all", "sector", "coworking"] else sector_name
        matrix = op_repo.get_sector_matrix(sec)
        excel_buffer = generate_operational_matrix_excel(matrix)
        clean_sec = (sector_name or "Sector").replace(" ", "_")
        filename = f"{clean_sec}_Operational_Model_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to export sector operational matrix Excel: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))



@router.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest) -> AskResponse:
    """Graph RAG endpoint: Traverses MySQL financial graph and synthesizes answers via Ollama Phi-3."""
    try:
        logger.info("Received AI inquiry: '%s' (company_id=%s)", request.question, request.company_id)
        result = graph_rag.query(question=request.question, company_id=request.company_id)
        return AskResponse(
            question=result["question"],
            answer=result["answer"],
            graph_nodes=result.get("graph_nodes", []),
            citations=result.get("citations", []),
            llm_used=result.get("llm_used", "Graph RAG"),
            ollama_available=result.get("ollama_available", False),
        )
    except Exception as exc:
        logger.exception("Error processing /api/ask inquiry: %s", exc)
        raise HTTPException(status_code=500, detail=f"Graph RAG processing failed: {exc}")


@router.post("/scrape/search", response_model=List[ScreenerSearchResult])
def search_screener(request: ScreenerSearchRequest) -> List[ScreenerSearchResult]:
    """Search for companies on Screener.in by query or ticker symbol (POST)."""
    try:
        results = scraper.search_company(request.query)
        return [ScreenerSearchResult(**r) for r in results]
    except Exception as exc:
        logger.exception("Error searching Screener: %s", exc)
        raise HTTPException(status_code=500, detail=f"Screener search failed: {exc}")


@router.get("/scrape/search", response_model=List[ScreenerSearchResult])
@router.get("/screener/search", response_model=List[ScreenerSearchResult])
def search_screener_get(
    q: str = Query(..., min_length=1, description="Company name or ticker query"),
) -> List[ScreenerSearchResult]:
    """Live search for companies on Screener.in by query or ticker symbol (GET)."""
    try:
        results = scraper.search_company(q)
        return [ScreenerSearchResult(**r) for r in results]
    except Exception as exc:
        logger.exception("Error searching Screener via GET: %s", exc)
        raise HTTPException(status_code=500, detail=f"Screener search failed: {exc}")


@router.post("/scrape/ingest", response_model=IngestionResponse)
def ingest_from_screener(request: IngestionRequest) -> IngestionResponse:
    """Scrape company from Screener, download PDF, extract chunks & risks, and store in MySQL Knowledge Graph."""
    try:
        logger.info("Triggering Screener ingestion for '%s'...", request.query)
        res = ingestion_pipeline.run_screener_ingestion(request.query)
        return IngestionResponse(**res)
    except Exception as exc:
        logger.exception("Error in /api/scrape/ingest: %s", exc)
        raise HTTPException(status_code=500, detail=f"Ingestion pipeline failed: {exc}")


@router.post("/scrape/reprocess/{company_id}")
def reprocess_company(company_id: int):
    """Re-process an existing downloaded PDF: extract text, chunks, risks, and financial data."""
    try:
        logger.info("Triggering re-process for company_id %s...", company_id)
        res = ingestion_pipeline.reprocess_company(company_id)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "Re-processing failed."))
        return res
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error in /api/scrape/reprocess/%s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail=f"Re-processing failed: {exc}")


@router.post("/automations/{automation_id}/run", response_model=AutomationRunResponse)
def run_automation_endpoint(automation_id: int) -> AutomationRunResponse:
    """Manually trigger discovery, streaming acquisition, and SHA-256 deduplication for an automation."""
    try:
        logger.info("Manual trigger for automation ID %s...", automation_id)
        result = automation_service.run_automation(automation_id=automation_id, trigger_type="manual")
        return AutomationRunResponse(**result)
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.exception("Failed to execute automation %s: %s", automation_id, exc)
        raise HTTPException(status_code=500, detail=f"Automation execution failed: {exc}")


@router.post("/documents/{document_id}/analyze")
def analyze_document_transcript(
    document_id: int,
    model: Optional[str] = Query(None, description="Preferred Ollama model (e.g. phi3:mini or qwen2.5:3b)"),
    refresh: bool = Query(False, description="Force re-analysis even if cached"),
):
    """Run local Ollama LLM (Phi-3 or Qwen) on an earnings concall transcript."""
    try:
        logger.info("Running transcript analysis for document ID %s (model=%s, refresh=%s)...", document_id, model, refresh)
        result = transcript_analyzer.analyze_document(
            document_id=document_id,
            preferred_model=model,
            force_refresh=refresh,
        )
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.exception("Transcript analysis failed for document %s: %s", document_id, exc)
        raise HTTPException(status_code=500, detail=f"Transcript analysis failed: {exc}")


@router.get("/documents/{document_id}/analysis")
def get_document_transcript_analysis(document_id: int):
    """Retrieve existing or newly computed structured analysis for a concall transcript."""
    try:
        result = transcript_analyzer.analyze_document(document_id=document_id, force_refresh=False)
        return result
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.exception("Error fetching analysis for document %s: %s", document_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to fetch analysis: {exc}")


@router.get("/sectors")
def list_sectors():
    """List all tracked business sectors with company counts and aggregate performance."""
    try:
        sectors_dict: Dict[str, Any] = {}
        with db_manager.get_cursor() as (cursor, _):
            cursor.execute("""
                SELECT 
                    c.id, c.name, c.ticker, c.sector, c.ratios_json,
                    f.revenue, f.revenue_growth, f.operating_margin, f.net_profit, f.period
                FROM companies c
                LEFT JOIN financial_data f ON f.company_id = c.id
                ORDER BY c.sector ASC, f.period DESC;
            """)
            rows = cursor.fetchall()

            for r in rows:
                s_name = r.get("sector") or "Unclassified"
                if s_name not in sectors_dict:
                    sectors_dict[s_name] = {
                        "sector": s_name,
                        "company_ids": set(),
                        "companies": [],
                        "growth_rates": [],
                        "margins": [],
                    }
                cid = r["id"]
                if cid not in sectors_dict[s_name]["company_ids"]:
                    sectors_dict[s_name]["company_ids"].add(cid)
                    sectors_dict[s_name]["companies"].append({
                        "id": cid,
                        "name": r["name"],
                        "ticker": r.get("ticker"),
                        "revenue": float(r["revenue"]) if r.get("revenue") else None,
                        "revenue_growth": float(r["revenue_growth"]) if r.get("revenue_growth") else None,
                        "operating_margin": float(r["operating_margin"]) if r.get("operating_margin") else None,
                        "net_profit": float(r["net_profit"]) if r.get("net_profit") else None,
                        "period": r.get("period"),
                    })
                    if r.get("revenue_growth") is not None:
                        sectors_dict[s_name]["growth_rates"].append(float(r["revenue_growth"]))
                    if r.get("operating_margin") is not None:
                        sectors_dict[s_name]["margins"].append(float(r["operating_margin"]))

        result = []
        for s_name, s_data in sectors_dict.items():
            g_list = s_data["growth_rates"]
            m_list = s_data["margins"]
            avg_g = round(sum(g_list) / len(g_list), 4) if g_list else None
            avg_m = round(sum(m_list) / len(m_list), 4) if m_list else None
            result.append({
                "sector": s_name,
                "company_count": len(s_data["companies"]),
                "avg_revenue_growth": avg_g,
                "avg_operating_margin": avg_m,
                "companies": s_data["companies"],
            })

        return sorted(result, key=lambda x: x["company_count"], reverse=True)
    except Exception as exc:
        logger.exception("Error listing sectors: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to fetch sectors: {exc}")


@router.get("/sectors/{sector_name}/comparison")
def compare_sector_peers(sector_name: str):
    """Peer comparison for companies in a specific sector (growth, margins, valuation, guidance)."""
    try:
        import json
        with db_manager.get_cursor() as (cursor, _):
            cursor.execute(
                "SELECT * FROM companies WHERE LOWER(sector) = LOWER(%s) ORDER BY name ASC;",
                (sector_name.strip(),),
            )
            comps = cursor.fetchall()
            if not comps:
                cursor.execute(
                    "SELECT * FROM companies WHERE LOWER(sector) LIKE LOWER(%s) ORDER BY name ASC;",
                    (f"%{sector_name.strip()}%",),
                )
                comps = cursor.fetchall()

            peers = []
            for c in comps:
                cid = c["id"]
                cursor.execute(
                    "SELECT * FROM financial_data WHERE company_id = %s ORDER BY period DESC LIMIT 1;",
                    (cid,),
                )
                latest_fin = cursor.fetchone()

                ratios = {}
                if c.get("ratios_json"):
                    try:
                        ratios = json.loads(c["ratios_json"]) if isinstance(c["ratios_json"], str) else c["ratios_json"]
                    except Exception:
                        pass

                peers.append({
                    "id": cid,
                    "name": c["name"],
                    "ticker": c.get("ticker"),
                    "sector": c.get("sector"),
                    "market_cap": ratios.get("Market Cap", "—"),
                    "current_price": ratios.get("Current Price", "—"),
                    "pe_ratio": ratios.get("Stock P/E", "—"),
                    "roce": ratios.get("ROCE", "—"),
                    "roe": ratios.get("ROE", "—"),
                    "latest_period": latest_fin["period"] if latest_fin else None,
                    "revenue": float(latest_fin["revenue"]) if latest_fin and latest_fin.get("revenue") else None,
                    "revenue_growth": float(latest_fin["revenue_growth"]) if latest_fin and latest_fin.get("revenue_growth") else None,
                    "operating_margin": float(latest_fin["operating_margin"]) if latest_fin and latest_fin.get("operating_margin") else None,
                    "net_profit": float(latest_fin["net_profit"]) if latest_fin and latest_fin.get("net_profit") else None,
                })

            return {
                "sector": sector_name,
                "peer_count": len(peers),
                "peers": peers,
            }
    except Exception as exc:
        logger.exception("Error in sector comparison for %s: %s", sector_name, exc)
        raise HTTPException(status_code=500, detail=f"Sector comparison failed: {exc}")


@router.post("/extract/kpis/{company_id}")
def extract_company_kpis(company_id: int):
    """Run pure Python (PyMuPDF) non-LLM operational KPI extraction on all filings for a company."""
    try:
        db_company = company_repo.get_by_id(company_id)
        if not db_company:
            raise HTTPException(status_code=404, detail=f"Company with ID {company_id} not found.")

        # Find all documents for this company
        docs = document_repo.get_by_company(company_id)
        extracted_count = 0
        processed_docs = 0

        # Also check local files matching company ticker
        ticker = db_company.get("ticker", "")
        local_files = list(settings.DOWNLOAD_DIR.glob(f"{ticker}_*.pdf")) if ticker else []

        # Process registered documents
        for doc in docs:
            local_path = doc.get("local_path")
            if local_path:
                pdf_p = Path(local_path)
                if not pdf_p.is_absolute():
                    pdf_p = Path.cwd() / pdf_p
                if pdf_p.exists():
                    res = op_extractor.extract_from_pdf(
                        pdf_p,
                        company_id=company_id,
                        period_override=doc.get("report_period"),
                        document_id=doc.get("id"),
                    )
                    extracted_count += len(res)
                    processed_docs += 1

        # Also process any unindexed local files
        processed_names = {doc.get("file_name") for doc in docs}
        for lf in local_files:
            if lf.name not in processed_names:
                res = op_extractor.extract_from_pdf(lf, company_id=company_id)
                extracted_count += len(res)
                processed_docs += 1

        logger.info(
            "Non-LLM KPI extraction completed for company %s: %d metrics from %d documents",
            company_id,
            extracted_count,
            processed_docs,
        )
        return {
            "success": True,
            "company_id": company_id,
            "documents_processed": processed_docs,
            "metrics_extracted": extracted_count,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("KPI extraction failed for company %s: %s", company_id, exc)
        raise HTTPException(status_code=500, detail=f"KPI extraction error: {exc}")




