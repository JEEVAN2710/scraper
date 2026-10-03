"""Repository layer providing parameterized data access for MySQL tables with robust error handling."""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from app.database.connection import DatabaseManager, get_db_manager

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with shared DatabaseManager reference."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or get_db_manager()


class CompanyRepository(BaseRepository):
    """Repository for managing company records."""

    def create(
        self,
        name: str,
        ticker: Optional[str] = None,
        website: Optional[str] = None,
        about: Optional[str] = None,
        sector: Optional[str] = None,
        ratios_json: Optional[str] = None,
    ) -> int:
        """Insert a company and return its new primary key ID."""
        if about is not None or sector is not None or ratios_json is not None:
            query = """
                INSERT INTO companies (name, ticker, website, about, sector, ratios_json)
                VALUES (%s, %s, %s, %s, %s, %s);
            """
            params = (name, ticker, website, about, sector, ratios_json)
        else:
            query = """
                INSERT INTO companies (name, ticker, website)
                VALUES (%s, %s, %s);
            """
            params = (name, ticker, website)

        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, params)
                new_id = cursor.lastrowid
                logger.info("Created company '%s' (ticker: %s) with ID: %s", name, ticker, new_id)
                return new_id
        except Exception as exc:
            logger.exception("Failed to insert company '%s' (ticker: %s): %s", name, ticker, exc)
            raise

    def update_metadata(
        self,
        company_id: int,
        about: Optional[str] = None,
        sector: Optional[str] = None,
        ratios_json: Optional[str] = None,
    ) -> None:
        """Update company profile about, sector, and ratios."""
        updates = []
        params = []
        if about is not None:
            updates.append("about = %s")
            params.append(about)
        if sector is not None:
            updates.append("sector = %s")
            params.append(sector)
        if ratios_json is not None:
            updates.append("ratios_json = %s")
            params.append(ratios_json)
        if not updates:
            return
        params.append(company_id)
        query = f"UPDATE companies SET {', '.join(updates)} WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, tuple(params))
        except Exception as exc:
            logger.warning("Failed to update company metadata for %s: %s", company_id, exc)

    def get_by_id(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a company record by primary key."""
        query = "SELECT * FROM companies WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (company_id,))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to query company by ID %s: %s", company_id, exc)
            raise

    def get_by_ticker(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch a company record by unique ticker."""
        query = "SELECT * FROM companies WHERE ticker = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (ticker,))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to query company by ticker '%s': %s", ticker, exc)
            raise

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Fetch a company record by exact name."""
        query = "SELECT * FROM companies WHERE name = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (name,))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to query company by name '%s': %s", name, exc)
            raise

    def get_or_create(
        self,
        name: str,
        ticker: Optional[str] = None,
        website: Optional[str] = None,
        about: Optional[str] = None,
        sector: Optional[str] = None,
        ratios_json: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch existing company by ticker or name, or create if not present."""
        try:
            existing = None
            if ticker:
                existing = self.get_by_ticker(ticker)
            if not existing:
                existing = self.get_by_name(name)

            if existing:
                if about or sector or ratios_json:
                    self.update_metadata(existing["id"], about=about, sector=sector, ratios_json=ratios_json)
                    existing = self.get_by_id(existing["id"]) or existing
                return existing

            new_id = self.create(name=name, ticker=ticker, website=website, about=about, sector=sector, ratios_json=ratios_json)
            created = self.get_by_id(new_id)
            if created is None:
                raise RuntimeError(f"Failed to retrieve company immediately after creation (id={new_id}).")
            return created
        except Exception as exc:
            logger.exception("Failed get_or_create for company '%s' (ticker: %s): %s", name, ticker, exc)
            raise

    def list_all(self) -> List[Dict[str, Any]]:
        """List all registered companies."""
        query = "SELECT * FROM companies ORDER BY name ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query)
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list companies from database: %s", exc)
            raise


