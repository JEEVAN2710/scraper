"""Abstract base interfaces for multi-source document discovery."""

from abc import ABC, abstractmethod
from typing import List, Optional

from app.scraper.models import DiscoveredDocument


class BaseSourceProvider(ABC):
    """Abstract interface for all document discovery sources (Screener, Corporate Websites, Exchanges, IR)."""

    def __init__(self, source_type: str) -> None:
        self.source_type = source_type

    @abstractmethod
    def discover(
        self,
        source_url: str,
        company_identifier: Optional[str] = None,
        max_documents: int = 30,
    ) -> List[DiscoveredDocument]:
        """Inspect origin source URL and return candidate document records.

        Args:
            source_url: Configured URL to inspect for filings.
            company_identifier: Optional ticker symbol or company name for context.
            max_documents: Upper limit on candidate documents to discover.

        Returns:
            List[DiscoveredDocument]: Structured candidate documents found.
        """
        pass
