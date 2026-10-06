"""Web and report scraping module."""

from app.scraper.base import BaseSourceProvider
from app.scraper.classifier import classify_document, is_financial_document
from app.scraper.models import DiscoveredDocument, DownloadedDocument
from app.scraper.pdf_downloader import DownloadError, InvalidPDFError, OversizedFileError, PDFDownloader
from app.scraper.screener_scraper import ScreenerScraper
from app.scraper.source_discovery import GenericWebProvider, ScreenerProvider, SourceDiscoveryRegistry
from app.scraper.url_utils import is_safe_url, normalize_url, sanitize_filename, sanitize_log_url

__all__ = [
    "ScreenerScraper",
    "BaseSourceProvider",
    "DiscoveredDocument",
    "DownloadedDocument",
    "PDFDownloader",
    "DownloadError",
    "InvalidPDFError",
    "OversizedFileError",
    "classify_document",
    "is_financial_document",
    "ScreenerProvider",
    "GenericWebProvider",
    "SourceDiscoveryRegistry",
    "is_safe_url",
    "normalize_url",
    "sanitize_filename",
    "sanitize_log_url",
]