class DocumentRepository(BaseRepository):
    """Repository for managing PDF documents and duplicate detection."""

    def create(
        self,
        company_id: int,
        file_name: str,
        local_path: str,
        file_hash: str,
        file_url: Optional[str] = None,
        document_type: str = "annual_report",
        report_period: Optional[str] = None,
        report_date: Optional[str] = None,
        processing_status: str = "downloaded",
    ) -> int:
        """Insert a document record and return its primary key ID."""
        query = """
            INSERT INTO documents (
                company_id, file_name, file_url, local_path, file_hash,
                document_type, report_period, report_date, processing_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(
                    query,
                    (
                        company_id,
                        file_name,
                        file_url,
                        local_path,
                        file_hash,
                        document_type,
                        report_period,
                        report_date,
                        processing_status,
                    ),
                )
                doc_id = cursor.lastrowid
                logger.info(
                    "Inserted document '%s' (hash: %s, company_id: %s) with ID: %s",
                    file_name,
                    file_hash[:16],
                    company_id,
                    doc_id,
                )
                return doc_id
        except Exception as exc:
            logger.exception(
                "Failed to insert document '%s' for company_id %s: %s",
                file_name,
                company_id,
                exc,
            )
            raise

    def get_by_id(self, document_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a document by ID."""
        query = "SELECT * FROM documents WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id,))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to query document by ID %s: %s", document_id, exc)
            raise

    def get_by_hash(self, file_hash: str) -> Optional[Dict[str, Any]]:
        """Find an existing document by SHA-256 hash (used for duplicate detection)."""
        query = "SELECT * FROM documents WHERE file_hash = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (file_hash,))
                result = cursor.fetchone()
                if result:
                    logger.info("Found existing document matching hash %s (ID: %s)", file_hash[:16], result.get("id"))
                return result
        except Exception as exc:
            logger.exception("Failed to query document by hash '%s': %s", file_hash[:16], exc)
            raise

    def update_status(
        self,
        document_id: int,
        status: str,
        processed_at: Optional[datetime] = None,
    ) -> bool:
        """Update processing status and optional completion timestamp."""
        try:
            if processed_at:
                query = """
                    UPDATE documents
                    SET processing_status = %s, processed_at = %s
                    WHERE id = %s;
                """
                params = (status, processed_at, document_id)
            else:
                query = "UPDATE documents SET processing_status = %s WHERE id = %s;"
                params = (status, document_id)

            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, params)
                success = cursor.rowcount > 0
                logger.info("Updated document %s status to '%s' (success=%s)", document_id, status, success)
                return success
        except Exception as exc:
            logger.exception("Failed to update status for document %s: %s", document_id, exc)
            raise

    def list_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """List all documents for a specific company."""
        query = "SELECT * FROM documents WHERE company_id = %s ORDER BY created_at DESC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (company_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list documents for company_id %s: %s", company_id, exc)
            raise


