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
        is_active: bool = True,
        tracking_tier: str = "standard",
    ) -> int:
        if (
            about is not None
            or sector is not None
            or ratios_json is not None
            or not is_active
            or tracking_tier != "standard"
        ):
            query = """
                INSERT INTO companies (name, ticker, website, about, sector, ratios_json, is_active, tracking_tier)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """
            params = (name, ticker, website, about, sector, ratios_json, is_active, tracking_tier)
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

    def set_active(self, company_id: int, is_active: bool) -> bool:
        """Set whether a company is actively monitored."""
        query = "UPDATE companies SET is_active = %s WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (is_active, company_id))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to set is_active=%s for company %s: %s", is_active, company_id, exc)
            raise

    def set_tracking_tier(self, company_id: int, tier: str) -> bool:
        """Set company monitoring tier ('standard' or 'priority')."""
        query = "UPDATE companies SET tracking_tier = %s WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (tier, company_id))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to set tracking_tier=%s for company %s: %s", tier, company_id, exc)
            raise

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
        is_active: bool = True,
        tracking_tier: str = "standard",
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

            new_id = self.create(
                name=name,
                ticker=ticker,
                website=website,
                about=about,
                sector=sector,
                ratios_json=ratios_json,
                is_active=is_active,
                tracking_tier=tracking_tier,
            )
            created = self.get_by_id(new_id)
            if created is None:
                raise RuntimeError(f"Failed to retrieve company immediately after creation (id={new_id}).")
            return created
        except Exception as exc:
            logger.exception("Failed get_or_create for company '%s' (ticker: %s): %s", name, ticker, exc)
            raise

    def list_all(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """List registered companies."""
        if active_only:
            query = "SELECT * FROM companies WHERE is_active = TRUE ORDER BY name ASC;"
        else:
            query = "SELECT * FROM companies ORDER BY name ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query)
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list companies from database: %s", exc)
            raise

    def delete(self, company_id: int, delete_files: bool = True) -> bool:
        """Cascade delete a company and all related records, files, and knowledge graph entries."""
        try:
            # 1. Fetch document paths and IDs for this company
            doc_records = []
            with self.db.get_cursor() as (cursor, _):
                cursor.execute("SELECT id, local_path FROM documents WHERE company_id = %s;", (company_id,))
                doc_records = cursor.fetchall()

            doc_ids = [d["id"] for d in doc_records if d.get("id")]
            file_paths = [d.get("local_path") for d in doc_records if d.get("local_path")]

            with self.db.get_cursor() as (cursor, _):
                if doc_ids:
                    format_strings = ",".join(["%s"] * len(doc_ids))
                    try:
                        cursor.execute(f"DELETE FROM extraction_runs WHERE document_id IN ({format_strings});", tuple(doc_ids))
                    except Exception:
                        pass
                    cursor.execute(f"DELETE FROM document_chunks WHERE document_id IN ({format_strings});", tuple(doc_ids))
                    try:
                        cursor.execute(f"DELETE FROM processing_logs WHERE document_id IN ({format_strings});", tuple(doc_ids))
                    except Exception:
                        pass

                cursor.execute("DELETE FROM risk_factors WHERE company_id = %s;", (company_id,))
                cursor.execute("DELETE FROM financial_data WHERE company_id = %s;", (company_id,))

                try:
                    cursor.execute(
                        "DELETE FROM automation_runs WHERE automation_id IN (SELECT id FROM automations WHERE company_id = %s);",
                        (company_id,),
                    )
                    cursor.execute("DELETE FROM automations WHERE company_id = %s;", (company_id,))
                except Exception:
                    pass

                try:
                    cursor.execute("DELETE FROM company_sources WHERE company_id = %s;", (company_id,))
                except Exception:
                    pass

                try:
                    cursor.execute("DELETE FROM operational_metrics WHERE company_id = %s;", (company_id,))
                except Exception:
                    pass

                cursor.execute("DELETE FROM documents WHERE company_id = %s;", (company_id,))
                cursor.execute("DELETE FROM companies WHERE id = %s;", (company_id,))
                deleted = cursor.rowcount > 0

            # 2. Delete physical files from disk if requested
            if delete_files and file_paths:
                from pathlib import Path
                for fp_str in file_paths:
                    try:
                        fp = Path(fp_str)
                        if not fp.is_absolute():
                            fp = Path.cwd() / fp
                        if fp.exists() and fp.is_file():
                            fp.unlink(missing_ok=True)
                            logger.info("Deleted document file on disk: %s", fp)
                    except Exception as f_err:
                        logger.warning("Could not delete file %s on disk: %s", fp_str, f_err)

            # 3. Synchronize Knowledge Graph
            try:
                from app.pipeline.graphify import Graphifier, get_knowledge_graph
                kg = get_knowledge_graph(self.db.settings)
                graphifier = Graphifier(self.db, kg, self.db.settings)
                graphifier.graphify_from_db()
                logger.info("Knowledge Graph re-synchronized after deleting company %s", company_id)
            except Exception as g_err:
                logger.debug("Non-fatal graph reload notice after company delete: %s", g_err)

            logger.info("Successfully deleted company ID %s and associated data", company_id)
            return deleted
        except Exception as exc:
            logger.exception("Failed to delete company %s: %s", company_id, exc)
            raise


class CompanySourceRepository(BaseRepository):
    """Repository for managing multi-source document ingestion origins."""

    def create(
        self,
        company_id: int,
        source_type: str,
        source_url: str,
        is_active: bool = True,
        config_json: Optional[str] = None,
    ) -> int:
        """Register a document source for a company."""
        query = """
            INSERT INTO company_sources (company_id, source_type, source_url, is_active, config_json)
            VALUES (%s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (company_id, source_type, source_url, is_active, config_json))
                new_id = cursor.lastrowid
                logger.info(
                    "Registered source %s (type: %s) for company %s (ID: %s)",
                    source_url,
                    source_type,
                    company_id,
                    new_id,
                )
                return new_id
        except Exception as exc:
            logger.exception("Failed to insert company source for company %s: %s", company_id, exc)
            raise

    def get_by_id(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a source by its primary key ID."""
        query = "SELECT * FROM company_sources WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (source_id,))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to get company source by ID %s: %s", source_id, exc)
            raise

    def list_by_company(self, company_id: int, active_only: bool = False) -> List[Dict[str, Any]]:
        """List configured sources for a company."""
        if active_only:
            query = "SELECT * FROM company_sources WHERE company_id = %s AND is_active = TRUE ORDER BY created_at ASC;"
        else:
            query = "SELECT * FROM company_sources WHERE company_id = %s ORDER BY created_at ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (company_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list sources for company %s: %s", company_id, exc)
            raise

    def update_polled(self, source_id: int, last_polled_at: Optional[datetime] = None) -> bool:
        """Update the last_polled_at timestamp for a source."""
        ts = last_polled_at or datetime.now()
        query = "UPDATE company_sources SET last_polled_at = %s WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (ts, source_id))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to update last_polled_at for source %s: %s", source_id, exc)
            raise

    def set_active(self, source_id: int, is_active: bool) -> bool:
        """Enable or disable a company source."""
        query = "UPDATE company_sources SET is_active = %s WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (is_active, source_id))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to set is_active=%s for source %s: %s", is_active, source_id, exc)
            raise

    def delete(self, source_id: int) -> bool:
        """Delete a company source."""
        query = "DELETE FROM company_sources WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (source_id,))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to delete company source %s: %s", source_id, exc)
            raise


