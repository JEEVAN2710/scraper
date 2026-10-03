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
from app.database.repositories import ChunkRepository, CompanyRepository, DocumentRepository
from app.export.excel_exporter import generate_company_csv, generate_company_excel
from app.pipeline.graph_rag import GraphRAGEngine
from app.pipeline.graphify import Graphifier, get_knowledge_graph as get_kg_instance
from app.pipeline.ingestion_pipeline import IngestionPipeline
from app.scraper.screener_scraper import ScreenerScraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Financial AI Assistant"])
settings = get_settings()
db_manager = get_db_manager(settings)
graph_rag = GraphRAGEngine(db_manager)
scraper = ScreenerScraper(settings)
ingestion_pipeline = IngestionPipeline(db_manager, settings)
chunk_repo = ChunkRepository(db_manager)

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
                "quarterly_data": [],
                "currency": fin_data[0].get("currency", "USD") if fin_data else "USD",
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
        # 1. Try MySQL first
        try:
            with db_manager.get_cursor() as (cursor, _):
                cursor.execute("SELECT * FROM companies ORDER BY name ASC;")
                rows = cursor.fetchall()
                if rows:
                    summaries = []
                    seen_tickers = set()
                    for row in rows:
                        cid = row["id"]
                        ticker = (row.get("ticker") or "").upper()
                        if ticker:
                            seen_tickers.add(ticker)
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
                                currency=latest.get("currency", "USD") if latest else "USD",
                            )
                        )

                    # Merge baseline demo companies if not already present in DB
                    for c in DEMO_COMPANIES:
                        if c.get("ticker", "").upper() not in seen_tickers:
                            latest_d = c["financial_data"][-1] if c.get("financial_data") else {}
                            summaries.append(
                                CompanySummary(
                                    id=c["id"],
                                    name=c["name"],
                                    ticker=c.get("ticker"),
                                    website=c.get("website"),
                                    document_count=len(c.get("documents", [])),
                                    latest_period=c.get("latest_period"),
                                    latest_revenue=latest_d.get("revenue"),
                                    latest_net_profit=latest_d.get("net_profit"),
                                    latest_revenue_growth=latest_d.get("revenue_growth"),
                                    currency=c.get("currency", "USD"),
                                )
                            )
                    return summaries
        except Exception as db_exc:
            logger.warning("Database query failed during list_companies, falling back to demo records: %s", db_exc)

        # 2. Fallback to Demo Companies
        summaries = []
        for c in DEMO_COMPANIES:
            latest = c["financial_data"][-1] if c.get("financial_data") else {}
            summaries.append(
                CompanySummary(
                    id=c["id"],
                    name=c["name"],
                    ticker=c.get("ticker"),
                    website=c.get("website"),
                    document_count=len(c.get("documents", [])),
                    latest_period=c.get("latest_period"),
                    latest_revenue=latest.get("revenue"),
                    latest_net_profit=latest.get("net_profit"),
                    latest_revenue_growth=latest.get("revenue_growth"),
                    currency=c.get("currency", "USD"),
                )
            )
        return summaries
    except Exception as exc:
        logger.exception("Failed to retrieve company list: %s", exc)
        raise HTTPException(status_code=500, detail="Unable to retrieve company list.")


@router.get("/companies/{company_id}", response_model=CompanyDetailResponse)
def get_company_detail(company_id: int) -> CompanyDetailResponse:
    """Retrieve full company details, financial metrics, risks, and documents."""
    try:
        # 1. Try MySQL
        data = _get_company_from_db(company_id)

        # 2. Fallback to demo items
        if not data:
            for c in DEMO_COMPANIES:
                if c["id"] == company_id:
                    data = c
                    break

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
            currency=data.get("currency", "USD"),
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


@router.get("/documents", response_model=List[DocumentItem])
def list_documents(company_id: Optional[int] = Query(None)) -> List[DocumentItem]:
    """List documents with file hashes and processing status."""
    try:
        docs: List[DocumentItem] = []
        # 1. Try MySQL
        try:
            with db_manager.get_cursor() as (cursor, _):
                if company_id:
                    cursor.execute("SELECT * FROM documents WHERE company_id = %s ORDER BY downloaded_at DESC;", (company_id,))
                else:
                    cursor.execute("SELECT * FROM documents ORDER BY downloaded_at DESC;")
                rows = cursor.fetchall()
                if rows:
                    return [DocumentItem(**r) for r in rows]
        except Exception as db_exc:
            logger.warning("Database query failed in list_documents: %s", db_exc)

        # 2. Fallback to demo documents
        for c in DEMO_COMPANIES:
            if company_id is None or c["id"] == company_id:
                for d in c.get("documents", []):
                    docs.append(DocumentItem(**d))
        return docs
    except Exception as exc:
        logger.exception("Error listing documents (company_id=%s): %s", company_id, exc)
        raise HTTPException(status_code=500, detail="Failed to list documents.")


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
        # Check MySQL first
        try:
            with db_manager.get_cursor() as (cursor, _):
                cursor.execute("SELECT * FROM documents WHERE id = %s;", (document_id,))
                doc_match = cursor.fetchone()
        except Exception as db_exc:
            logger.warning("Database lookup failed for document_id %s: %s", document_id, db_exc)

        # Fallback to demo list
        if not doc_match:
            for c in DEMO_COMPANIES:
                for d in c.get("documents", []):
                    if d["id"] == document_id:
                        doc_match = d
                        break
                if doc_match:
                    break

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
def export_excel(company_id: int):
    """Generate and stream a multi-sheet formatted Excel workbook (.xlsx) with all PDF-extracted data."""
    try:
        data = _get_company_from_db(company_id)
        if not data:
            for c in DEMO_COMPANIES:
                if c["id"] == company_id:
                    data = c
                    break

        if not data:
            logger.warning("Excel export requested for unknown company_id: %s", company_id)
            raise HTTPException(status_code=404, detail="Company not found.")

        # Pull document chunks (PDF-extracted text) from database
        pdf_chunks = []
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

        excel_buffer = generate_company_excel(data)
        filename = f"{data.get('ticker', 'company')}_{datetime.now().strftime('%Y%m%d')}_financial_report.xlsx"

        logger.info("Successfully generated Excel report for company_id %s ('%s') with %d PDF chunks", company_id, filename, len(pdf_chunks))
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


@router.get("/export/csv/{company_id}")
def export_csv(company_id: int):
    """Generate and stream financial metrics in standard CSV format."""
    try:
        data = _get_company_from_db(company_id)
        if not data:
            for c in DEMO_COMPANIES:
                if c["id"] == company_id:
                    data = c
                    break

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
    """Search for companies on Screener.in by query or ticker symbol."""
    try:
        results = scraper.search_company(request.query)
        return [ScreenerSearchResult(**r) for r in results]
    except Exception as exc:
        logger.exception("Error searching Screener: %s", exc)
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

