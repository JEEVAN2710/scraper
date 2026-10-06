"""Concrete source discovery providers for Screener and generic corporate web pages."""

import logging
from typing import Dict, List, Optional, Set
from bs4 import BeautifulSoup
import httpx

from app.config.settings import Settings, get_settings
from app.scraper.base import BaseSourceProvider
from app.scraper.classifier import classify_document, is_financial_document
from app.scraper.models import DiscoveredDocument
from app.scraper.url_utils import is_safe_url, normalize_url, sanitize_log_url

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class ScreenerProvider(BaseSourceProvider):
    """Source provider extracting annual report and concall transcript filings from Screener.in."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__(source_type="screener")
        self.settings = settings or get_settings()
        self.timeout = getattr(self.settings, "DISCOVERY_TIMEOUT", 25.0)

    def discover(
        self,
        source_url: str,
        company_identifier: Optional[str] = None,
        max_documents: int = 30,
        client: Optional[httpx.Client] = None,
    ) -> List[DiscoveredDocument]:
        """Discover PDF filings from a Screener.in company page."""
        log_url = sanitize_log_url(source_url)
        logger.info("Discovering documents from Screener source: %s", log_url)

        if not is_safe_url(source_url):
            logger.warning("Rejecting unsafe Screener URL: %s", log_url)
            return []

        def _fetch(req_client: httpx.Client) -> str:
            resp = req_client.get(source_url, follow_redirects=True, timeout=self.timeout, headers=DEFAULT_HEADERS)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code} fetching Screener page {log_url}")
            return resp.text

        try:
            if client:
                html_text = _fetch(client)
            else:
                with httpx.Client() as default_client:
                    html_text = _fetch(default_client)
        except Exception as exc:
            logger.exception("Failed to fetch Screener page from %s: %s", log_url, exc)
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        annual_docs: List[DiscoveredDocument] = []
        seen_urls: Set[str] = set()

        # 1. Extract Annual Reports (Dedicated section)
        ar_container = soup.find("div", class_="annual-reports")
        candidate_containers = [ar_container] if ar_container else [soup]

        for container in candidate_containers:
            for a in container.find_all("a", href=True):
                # If falling back to full soup, never scan inside concalls section
                if not ar_container and a.find_parent("div", class_="concalls"):
                    continue
                href = a["href"].strip()
                if not href or href.startswith("#") or href.startswith("javascript:"):
                    continue

                link_text = " ".join(a.text.split()).strip()
                is_annual_candidate = (
                    "annual" in link_text.lower()
                    or "annual" in href.lower()
                    or "bseplus" in href.lower()
                    or "corpfiling" in href.lower()
                )
                if not is_annual_candidate and not (ar_container and href.lower().endswith(".pdf")):
                    continue

                normalized = normalize_url(source_url, href)
                if not normalized or normalized in seen_urls:
                    continue

                doc_type, period = classify_document(link_text, normalized)
                seen_urls.add(normalized)
                annual_docs.append(
                    DiscoveredDocument(
                        url=normalized,
                        source_url=source_url,
                        title=link_text if len(link_text) > 3 else "Annual Report",
                        document_type=doc_type if doc_type != "OTHER" else "ANNUAL_REPORT",
                        report_period=period,
                        company_identifier=company_identifier,
                        source_name=self.source_type,
                    )
                )

        # 2. Extract Concall Transcripts and Investor Presentations
        concall_docs: List[DiscoveredDocument] = []
        concall_div = soup.find("div", class_="concalls")
        if concall_div:
            for li in concall_div.find_all("li"):
                period_el = li.find("div", class_="ink-600")
                period_text = period_el.text.strip() if period_el else None

                for a in li.find_all("a", href=True):
                    href = a["href"].strip()
                    text = a.text.strip().lower()
                    title = (a.get("title") or "").lower()

                    if href.lower().endswith((".mp3", ".mp4", ".wav", ".m4a", ".ogg")):
                        continue
                    if "youtu" in href.lower():
                        continue

                    is_transcript = "transcript" in text or "transcript" in title
                    is_ppt = text in ("ppt", "presentation", "factsheet") or "presentation" in title or "factsheet" in title

                    if is_transcript or is_ppt:
                        normalized = normalize_url(source_url, href)
                        if normalized and normalized not in seen_urls:
                            seen_urls.add(normalized)
                            if is_transcript:
                                title_str = f"Concall Transcript {period_text}" if period_text else "Concall Transcript"
                                doc_kind = "CONCALL_TRANSCRIPT"
                            else:
                                title_str = f"Investor Presentation {period_text}" if period_text else "Investor Presentation"
                                doc_kind = "INVESTOR_PRESENTATION"

                            doc_type, period = classify_document(title_str, normalized)
                            concall_docs.append(
                                DiscoveredDocument(
                                    url=normalized,
                                    source_url=source_url,
                                    title=title_str,
                                    document_type=doc_kind,
                                    report_period=period_text or period,
                                    company_identifier=company_identifier,
                                    source_name=self.source_type,
                                )
                            )

        # Allocate discovered documents ensuring both recent concalls and annual reports are included
        # Prioritize concall transcripts & presentations (up to half or more of max_documents)
        concall_budget = max(4, max_documents // 2)
        ar_budget = max_documents - min(len(concall_docs), concall_budget)

        discovered = concall_docs[:concall_budget] + annual_docs[:ar_budget]
        # If still room, fill with remaining
        if len(discovered) < max_documents:
            remaining = [d for d in (concall_docs + annual_docs) if d not in discovered]
            discovered.extend(remaining[: max_documents - len(discovered)])

        logger.info(
            "ScreenerProvider discovered %d documents (%d concalls/PPT, %d annual reports) from %s",
            len(discovered),
            len([d for d in discovered if d.document_type in ("CONCALL_TRANSCRIPT", "INVESTOR_PRESENTATION")]),
            len([d for d in discovered if d.document_type == "ANNUAL_REPORT"]),
            log_url,
        )
        return discovered


class GenericWebProvider(BaseSourceProvider):
    """Source provider for scanning corporate websites, investor relations pages, and custom URLs."""

    def __init__(self, source_type: str = "company_website", settings: Optional[Settings] = None) -> None:
        super().__init__(source_type=source_type)
        self.settings = settings or get_settings()
        self.timeout = getattr(self.settings, "DISCOVERY_TIMEOUT", 25.0)

    def discover(
        self,
        source_url: str,
        company_identifier: Optional[str] = None,
        max_documents: int = 30,
        client: Optional[httpx.Client] = None,
    ) -> List[DiscoveredDocument]:
        """Scan an HTML page for downloadable PDF filings and official reports."""
        log_url = sanitize_log_url(source_url)
        logger.info("Scanning generic source [%s]: %s", self.source_type, log_url)

        if not is_safe_url(source_url):
            logger.warning("Rejecting unsafe URL: %s", log_url)
            return []

        # If source_url directly targets a PDF file
        if source_url.lower().endswith(".pdf"):
            doc_type, period = classify_document(Path(source_url).stem, source_url)
            return [
                DiscoveredDocument(
                    url=source_url,
                    source_url=source_url,
                    title=Path(source_url).stem,
                    document_type=doc_type,
                    report_period=period,
                    company_identifier=company_identifier,
                    source_name=self.source_type,
                )
            ]

        def _fetch(req_client: httpx.Client) -> str:
            resp = req_client.get(source_url, follow_redirects=True, timeout=self.timeout, headers=DEFAULT_HEADERS)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code} fetching page {log_url}")
            return resp.text

        try:
            if client:
                html_text = _fetch(client)
            else:
                with httpx.Client() as default_client:
                    html_text = _fetch(default_client)
        except Exception as exc:
            logger.exception("Failed to scan page %s: %s", log_url, exc)
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        discovered: List[DiscoveredDocument] = []
        seen_urls: Set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            link_text = " ".join(a.text.split()).strip()
            normalized = normalize_url(source_url, href)
            if not normalized or normalized in seen_urls:
                continue

            # Check financial relevance and classification
            if not is_financial_document(link_text, normalized):
                continue

            doc_type, period = classify_document(link_text, normalized)
            seen_urls.add(normalized)

            discovered.append(
                DiscoveredDocument(
                    url=normalized,
                    source_url=source_url,
                    title=link_text if len(link_text) > 3 else (Path(normalized).stem or "Financial Filing"),
                    document_type=doc_type,
                    report_period=period,
                    company_identifier=company_identifier,
                    source_name=self.source_type,
                )
            )

            if len(discovered) >= max_documents:
                break

        logger.info(
            "GenericWebProvider [%s] discovered %d candidates from %s",
            self.source_type,
            len(discovered),
            log_url,
        )
        return discovered


class SourceDiscoveryRegistry:
    """Registry and factory resolving company source types to appropriate provider instances."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._providers: Dict[str, BaseSourceProvider] = {
            "screener": ScreenerProvider(self.settings),
            "company_website": GenericWebProvider("company_website", self.settings),
            "investor_relations": GenericWebProvider("investor_relations", self.settings),
            "custom_url": GenericWebProvider("custom_url", self.settings),
            "bse": GenericWebProvider("bse", self.settings),
            "nse": GenericWebProvider("nse", self.settings),
        }

    def get_provider(self, source_type: str) -> BaseSourceProvider:
        """Resolve a source type to a provider instance with safe fallback."""
        key = (source_type or "").lower().strip()
        if key in self._providers:
            return self._providers[key]

        # Default fallback
        logger.info("Unrecognized source type '%s', falling back to GenericWebProvider", source_type)
        return self._providers["custom_url"]

    def register_provider(self, source_type: str, provider: BaseSourceProvider) -> None:
        """Register a new custom discovery provider."""
        self._providers[source_type.lower().strip()] = provider