class AutomationRepository(BaseRepository):
    """Repository for managing scheduled and recurring discovery automations."""

    def create(
        self,
        company_id: int,
        name: str,
        schedule_type: str = "manual",
        schedule_expression: Optional[str] = None,
        source_id: Optional[int] = None,
        is_active: bool = True,
        max_retries: int = 3,
    ) -> int:
        """Register a new automation rule."""
        query = """
            INSERT INTO automations (
                company_id, source_id, name, schedule_type,
                schedule_expression, is_active, max_retries
            ) VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(
                    query,
                    (company_id, source_id, name, schedule_type, schedule_expression, is_active, max_retries),
                )
                new_id = cursor.lastrowid
                logger.info("Created automation '%s' (type: %s) with ID: %s", name, schedule_type, new_id)
                return new_id
        except Exception as exc:
            logger.exception("Failed to create automation '%s': %s", name, exc)
            raise

    def get_by_id(self, automation_id: int) -> Optional[Dict[str, Any]]:
        """Fetch automation by primary key ID."""
        query = "SELECT * FROM automations WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (automation_id,))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to get automation by ID %s: %s", automation_id, exc)
            raise

    def list_by_company(self, company_id: int, active_only: bool = False) -> List[Dict[str, Any]]:
        """List automations for a given company."""
        if active_only:
            query = "SELECT * FROM automations WHERE company_id = %s AND is_active = TRUE ORDER BY created_at DESC;"
        else:
            query = "SELECT * FROM automations WHERE company_id = %s ORDER BY created_at DESC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (company_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list automations for company %s: %s", company_id, exc)
            raise

    def list_all(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """List all automations."""
        if active_only:
            query = "SELECT * FROM automations WHERE is_active = TRUE ORDER BY name ASC;"
        else:
            query = "SELECT * FROM automations ORDER BY name ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query)
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list all automations: %s", exc)
            raise

    def list_due(self, current_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Fetch active scheduled automations that are due to run."""
        ts = current_time or datetime.now()
        query = """
            SELECT * FROM automations 
            WHERE is_active = TRUE 
              AND schedule_type != 'manual' 
              AND next_run_at IS NOT NULL 
              AND next_run_at <= %s 
            ORDER BY next_run_at ASC;
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (ts,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list due automations: %s", exc)
            raise

    def update_schedule(
        self,
        automation_id: int,
        last_run_at: Optional[datetime] = None,
        next_run_at: Optional[datetime] = None,
    ) -> bool:
        """Update last_run_at and next_run_at for an automation."""
        updates = []
        params = []
        if last_run_at is not None:
            updates.append("last_run_at = %s")
            params.append(last_run_at)
        if next_run_at is not None:
            updates.append("next_run_at = %s")
            params.append(next_run_at)
        if not updates:
            return False
        params.append(automation_id)
        query = f"UPDATE automations SET {', '.join(updates)} WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, tuple(params))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to update schedule for automation %s: %s", automation_id, exc)
            raise

    def set_active(self, automation_id: int, is_active: bool) -> bool:
        """Enable or disable an automation."""
        query = "UPDATE automations SET is_active = %s WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (is_active, automation_id))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to set is_active=%s for automation %s: %s", is_active, automation_id, exc)
            raise

    def delete(self, automation_id: int) -> bool:
        """Delete an automation."""
        query = "DELETE FROM automations WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (automation_id,))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to delete automation %s: %s", automation_id, exc)
            raise


class AutomationRunRepository(BaseRepository):
    """Repository for recording automation run instances and execution metrics."""

    def create(self, automation_id: int, trigger_type: str = "manual") -> int:
        """Create a new automation run entry with pending status."""
        query = """
            INSERT INTO automation_runs (automation_id, trigger_type, status)
            VALUES (%s, %s, 'pending');
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (automation_id, trigger_type))
                run_id = cursor.lastrowid
                logger.info(
                    "Created automation run %s for automation %s (trigger: %s)",
                    run_id,
                    automation_id,
                    trigger_type,
                )
                return run_id
        except Exception as exc:
            logger.exception("Failed to create automation run for automation %s: %s", automation_id, exc)
            raise

    def get_by_id(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Fetch automation run by primary key ID."""
        query = "SELECT * FROM automation_runs WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (run_id,))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to get automation run by ID %s: %s", run_id, exc)
            raise

    def list_by_automation(self, automation_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """List runs for a given automation, ordered most recent first."""
        query = "SELECT * FROM automation_runs WHERE automation_id = %s ORDER BY started_at DESC LIMIT %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (automation_id, limit))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list runs for automation %s: %s", automation_id, exc)
            raise

    def update_status(
        self,
        run_id: int,
        status: str,
        error_message: Optional[str] = None,
        docs_discovered: Optional[int] = None,
        docs_downloaded: Optional[int] = None,
        docs_processed: Optional[int] = None,
        completed_at: Optional[datetime] = None,
    ) -> bool:
        """Update run status, discovery/processing counters, and error message."""
        updates = ["status = %s"]
        params: List[Any] = [status]

        if error_message is not None:
            updates.append("error_message = %s")
            params.append(error_message)
        if docs_discovered is not None:
            updates.append("documents_discovered = %s")
            params.append(docs_discovered)
        if docs_downloaded is not None:
            updates.append("documents_downloaded = %s")
            params.append(docs_downloaded)
        if docs_processed is not None:
            updates.append("documents_processed = %s")
            params.append(docs_processed)
        if completed_at is not None:
            updates.append("completed_at = %s")
            params.append(completed_at)
        elif status in ("completed", "failed", "cancelled") and completed_at is None:
            updates.append("completed_at = %s")
            params.append(datetime.now())

        params.append(run_id)
        query = f"UPDATE automation_runs SET {', '.join(updates)} WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, tuple(params))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to update status for automation run %s: %s", run_id, exc)
            raise


class ExtractionRunRepository(BaseRepository):
    """Repository for auditing LLM extraction executions, token counts, and schema validation results."""

    def create(
        self,
        document_id: int,
        model_name: str,
        raw_response: str,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        is_valid: bool = False,
        validation_errors: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> int:
        """Record an LLM extraction attempt."""
        query = """
            INSERT INTO extraction_runs (
                document_id, model_name, raw_response, prompt_tokens,
                completion_tokens, is_valid, validation_errors, duration_seconds
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(
                    query,
                    (
                        document_id,
                        model_name,
                        raw_response,
                        prompt_tokens,
                        completion_tokens,
                        is_valid,
                        validation_errors,
                        duration_seconds,
                    ),
                )
                run_id = cursor.lastrowid
                logger.info(
                    "Recorded extraction run %s for doc %s (model: %s, valid: %s)",
                    run_id,
                    document_id,
                    model_name,
                    is_valid,
                )
                return run_id
        except Exception as exc:
            logger.exception("Failed to record extraction run for doc %s: %s", document_id, exc)
            raise

    def get_by_id(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Fetch extraction run by primary key ID."""
        query = "SELECT * FROM extraction_runs WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (run_id,))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to get extraction run by ID %s: %s", run_id, exc)
            raise

    def list_by_document(self, document_id: int) -> List[Dict[str, Any]]:
        """List all extraction runs for a document, ordered newest first."""
        query = "SELECT * FROM extraction_runs WHERE document_id = %s ORDER BY created_at DESC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list extraction runs for document %s: %s", document_id, exc)
            raise


class DocumentRepository(BaseRepository):
    """Repository for managing PDF documents, metadata, and duplicate detection."""

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
        source_id: Optional[int] = None,
        file_size_bytes: Optional[int] = None,
        page_count: Optional[int] = None,
        text_density_score: Optional[float] = None,
    ) -> int:
        """Insert a document record and return its primary key ID."""
        query = """
            INSERT INTO documents (
                company_id, file_name, file_url, local_path, file_hash,
                document_type, report_period, report_date, processing_status,
                source_id, file_size_bytes, page_count, text_density_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
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
                        source_id,
                        file_size_bytes,
                        page_count,
                        text_density_score,
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

    def get_by_url(self, company_id: int, file_url: str) -> Optional[Dict[str, Any]]:
        """Find an existing document by company ID and file URL (used for URL-level duplicate detection)."""
        query = "SELECT * FROM documents WHERE company_id = %s AND file_url = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (company_id, file_url))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to query document by URL for company %s: %s", company_id, exc)
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

    def update_metadata(
        self,
        document_id: int,
        file_size_bytes: Optional[int] = None,
        page_count: Optional[int] = None,
        text_density_score: Optional[float] = None,
    ) -> bool:
        """Update document technical metadata (file size, page count, density score)."""
        updates = []
        params = []
        if file_size_bytes is not None:
            updates.append("file_size_bytes = %s")
            params.append(file_size_bytes)
        if page_count is not None:
            updates.append("page_count = %s")
            params.append(page_count)
        if text_density_score is not None:
            updates.append("text_density_score = %s")
            params.append(text_density_score)
        if not updates:
            return False
        params.append(document_id)
        query = f"UPDATE documents SET {', '.join(updates)} WHERE id = %s;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, tuple(params))
                return cursor.rowcount > 0
        except Exception as exc:
            logger.exception("Failed to update metadata for document %s: %s", document_id, exc)
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

    def list_by_status(self, status: str) -> List[Dict[str, Any]]:
        """List all documents currently in a given processing status."""
        query = "SELECT * FROM documents WHERE processing_status = %s ORDER BY created_at ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (status,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list documents by status '%s': %s", status, exc)
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
        automation_run_id: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> int:
        """Insert an audit log entry."""
        query = """
            INSERT INTO processing_logs (
                document_id, stage, status, message, error_details, completed_at,
                automation_run_id, duration_ms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(
                    query,
                    (
                        document_id,
                        stage,
                        status,
                        message,
                        error_details,
                        completed_at,
                        automation_run_id,
                        duration_ms,
                    ),
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

    def list_by_automation_run(self, automation_run_id: int) -> List[Dict[str, Any]]:
        """Fetch audit log history for a specific automation run."""
        query = "SELECT * FROM processing_logs WHERE automation_run_id = %s ORDER BY started_at ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (automation_run_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to retrieve logs for automation_run_id %s: %s", automation_run_id, exc)
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
        extraction_run_id: Optional[int] = None,
        confidence_score: float = 1.0,
        source_page: Optional[int] = None,
    ) -> int:
        """Insert a single financial metric row."""
        query = """
            INSERT INTO financial_data (
                document_id, company_id, period, revenue, revenue_growth,
                net_profit, profit_growth, operating_profit, operating_margin,
                eps, total_assets, total_liabilities, cash_flow, currency,
                extraction_run_id, confidence_score, source_page
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
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
                        extraction_run_id,
                        confidence_score,
                        source_page,
                    ),
                )
                new_id = cursor.lastrowid
                logger.info(
                    "Inserted financial data for company_id %s, period %s (ID: %s)",
                    company_id,
                    period,
                    new_id,
                )
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

    def list_by_document(self, document_id: int) -> List[Dict[str, Any]]:
        """List all financial data for a specific document."""
        query = "SELECT * FROM financial_data WHERE document_id = %s ORDER BY period ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list financial data for document_id %s: %s", document_id, exc)
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
        extraction_run_id: Optional[int] = None,
        severity: str = "medium",
        confidence_score: float = 1.0,
    ) -> int:
        """Insert a single risk factor disclosure."""
        query = """
            INSERT INTO risk_factors (
                document_id, company_id, risk, description, page_number,
                extraction_run_id, severity, confidence_score
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(
                    query,
                    (
                        document_id,
                        company_id,
                        risk,
                        description,
                        page_number,
                        extraction_run_id,
                        severity,
                        confidence_score,
                    ),
                )
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

    def list_by_document(self, document_id: int) -> List[Dict[str, Any]]:
        """List all risk factors for a specific document."""
        query = "SELECT * FROM risk_factors WHERE document_id = %s ORDER BY page_number ASC;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id,))
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to list risk factors for document_id %s: %s", document_id, exc)
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
        word_count: Optional[int] = None,
        is_ocr: bool = False,
    ) -> int:
        """Insert a single document chunk."""
        query = """
            INSERT INTO document_chunks (
                document_id, chunk_index, page_start, page_end, content, word_count, is_ocr
            ) VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id, chunk_index, page_start, page_end, content, word_count, is_ocr))
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


