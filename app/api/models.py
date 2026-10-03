"""Pydantic request and response models for the FastAPI layer."""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class FinancialDataPoint(BaseModel):
    """Financial metric data point for a reporting period."""
    id: Optional[int] = None
    period: str = Field(..., description="Reporting period, e.g., FY2023, Q1-2024")
    revenue: Optional[float] = Field(None, description="Total revenue in currency units")
    revenue_growth: Optional[float] = Field(None, description="YoY or QoQ revenue growth rate")
    net_profit: Optional[float] = Field(None, description="Net profit / income")
    profit_growth: Optional[float] = Field(None, description="Net profit growth rate")
    operating_profit: Optional[float] = Field(None, description="Operating profit / EBIT")
    operating_margin: Optional[float] = Field(None, description="Operating margin percentage")
    eps: Optional[float] = Field(None, description="Earnings per share")
    total_assets: Optional[float] = Field(None, description="Total assets")
    total_liabilities: Optional[float] = Field(None, description="Total liabilities")
    cash_flow: Optional[float] = Field(None, description="Free or operating cash flow")
    currency: str = Field(default="USD", description="Currency symbol/code")


class RiskFactorItem(BaseModel):
    """Extracted risk factor with provenance page reference."""
    id: Optional[int] = None
    risk: str = Field(..., description="Risk category or concise title")
    description: Optional[str] = Field(None, description="Contextual excerpt explaining the risk")
    page_number: Optional[int] = Field(None, description="PDF source page number citation")
    period: Optional[str] = Field(None, description="Report period where risk was detected")


class DocumentItem(BaseModel):
    """PDF Document record and duplicate detection hash."""
    id: int
    company_id: int
    file_name: str
    file_url: Optional[str] = None
    local_path: str
    file_hash: str
    document_type: str = "annual_report"
    report_period: Optional[str] = None
    processing_status: str
    downloaded_at: Optional[datetime] = None


class CompanySummary(BaseModel):
    """High-level company summary card."""
    id: int
    name: str
    ticker: Optional[str] = None
    website: Optional[str] = None
    document_count: int = 0
    latest_period: Optional[str] = None
    latest_revenue: Optional[float] = None
    latest_net_profit: Optional[float] = None
    latest_revenue_growth: Optional[float] = None
    currency: str = "USD"


class CompanyDetailResponse(BaseModel):
    """Full company dossier including metrics, risks, and documents."""
    id: int
    name: str
    ticker: Optional[str] = None
    website: Optional[str] = None
    currency: str = "USD"
    latest_period: Optional[str] = None
    about: Optional[str] = None
    sector: Optional[str] = None
    ratios: Optional[Dict[str, Any]] = None
    pros: List[str] = []
    cons: List[str] = []
    quarterly_data: List[Dict[str, Any]] = []
    financial_data: List[FinancialDataPoint] = []
    risks: List[RiskFactorItem] = []
    documents: List[DocumentItem] = []


class HealthResponse(BaseModel):
    """System health check payload."""
    status: str
    app_name: str
    environment: str
    mysql: Dict[str, Any]
    ollama: Dict[str, Any]
    storage: Dict[str, bool]


class AskRequest(BaseModel):
    """Payload for asking the Financial AI Assistant a question."""
    question: str = Field(..., min_length=2, description="User financial inquiry")
    company_id: Optional[int] = Field(None, description="Optional target company ID")


class AskResponse(BaseModel):
    """Structured response from Graph RAG and local Ollama inference."""
    question: str
    answer: str
    graph_nodes: List[str] = []
    citations: List[Dict[str, Any]] = []
    llm_used: str
    ollama_available: bool


class ScreenerSearchRequest(BaseModel):
    """Request payload for Screener.in company search."""
    query: str


class ScreenerSearchResult(BaseModel):
    """Single company match from Screener search."""
    id: Optional[int] = None
    name: str
    ticker: str
    url: str


class IngestionRequest(BaseModel):
    """Request payload to initiate Screener scraping, PDF downloading, and graph ingestion."""
    query: str


class IngestionResponse(BaseModel):
    """Result of end-to-end Screener scraping and Knowledge Graph ingestion."""
    success: bool
    company_id: Optional[int] = None
    document_id: Optional[int] = None
    name: Optional[str] = None
    ticker: Optional[str] = None
    website: Optional[str] = None
    about: Optional[str] = None
    sector: Optional[str] = None
    ratios: Optional[Dict[str, Any]] = None
    pros: List[str] = []
    cons: List[str] = []
    quarterly_data: List[Dict[str, Any]] = []
    currency: Optional[str] = "INR"
    pdf_name: Optional[str] = None
    file_hash: Optional[str] = None
    metrics_count: int = 0
    risks_count: int = 0
    chunks_count: int = 0
    concalls_count: int = 0
    stages: List[str] = []
    duration_seconds: float = 0.0
    error: Optional[str] = None

