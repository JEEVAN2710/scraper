"""Streaming PDF Downloader with chunked hashing, size limits, and magic-byte signature validation."""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import httpx

from app.config.settings import Settings, get_settings
from app.scraper.models import DownloadedDocument
from app.scraper.url_utils import is_safe_url, sanitize_filename, sanitize_log_url

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class DownloadError(Exception):
    """Base exception for document download failures."""
    pass


class InvalidPDFError(DownloadError):
    """Raised when downloaded stream does not contain a valid %PDF- header."""
    pass


class OversizedFileError(DownloadError):
    """Raised when downloaded file exceeds configured size ceiling."""
    pass


class PDFDownloader:
    """Manages streaming document downloads, size capping, and streaming SHA-256 fingerprinting."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.download_dir = Path(self.settings.DOWNLOAD_DIR)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir = self.download_dir / ".staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        self.timeout = getattr(self.settings, "DOWNLOAD_TIMEOUT", 45.0)
        self.max_size_bytes = getattr(self.settings, "DOWNLOAD_MAX_SIZE_MB", 100) * 1024 * 1024
        self.chunk_size = getattr(self.settings, "DOWNLOAD_CHUNK_SIZE", 65536)

    def download(
        self,
        url: str,
        preferred_name: Optional[str] = None,
        company_identifier: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ) -> DownloadedDocument:
        """Stream a PDF document from a URL to local disk with size & signature verification.

        Args:
            url: Normalized candidate URL.
            preferred_name: Suggested filename or title for saving.
            company_identifier: Optional company ticker/id to prefix filename.
            client: Optional httpx.Client instance for connection pooling / mocking.

        Returns:
            DownloadedDocument: Metadata of the successfully downloaded and hashed file.
        """
        if not is_safe_url(url):
            raise DownloadError(f"URL is unsafe or unsupported: {sanitize_log_url(url)}")

        log_url = sanitize_log_url(url)
        logger.info("Starting streaming download from %s...", log_url)

        # Temporary staging path during download
        staging_filename = f"dl_{hashlib.md5(url.encode()).hexdigest()}_{datetime.now().strftime('%Y%m%d%H%M%S')}.tmp"
        staging_path = self.staging_dir / staging_filename

        hasher = hashlib.sha256()
        total_bytes = 0
        content_type = None
        first_chunk = True

        def _do_stream(req_client: httpx.Client) -> DownloadedDocument:
            nonlocal total_bytes, content_type, first_chunk
            try:
                with req_client.stream("GET", url, follow_redirects=True, timeout=self.timeout, headers=DEFAULT_HEADERS) as response:
                    if response.status_code != 200:
                        raise DownloadError(f"HTTP {response.status_code} returned when requesting {log_url}")

                    content_type = response.headers.get("Content-Type", "")

                    with open(staging_path, "wb") as f_out:
                        for chunk in response.iter_bytes(chunk_size=self.chunk_size):
                            if not chunk:
                                continue

                            # Signature check on first bytes
                            if first_chunk:
                                # Look for %PDF- in the first 1024 bytes (allows for UTF-8 BOM, whitespace)
                                if b"%PDF-" not in chunk[:1024]:
                                    # If not in first bytes and content-type is HTML/text, reject
                                    if "text/html" in content_type.lower() or "application/json" in content_type.lower():
                                        raise InvalidPDFError(
                                            f"Downloaded content from {log_url} is not a PDF (Content-Type: {content_type})"
                                        )
                                    # Even without explicit Content-Type, reject if no %PDF- header
                                    if b"%PDF-" not in chunk:
                                        raise InvalidPDFError(f"Downloaded stream from {log_url} lacks %PDF- header signature")
                                first_chunk = False

                            total_bytes += len(chunk)
                            if total_bytes > self.max_size_bytes:
                                raise OversizedFileError(
                                    f"File from {log_url} exceeded maximum size of {self.max_size_bytes / (1024*1024):.1f} MB"
                                )

                            hasher.update(chunk)
                            f_out.write(chunk)

                if total_bytes == 0:
                    raise DownloadError(f"Downloaded file from {log_url} is empty (0 bytes)")

                sha256_hash = hasher.hexdigest()

                # Generate clean final filename
                base_name = preferred_name or Path(url).stem or "document"
                if company_identifier:
                    final_stem = f"{company_identifier}_{base_name}_{sha256_hash[:8]}"
                else:
                    final_stem = f"{base_name}_{sha256_hash[:8]}"

                final_name = sanitize_filename(f"{final_stem}.pdf")
                final_path = self.download_dir / final_name

                # If file already exists with same name and size, overwrite safely
                if final_path.exists():
                    final_path.unlink()

                staging_path.rename(final_path)
                logger.info(
                    "Successfully downloaded %s (%d bytes, SHA-256: %s)",
                    final_path.name,
                    total_bytes,
                    sha256_hash[:16],
                )

                return DownloadedDocument(
                    url=url,
                    local_path=str(final_path.relative_to(Path.cwd()) if final_path.is_relative_to(Path.cwd()) else final_path),
                    file_name=final_path.name,
                    file_size=total_bytes,
                    sha256=sha256_hash,
                    content_type=content_type,
                    downloaded_at=datetime.now(),
                )

            except Exception:
                # Clean up staging file on failure
                if staging_path.exists():
                    try:
                        staging_path.unlink()
                    except Exception as clean_err:
                        logger.debug("Failed cleaning up staging file %s: %s", staging_path, clean_err)
                raise

        if client:
            return _do_stream(client)
        else:
            with httpx.Client() as default_client:
                return _do_stream(default_client)