class ExtractionRunRepository(BaseRepository):
    """Repository for managing LLM extraction runs and structured audit records."""

    def create(
        self,
        document_id: int,
        model_name: str,
        raw_response: str,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        is_valid: bool = True,
        validation_errors: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> int:
        """Insert an LLM extraction audit run."""
        query = """
            INSERT INTO extraction_runs (
                document_id, model_name, raw_response, prompt_tokens,
                completion_tokens, is_valid, validation_errors, duration_seconds
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(
                    query,
                    (
                        document_id,
                        model_name,
                        raw_response,
                        prompt_tokens,
                        completion_tokens,
                        is_valid,
                        validation_errors,
                        duration_seconds,
                    ),
                )
                return cursor.lastrowid
        except Exception as exc:
            logger.exception("Failed to insert extraction run for document %s: %s", document_id, exc)
            raise

    def get_latest_by_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        """Fetch the latest extraction run for a document."""
        query = "SELECT * FROM extraction_runs WHERE document_id = %s ORDER BY created_at DESC LIMIT 1;"
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, (document_id,))
                return cursor.fetchone()
        except Exception as exc:
            logger.exception("Failed to get extraction run for document %s: %s", document_id, exc)
            return None


def sort_fiscal_periods(periods: List[str]) -> List[str]:
    """Sort fiscal quarters chronologically (e.g. Q3 FY24, Q4 FY24, Q1 FY25 ... Q1 FY27)."""
    import re

    def period_key(p: str):
        m = re.search(r"Q([1-4])\s*FY(\d{2,4})", p, re.IGNORECASE)
        if m:
            q = int(m.group(1))
            yr = int(m.group(2))
            if yr < 100:
                yr += 2000
            return (yr, q)
        month_map = {"mar": 4, "jun": 1, "sep": 2, "dec": 3}
        m2 = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(\d{4})", p, re.IGNORECASE)
        if m2:
            mon = m2.group(1).lower()
            yr = int(m2.group(2))
            q = month_map.get(mon, 1)
            fy = yr if mon == "mar" else yr + 1
            return (fy, q)
        return (9999, 9)

    return sorted(list(set(periods)), key=period_key)


def format_fiscal_period_display(period: str) -> str:
    """Format a fiscal period like 'Q1 FY27' into a clear calendar-annotated label 'Q1 FY27 (Jun \\'26)'."""
    import re
    m = re.search(r"Q([1-4])\s*FY(\d{2,4})", period, re.IGNORECASE)
    if not m:
        return period
    q = int(m.group(1))
    yr = int(m.group(2))
    if yr < 100:
        full_yr = 2000 + yr
        short_yr = yr
    else:
        full_yr = yr
        short_yr = yr % 100

    # In Indian FY (April - March):
    # Q1 ends June 30 of calendar year (full_yr - 1)
    # Q2 ends Sept 30 of calendar year (full_yr - 1)
    # Q3 ends Dec 31 of calendar year (full_yr - 1)
    # Q4 ends Mar 31 of calendar year full_yr
    if q == 1:
        cal_yr = (full_yr - 1) % 100
        return f"Q1 FY{short_yr:02d} (Jun '{cal_yr:02d})"
    elif q == 2:
        cal_yr = (full_yr - 1) % 100
        return f"Q2 FY{short_yr:02d} (Sep '{cal_yr:02d})"
    elif q == 3:
        cal_yr = (full_yr - 1) % 100
        return f"Q3 FY{short_yr:02d} (Dec '{cal_yr:02d})"
    elif q == 4:
        cal_yr = short_yr
        return f"Q4 FY{short_yr:02d} (Mar '{cal_yr:02d})"
    return period


