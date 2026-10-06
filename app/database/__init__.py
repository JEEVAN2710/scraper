"""Database package for Financial AI Assistant."""

from app.database.connection import DatabaseManager, get_db_manager
from app.database.migrations.runner import run_migrations
from app.database.repositories import (
    BaseRepository,
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
    OperationalMetricRepository,
    sort_fiscal_periods,
)

__all__ = [
    "DatabaseManager",
    "get_db_manager",
    "run_migrations",
    "BaseRepository",
    "CompanyRepository",
    "CompanySourceRepository",
    "AutomationRepository",
    "AutomationRunRepository",
    "ExtractionRunRepository",
    "DocumentRepository",
    "ProcessingLogRepository",
    "FinancialDataRepository",
    "RiskFactorRepository",
    "ChunkRepository",
    "OperationalMetricRepository",
    "sort_fiscal_periods",
]