class ProcessingLogRepository(BaseRepository):
    """Repository for auditing pipeline execution stages and error diagnosis."""

    def log(
        self,
        stage: str,
        status: str,
        document_id: Optional[int] = None,
        message: Optional[str] = None,
        error_details: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> int:
        """Insert an audit log entry."""
        query = """
            INSERT INTO processing_logs (
                document_id, stage, status, message, error_details, completed_at
            ) VALUES (%s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(
                    query,
                    (document_id, stage, status, message, error_details, completed_at),
                )
                log_id = cursor.lastrowid
                logger.debug("Logged stage '%s' status '%s' (log ID: %s)", stage, status, log_id)
                return log_id
        except Exception as exc:
            logger.exception(
                "Failed to insert processing log entry (stage='%s', status='%s'): %s",
                stage,
                status,
                exc,
            )
            raise

    def list_by_document(self, document_id: int) -> List[Dict[str, Any]]:
        """Fetch audit log history for a specific document."""
        query = "SELECT * FROM processing_logs WHERE document_id = %s ORDER BY started_at ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to retrieve logs for document_id %s: %s", document_id, exc)
            raise


class FinancialDataRepository(BaseRepository):
    """Repository for storing and querying structured financial metrics."""

    def create(
        self,
        document_id: int,
        company_id: int,
        period: str,
        revenue: Optional[float] = None,
        revenue_growth: Optional[float] = None,
        net_profit: Optional[float] = None,
        profit_growth: Optional[float] = None,
        operating_profit: Optional[float] = None,
        operating_margin: Optional[float] = None,
        eps: Optional[float] = None,
        total_assets: Optional[float] = None,
        total_liabilities: Optional[float] = None,
        cash_flow: Optional[float] = None,
        currency: str = "USD",
    ) -> int:
        """Insert a single financial metric row."""
        query = """
            INSERT INTO financial_data (
                document_id, company_id, period, revenue, revenue_growth,
                net_profit, profit_growth, operating_profit, operating_margin,
                eps, total_assets, total_liabilities, cash_flow, currency
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(
                    query,
                    (
                        document_id,
                        company_id,
                        period,
                        revenue,
                        revenue_growth,
                        net_profit,
                        profit_growth,
                        operating_profit,
                        operating_margin,
                        eps,
                        total_assets,
                        total_liabilities,
                        cash_flow,
                        currency,
                    ),
                )
                new_id = cursor.lastrowid
                logger.info("Inserted financial data for company_id %s, period %s (ID: %s)", company_id, period, new_id)
                return new_id
        except Exception as exc:
            logger.exception("Failed to insert financial data for company_id %s: %s", company_id, exc)
            raise

    def create_batch(self, items: List[Dict[str, Any]]) -> int:
        """Insert multiple financial metric rows."""
        count = 0
        for item in items:
            self.create(**item)
            count += 1
        return count

    def list_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """List all financial metrics for a specific company."""
        query = "SELECT * FROM financial_data WHERE company_id = %s ORDER BY period ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (company_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list financial data for company_id %s: %s", company_id, exc)
            raise


class RiskFactorRepository(BaseRepository):
    """Repository for storing and querying extracted risk factors with citations."""

    def create(
        self,
        document_id: int,
        company_id: int,
        risk: str,
        description: Optional[str] = None,
        page_number: Optional[int] = None,
    ) -> int:
        """Insert a single risk factor disclosure."""
        query = """
            INSERT INTO risk_factors (document_id, company_id, risk, description, page_number)
            VALUES (%s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id, company_id, risk, description, page_number))
                new_id = cursor.lastrowid
                logger.info("Inserted risk '%s' for company_id %s (ID: %s)", risk[:30], company_id, new_id)
                return new_id
        except Exception as exc:
            logger.exception("Failed to insert risk factor for company_id %s: %s", company_id, exc)
            raise

    def create_batch(self, items: List[Dict[str, Any]]) -> int:
        """Insert multiple risk factors."""
        count = 0
        for item in items:
            self.create(**item)
            count += 1
        return count

    def list_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """List all risk factors for a company."""
        query = "SELECT * FROM risk_factors WHERE company_id = %s ORDER BY page_number ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (company_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list risk factors for company_id %s: %s", company_id, exc)
            raise


class ChunkRepository(BaseRepository):
    """Repository for managing document text chunks."""

    def create(
        self,
        document_id: int,
        chunk_index: int,
        page_start: int,
        page_end: int,
        content: str,
    ) -> int:
        """Insert a single document chunk."""
        query = """
            INSERT INTO document_chunks (document_id, chunk_index, page_start, page_end, content)
            VALUES (%s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id, chunk_index, page_start, page_end, content))
                return cursor.lastrowid
        except Exception as exc:
            logger.exception("Failed to insert document chunk for document_id %s: %s", document_id, exc)
            raise

    def create_batch(self, items: List[Dict[str, Any]]) -> int:
        """Insert multiple document chunks."""
        count = 0
        for item in items:
            self.create(**item)
            count += 1
        return count

    def list_by_document(self, document_id: int) -> List[Dict[str, Any]]:
        """List all chunks for a document."""
        query = "SELECT * FROM document_chunks WHERE document_id = %s ORDER BY chunk_index ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list chunks for document_id %s: %s", document_id, exc)
            raise

