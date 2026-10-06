"""Automation execution service coordinating multi-source discovery, streaming download, and SHA-256 deduplication."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.settings import Settings, get_settings
from app.database.connection import DatabaseManager, get_db_manager
from app.database.repositories import (
    AutomationRepository,
    AutomationRunRepository,
    CompanyRepository,
    CompanySourceRepository,
    DocumentRepository,
    ProcessingLogRepository,
)
from app.scraper.models import DiscoveredDocument, DownloadedDocument
from app.scraper.pdf_downloader import DownloadError, PDFDownloader
from app.scraper.source_discovery import SourceDiscoveryRegistry
from app.scraper.url_utils import sanitize_log_url

logger = logging.getLogger(__name__)


class AutomationService:
    """Orchestrates document discovery, streaming acquisition, two-tier deduplication, and execution audit trails."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        settings: Optional[Settings] = None,
        downloader: Optional[PDFDownloader] = None,
        registry: Optional[SourceDiscoveryRegistry] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.db = db_manager or get_db_manager(self.settings)

        self.automation_repo = AutomationRepository(self.db)
        self.run_repo = AutomationRunRepository(self.db)
        self.company_repo = CompanyRepository(self.db)
        self.source_repo = CompanySourceRepository(self.db)
        self.doc_repo = DocumentRepository(self.db)
        self.log_repo = ProcessingLogRepository(self.db)

        self.downloader = downloader or PDFDownloader(self.settings)
        self.registry = registry or SourceDiscoveryRegistry(self.settings)

    def run_automation(self, automation_id: int, trigger_type: str = "manual") -> Dict[str, Any]:
        """Execute document discovery and acquisition for a registered automation.

        Pipeline stages:
        1. Load automation and associated company.
        2. Create automation_run record with status='running'.
        3. Load enabled company sources.
        4. For each source, discover candidate documents.
        5. Two-tier deduplication:
           - Tier 1: URL match against existing company documents.
           - Tier 2: Stream download to staging, compute SHA-256, match hash against database.
        6. Store new unique documents with status='downloaded'.
        7. Record audit logs and update run statistics.

        Returns:
            Dict[str, Any]: Execution summary with counters and timestamps.
        """
        started_at = datetime.now()
        automation = self.automation_repo.get_by_id(automation_id)
        if not automation:
            raise ValueError(f"Automation with ID {automation_id} not found.")

        company_id = automation["company_id"]
        company = self.company_repo.get_by_id(company_id)
        if not company:
            raise ValueError(f"Company ID {company_id} associated with automation {automation_id} not found.")

        ticker = company.get("ticker") or company.get("name")[:6].upper()

        # Create automation run record
        run_id = self.run_repo.create(automation_id=automation_id, trigger_type=trigger_type)
        self.run_repo.update_status(run_id=run_id, status="running")

        total_discovered = 0
        total_downloaded = 0
        total_duplicates = 0
        total_failed = 0
        error_message = None

        try:
            # 1. Resolve Sources
            sources: List[Dict[str, Any]] = []
            if automation.get("source_id"):
                spec_source = self.source_repo.get_by_id(automation["source_id"])
                if spec_source and spec_source.get("is_active"):
                    sources.append(spec_source)
            else:
                sources = self.source_repo.list_by_company(company_id, active_only=True)

            # Auto-create default Screener source if none configured and ticker is available
            if not sources and ticker:
                default_url = f"https://www.screener.in/company/{ticker}/consolidated/"
                source_id = self.source_repo.create(
                    company_id=company_id,
                    source_type="screener",
                    source_url=default_url,
                    is_active=True,
                )
                created_source = self.source_repo.get_by_id(source_id)
                if created_source:
                    sources.append(created_source)

            # 2. Iterate Sources and Discover Candidates
            all_candidates: List[tuple[Dict[str, Any], DiscoveredDocument]] = []
            max_per_source = getattr(self.settings, "DISCOVERY_MAX_PDFS", 30)

            for source in sources:
                source_id = source["id"]
                source_type = source.get("source_type", "custom_url")
                source_url = source["source_url"]
                clean_url = sanitize_log_url(source_url)

                self.log_repo.log(
                    stage="DISCOVERY_STARTED",
                    status="started",
                    automation_run_id=run_id,
                    message=f"Polling source [{source_type}]: {clean_url}",
                )

                try:
                    provider = self.registry.get_provider(source_type)
                    candidates = provider.discover(
                        source_url=source_url,
                        company_identifier=ticker,
                        max_documents=max_per_source,
                    )
                    self.source_repo.update_polled(source_id)

                    for cand in candidates:
                        all_candidates.append((source, cand))

                    total_discovered += len(candidates)
                    self.log_repo.log(
                        stage="DISCOVERY_COMPLETED",
                        status="success",
                        automation_run_id=run_id,
                        message=f"Source [{source_type}] discovered {len(candidates)} candidate documents.",
                    )
                except Exception as src_err:
                    logger.warning("Error discovering from source %s: %s", clean_url, src_err)
                    self.log_repo.log(
                        stage="DISCOVERY_COMPLETED",
                        status="warning",
                        automation_run_id=run_id,
                        message=f"Source [{source_type}] discovery encountered error: {str(src_err)}",
                        error_details=str(src_err),
                    )

            # Update discovered count in run record
            self.run_repo.update_status(run_id=run_id, status="running", docs_discovered=total_discovered)

            # 3. Process Each Candidate: Deduplication & Download
            for source, candidate in all_candidates:
                source_id = source["id"]
                cand_log_url = sanitize_log_url(candidate.url)

                # Tier 1 Deduplication: Check if URL already registered for this company
                existing_by_url = self.doc_repo.get_by_url(company_id=company_id, file_url=candidate.url)
                if existing_by_url:
                    total_duplicates += 1
                    self.log_repo.log(
                        stage="DUPLICATE_DETECTED",
                        status="success",
                        automation_run_id=run_id,
                        document_id=existing_by_url.get("id"),
                        message=f"Skipping duplicate URL already registered (Doc ID: {existing_by_url.get('id')})",
                    )
                    continue

                # Not an existing URL -> Attempt Download
                self.log_repo.log(
                    stage="DOWNLOAD_STARTED",
                    status="started",
                    automation_run_id=run_id,
                    message=f"Downloading candidate '{candidate.title}' from {cand_log_url}",
                )

                downloaded: Optional[DownloadedDocument] = None
                try:
                    downloaded = self.downloader.download(
                        url=candidate.url,
                        preferred_name=candidate.title,
                        company_identifier=ticker,
                    )
                except DownloadError as dl_err:
                    total_failed += 1
                    logger.warning("Download failed for %s: %s", cand_log_url, dl_err)
                    self.log_repo.log(
                        stage="DOWNLOAD_FAILED",
                        status="failed",
                        automation_run_id=run_id,
                        message=f"Download failed for '{candidate.title}': {str(dl_err)}",
                        error_details=str(dl_err),
                    )
                    continue
                except Exception as unk_err:
                    total_failed += 1
                    logger.exception("Unexpected error downloading %s: %s", cand_log_url, unk_err)
                    self.log_repo.log(
                        stage="DOWNLOAD_FAILED",
                        status="failed",
                        automation_run_id=run_id,
                        message=f"Unexpected download error: {str(unk_err)}",
                        error_details=str(unk_err),
                    )
                    continue

                # Tier 2 Deduplication: Check SHA-256 fingerprint in MySQL
                existing_by_hash = self.doc_repo.get_by_hash(downloaded.sha256)
                if existing_by_hash:
                    total_duplicates += 1
                    # Remove the downloaded duplicate file since identical content exists
                    local_path = Path(downloaded.local_path)
                    if local_path.exists():
                        try:
                            local_path.unlink()
                        except Exception as del_err:
                            logger.debug("Failed to remove duplicate file %s: %s", local_path, del_err)

                    self.log_repo.log(
                        stage="DUPLICATE_DETECTED",
                        status="success",
                        automation_run_id=run_id,
                        document_id=existing_by_hash.get("id"),
                        message=f"Duplicate detected via SHA-256 {downloaded.sha256[:16]} (Matches Doc ID: {existing_by_hash.get('id')})",
                    )
                    continue

                # Content is genuinely new -> Store in documents table
                try:
                    new_doc_id = self.doc_repo.create(
                        company_id=company_id,
                        file_name=downloaded.file_name,
                        local_path=downloaded.local_path,
                        file_hash=downloaded.sha256,
                        file_url=candidate.url,
                        document_type=candidate.document_type,
                        report_period=candidate.report_period,
                        report_date=candidate.report_date,
                        processing_status="downloaded",
                        source_id=source_id,
                        file_size_bytes=downloaded.file_size,
                    )
                    total_downloaded += 1

                    self.log_repo.log(
                        stage="DOWNLOAD_COMPLETED",
                        status="success",
                        automation_run_id=run_id,
                        document_id=new_doc_id,
                        message=f"Stored new document '{downloaded.file_name}' ({downloaded.file_size} bytes, SHA-256: {downloaded.sha256[:12]})",
                    )
                except Exception as db_err:
                    total_failed += 1
                    logger.exception("Failed to insert document record for %s: %s", downloaded.file_name, db_err)
                    self.log_repo.log(
                        stage="DOWNLOAD_FAILED",
                        status="failed",
                        automation_run_id=run_id,
                        message=f"Failed to record document metadata in database: {str(db_err)}",
                        error_details=str(db_err),
                    )

            # Determine final status
            final_status = "completed"
            if total_failed > 0 and total_downloaded == 0 and total_discovered > 0:
                final_status = "failed"
                error_message = f"All {total_failed} candidate document downloads failed."

            # Update automation_run record
            completed_at = datetime.now()
            self.run_repo.update_status(
                run_id=run_id,
                status=final_status,
                error_message=error_message,
                docs_discovered=total_discovered,
                docs_downloaded=total_downloaded,
                docs_processed=0,
                completed_at=completed_at,
            )

            # Update automation last_run_at
            self.automation_repo.update_schedule(automation_id=automation_id, last_run_at=completed_at)

            summary_msg = (
                f"Discovered: {total_discovered}, Downloaded: {total_downloaded}, "
                f"Duplicates: {total_duplicates}, Failed: {total_failed}."
            )
            logger.info("Automation run %s finished with status '%s'. %s", run_id, final_status, summary_msg)

            return {
                "run_id": run_id,
                "automation_id": automation_id,
                "company_id": company_id,
                "status": final_status,
                "documents_discovered": total_discovered,
                "documents_downloaded": total_downloaded,
                "duplicates": total_duplicates,
                "documents_failed": total_failed,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "message": summary_msg,
            }

        except Exception as exc:
            logger.exception("Fatal error during automation run %s: %s", run_id, exc)
            self.run_repo.update_status(
                run_id=run_id,
                status="failed",
                error_message=str(exc),
                docs_discovered=total_discovered,
                docs_downloaded=total_downloaded,
                completed_at=datetime.now(),
            )
            return {
                "run_id": run_id,
                "automation_id": automation_id,
                "company_id": company_id,
                "status": "failed",
                "documents_discovered": total_discovered,
                "documents_downloaded": total_downloaded,
                "duplicates": total_duplicates,
                "documents_failed": total_failed,
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now().isoformat(),
                "message": f"Automation run failed: {str(exc)}",
                "error": str(exc),
            }