class OperationalMetricRepository(BaseRepository):
    """Repository for managing multi-quarter operational metrics and sector KPIs."""

    # Default category ordering and highlights for standardized presentation
    STANDARDIZED_STRUCTURE = [
        {
            "category": "Financials",
            "metrics": [
                {"name": "Revenue from Ops", "unit": "₹ Cr", "is_highlight": True},
                {"name": "Operating Expenses", "unit": "₹ Cr", "is_highlight": False},
                {"name": "Operating EBITDA", "unit": "₹ Cr", "is_highlight": False},
                {"name": "Op. EBITDA Margin %", "unit": "%", "is_highlight": True},
                {"name": "Other Income", "unit": "₹ Cr", "is_highlight": False},
                {"name": "Interest / Finance Costs", "unit": "₹ Cr", "is_highlight": False},
                {"name": "Depreciation", "unit": "₹ Cr", "is_highlight": False},
                {"name": "Profit before tax (PBT)", "unit": "₹ Cr", "is_highlight": False},
                {"name": "Effective Tax Rate %", "unit": "%", "is_highlight": False},
                {"name": "Reported PAT", "unit": "₹ Cr", "is_highlight": True},
                {"name": "Diluted EPS", "unit": "₹", "is_highlight": False},
            ],
        },
        {
            "category": "Operational Disclosures",
            "metrics": [
                {"name": "Total Headcount", "unit": "Employees", "is_highlight": True},
                {"name": "LTM Attrition %", "unit": "%", "is_highlight": False},
                {"name": "Order Inflow / Deal TCV", "unit": "₹ Cr", "is_highlight": True},
                {"name": "Store Count", "unit": "Stores", "is_highlight": True},
                {"name": "SSSG %", "unit": "%", "is_highlight": False},
                {"name": "Capacity Utilization %", "unit": "%", "is_highlight": False},
            ],
        },
        {
            "category": "Capacity & Footprint",
            "metrics": [
                {"name": "Signed Supply Centers", "unit": "Centers", "is_highlight": False},
                {"name": "Signed Supply Seats", "unit": "Seats", "is_highlight": True},
                {"name": "Signed Supply Area (LOI)", "unit": "Mn Sq. Ft.", "is_highlight": False},
                {"name": "Total Centers", "unit": "Centers", "is_highlight": False},
                {"name": "Total Seats", "unit": "Seats", "is_highlight": False},
                {"name": "Operational Seats", "unit": "Seats", "is_highlight": True},
                {"name": "MA Portfolio %", "unit": "%", "is_highlight": False},
            ],
        },
        {
            "category": "Occupancy & Tenure",
            "metrics": [
                {"name": "Blended Occupancy %", "unit": "%", "is_highlight": True},
                {"name": ">12m Vintage Occ. %", "unit": "%", "is_highlight": False},
                {"name": "W. Avg Total Tenure", "unit": "Months", "is_highlight": False},
                {"name": "Active Clients", "unit": "Clients", "is_highlight": False},
                {"name": "% Multi-Center Clients", "unit": "%", "is_highlight": False},
            ],
        },
        {
            "category": "Client Concentration & Size",
            "metrics": [
                {"name": "100+ Seats (Enterprise)", "unit": "%", "is_highlight": True},
                {"name": "51-100 Seats", "unit": "%", "is_highlight": False},
                {"name": "1-50 Seats", "unit": "%", "is_highlight": False},
                {"name": ">= 24 Months", "unit": "%", "is_highlight": False},
                {"name": "12-23 Months", "unit": "%", "is_highlight": False},
                {"name": "< 12 Months", "unit": "%", "is_highlight": False},
            ],
        },
        {
            "category": "Industry Sector Concentration",
            "metrics": [
                {"name": "IT / ITeS", "unit": "%", "is_highlight": False},
                {"name": "BFSI", "unit": "%", "is_highlight": False},
                {"name": "Consulting / Professional", "unit": "%", "is_highlight": False},
                {"name": "Others", "unit": "%", "is_highlight": False},
            ],
        },
        {
            "category": "Segment Revenue Breakdown",
            "metrics": [
                {"name": "Co-working & Allied Revenue", "unit": "₹ Cr", "is_highlight": True},
                {"name": "Construction & Fit-out Revenue", "unit": "₹ Cr", "is_highlight": True},
                {"name": "Others Revenue", "unit": "₹ Cr", "is_highlight": False},
                {"name": "Rental", "unit": "₹ Cr", "is_highlight": False},
            ],
        },
    ]

    def create(
        self,
        company_id: int,
        period: str,
        metric_category: str,
        metric_name: str,
        metric_value: str,
        numeric_value: Optional[float] = None,
        unit: Optional[str] = None,
        document_id: Optional[int] = None,
        source_page: Optional[int] = None,
    ) -> int:
        """Insert or update a single operational metric."""
        query = """
            INSERT INTO operational_metrics (
                company_id, document_id, period, metric_category,
                metric_name, metric_value, numeric_value, unit, source_page
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            with self.db.get_cursor() as (cursor, _):
                # Clean prior duplicate if any
                cursor.execute(
                    "DELETE FROM operational_metrics WHERE company_id = %s AND period = %s AND metric_name = %s;",
                    (company_id, period, metric_name),
                )
                cursor.execute(
                    query,
                    (
                        company_id,
                        document_id,
                        period,
                        metric_category,
                        metric_name,
                        str(metric_value),
                        numeric_value,
                        unit,
                        source_page,
                    ),
                )
                return cursor.lastrowid
        except Exception as exc:
            logger.exception("Failed to insert operational metric %s for company %s: %s", metric_name, company_id, exc)
            raise

    def create_batch(self, company_id: int, items: List[Dict[str, Any]]) -> int:
        """Insert a batch of operational metrics, replacing duplicates."""
        if not items:
            return 0
        inserted_count = 0
        try:
            with self.db.get_cursor() as (cursor, _):
                for item in items:
                    period = item.get("period", "")
                    m_name = item.get("metric_name", "")
                    if not period or not m_name:
                        continue
                    # Remove existing duplicate
                    cursor.execute(
                        "DELETE FROM operational_metrics WHERE company_id = %s AND period = %s AND metric_name = %s;",
                        (company_id, period, m_name),
                    )
                    cursor.execute(
                        """
                        INSERT INTO operational_metrics (
                            company_id, document_id, period, metric_category,
                            metric_name, metric_value, numeric_value, unit, source_page
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            company_id,
                            item.get("document_id"),
                            period,
                            item.get("metric_category", "General"),
                            m_name,
                            str(item.get("metric_value", "")),
                            item.get("numeric_value"),
                            item.get("unit"),
                            item.get("source_page"),
                        ),
                    )
                    inserted_count += 1
            return inserted_count
        except Exception as exc:
            logger.exception("Failed to batch insert operational metrics for company %s: %s", company_id, exc)
            raise

    def list_by_company(self, company_id: int, period: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all operational metrics for a company, optionally filtered by period."""
        if period:
            query = "SELECT * FROM operational_metrics WHERE company_id = %s AND period = %s ORDER BY id ASC;"
            params = (company_id, period)
        else:
            query = "SELECT * FROM operational_metrics WHERE company_id = %s ORDER BY period ASC, id ASC;"
            params = (company_id,)
        try:
            with self.db.get_cursor() as (cursor, _):
                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as exc:
            logger.exception("Failed to fetch operational metrics for company %s: %s", company_id, exc)
            return []

    def get_matrix(self, company_id: int) -> Dict[str, Any]:
        """Pivots company operational metrics into a structured multi-quarter research matrix."""
        # 1. Fetch company profile
        with self.db.get_cursor() as (cursor, _):
            cursor.execute("SELECT id, name, ticker, sector FROM companies WHERE id = %s;", (company_id,))
            company = cursor.fetchone()
        if not company:
            return {}

        # 2. Fetch all raw metrics
        rows = self.list_by_company(company_id)

        # 3. Collect unique periods and sort chronologically
        raw_periods = list({r["period"] for r in rows if r.get("period")})
        sorted_periods = sort_fiscal_periods(raw_periods)

        # 4. Build lookup table: (category, metric_name, period) -> row
        data_map: Dict[tuple, Dict[str, Any]] = {}
        for r in rows:
            cat = r.get("metric_category", "General")
            name = r.get("metric_name", "")
            prd = r.get("period", "")
            data_map[(cat, name, prd)] = r

        # Determine whether the company is in Coworking / Real Estate
        sec_text = (company.get("sector") or "").lower()
        tck_text = (company.get("ticker") or "").upper()
        is_coworking = any(k in sec_text for k in ["cowork", "workspace", "real estate", "realty"]) or tck_text in ["AWFIS", "EFCIL"]

        # 5. Populate categories according to standard schema + any custom found metrics
        categories_output = []
        visited_keys = set()

        for group in self.STANDARDIZED_STRUCTURE:
            cat_name = group["category"]
            metrics_list = []
            has_data_in_group = False

            for m_def in group["metrics"]:
                name = m_def["name"]
                unit = m_def["unit"]
                highlight = m_def["is_highlight"]

                # Extract values across periods
                values_dict = {}
                numeric_dict = {}
                has_metric_data = False
                for p in sorted_periods:
                    key = (cat_name, name, p)
                    visited_keys.add(key)
                    if key in data_map:
                        item = data_map[key]
                        values_dict[p] = item.get("metric_value", "-")
                        numeric_dict[p] = float(item["numeric_value"]) if item.get("numeric_value") is not None else None
                        has_data_in_group = True
                        has_metric_data = True
                    else:
                        values_dict[p] = "-"
                        numeric_dict[p] = None

                # Metric filtering:
                # 1. If metric has data in at least one period, always include
                # 2. If it is a coworking company and part of standard coworking categories, include to match target model
                # 3. If it is one of the 4 headline financial metrics, always include
                is_core_fin = name in ["Revenue from Ops", "Operating EBITDA", "Op. EBITDA Margin %", "Reported PAT"]
                is_cw_metric = is_coworking and cat_name in [
                    "Capacity & Footprint", "Occupancy & Tenure", "Client Concentration & Size",
                    "Industry Sector Concentration", "Segment Revenue Breakdown"
                ]
                if has_metric_data or is_cw_metric or is_core_fin:
                    metrics_list.append({
                        "name": name,
                        "unit": unit,
                        "is_highlight": highlight,
                        "values": values_dict,
                        "numeric_values": numeric_dict,
                    })

            # Include category if:
            # - It contains metrics AND (has actual data OR is a coworking company for standard coworking categories)
            if metrics_list:
                if has_data_in_group:
                    categories_output.append({
                        "category": cat_name,
                        "metrics": metrics_list,
                    })
                elif is_coworking and cat_name != "Operational Disclosures":
                    categories_output.append({
                        "category": cat_name,
                        "metrics": metrics_list,
                    })

        # Check for unmapped custom metrics
        custom_metrics_map: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for r in rows:
            cat = r.get("metric_category", "General")
            name = r.get("metric_name", "")
            prd = r.get("period", "")
            if (cat, name, prd) not in visited_keys:
                if cat not in custom_metrics_map:
                    custom_metrics_map[cat] = {}
                if name not in custom_metrics_map[cat]:
                    custom_metrics_map[cat][name] = {
                        "unit": r.get("unit", ""),
                        "is_highlight": False,
                        "values": {},
                        "numeric_values": {},
                    }
                custom_metrics_map[cat][name]["values"][prd] = r.get("metric_value", "-")
                custom_metrics_map[cat][name]["numeric_values"][prd] = (
                    float(r["numeric_value"]) if r.get("numeric_value") is not None else None
                )

        for cat, metrics_dict in custom_metrics_map.items():
            c_list = []
            for m_name, m_info in metrics_dict.items():
                v_dict = {}
                n_dict = {}
                for p in sorted_periods:
                    v_dict[p] = m_info["values"].get(p, "-")
                    n_dict[p] = m_info["numeric_values"].get(p, None)
                c_list.append({
                    "name": m_name,
                    "unit": m_info["unit"],
                    "is_highlight": False,
                    "values": v_dict,
                    "numeric_values": n_dict,
                })
            categories_output.append({
                "category": cat,
                "metrics": c_list,
            })

        period_labels = {p: format_fiscal_period_display(p) for p in sorted_periods}
        return {
            "company_id": company["id"],
            "company_name": company["name"],
            "ticker": company["ticker"],
            "sector": company["sector"],
            "periods": sorted_periods,
            "period_labels": period_labels,
            "categories": categories_output,
        }

    def get_sector_matrix(self, sector_name: Optional[str] = None) -> Dict[str, Any]:
        """Fetch stacked matrices for all companies in a sector (or all companies if unspecified)."""
        with self.db.get_cursor() as (cursor, _):
            if sector_name:
                cursor.execute(
                    "SELECT id, name, ticker FROM companies WHERE sector = %s OR sector LIKE %s ORDER BY name ASC;",
                    (sector_name, f"%{sector_name}%"),
                )
            else:
                cursor.execute("SELECT id, name, ticker FROM companies ORDER BY name ASC;")
            companies = cursor.fetchall()

        matrices = []
        all_periods = set()
        for comp in companies:
            mat = self.get_matrix(comp["id"])
            if mat:
                matrices.append(mat)
                all_periods.update(mat.get("periods", []))

        g_periods = sort_fiscal_periods(list(all_periods))
        g_period_labels = {p: format_fiscal_period_display(p) for p in g_periods}
        return {
            "sector": sector_name or "All Tracked Companies",
            "global_periods": g_periods,
            "global_period_labels": g_period_labels,
            "companies": matrices,
        }


