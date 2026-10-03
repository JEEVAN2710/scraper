"""PDF Extraction, SHA-256 fingerprinting, text chunking, and risk factor identification."""

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pypdf import PdfReader

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extracts text, metadata, chunks, and risk disclosures from PDF annual reports."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.chunk_size = self.settings.CHUNK_SIZE
        self.chunk_overlap = self.settings.CHUNK_OVERLAP
        self.min_words_for_ocr = self.settings.OCR_FALLBACK_MIN_WORDS

    def compute_sha256(self, file_path: Path) -> str:
        """Compute SHA-256 hash for document deduplication."""
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            file_hash = hasher.hexdigest()
            logger.debug("Computed SHA-256 for %s: %s", file_path.name, file_hash)
            return file_hash
        except Exception as exc:
            logger.exception("Failed computing SHA-256 for %s: %s", file_path, exc)
            raise

    def extract_text_and_pages(self, file_path: Path, max_pages: Optional[int] = 100) -> Dict[str, Any]:
        """Extract text and metadata from PDF pages."""
        logger.info("Extracting text from PDF: %s (max_pages=%s)", file_path.name, max_pages)
        pages_data: List[Dict[str, Any]] = []
        total_words = 0
        scanned_pages_count = 0

        try:
            reader = PdfReader(str(file_path))
            total_doc_pages = len(reader.pages)
            limit = min(total_doc_pages, max_pages) if max_pages else total_doc_pages

            for page_idx in range(limit):
                page_num = page_idx + 1
                try:
                    page_obj = reader.pages[page_idx]
                    page_text = page_obj.extract_text() or ""
                    cleaned_text = re.sub(r"\s+", " ", page_text).strip()
                    words = cleaned_text.split()
                    word_count = len(words)
                    total_words += word_count

                    is_scanned = word_count < self.min_words_for_ocr
                    if is_scanned:
                        scanned_pages_count += 1

                    pages_data.append({
                        "page_number": page_num,
                        "text": cleaned_text,
                        "word_count": word_count,
                        "is_scanned": is_scanned,
                    })
                except Exception as page_err:
                    logger.warning("Error reading page %d of %s: %s", page_num, file_path.name, page_err)

            logger.info(
                "Extracted %d pages (%d total words, %d low-word/scanned pages) from %s",
                len(pages_data),
                total_words,
                scanned_pages_count,
                file_path.name,
            )

            return {
                "file_name": file_path.name,
                "total_doc_pages": total_doc_pages,
                "extracted_pages": len(pages_data),
                "total_words": total_words,
                "scanned_pages_count": scanned_pages_count,
                "pages": pages_data,
            }
        except Exception as exc:
            logger.exception("Failed extracting text from PDF %s: %s", file_path, exc)
            raise

    def chunk_document(
        self,
        pages: List[Dict[str, Any]],
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Split document pages into overlapping character-aware chunks."""
        size = chunk_size or self.chunk_size
        step = size - (overlap or self.chunk_overlap)
        chunks: List[Dict[str, Any]] = []
        chunk_idx = 0

        for page in pages:
            text = page.get("text", "")
            page_num = page.get("page_number", 1)
            if not text:
                continue

            for start in range(0, len(text), max(1, step)):
                end = start + size
                chunk_content = text[start:end].strip()
                if len(chunk_content) < 50:  # Skip trivial fragments
                    continue

                chunks.append({
                    "chunk_index": chunk_idx,
                    "page_start": page_num,
                    "page_end": page_num,
                    "content": chunk_content,
                })
                chunk_idx += 1

        logger.info("Generated %d chunks from %d pages", len(chunks), len(pages))
        return chunks

    def extract_risk_factors(
        self,
        pages: List[Dict[str, Any]],
        ticker: str,
        max_risks: int = 6,
    ) -> List[Dict[str, Any]]:
        """Identify risk factors, threats, and uncertainties with exact page numbers."""
        risks: List[Dict[str, Any]] = []
        seen_titles = set()

        risk_indicators = [
            (r"(cybersecurity|data\s+security|information\s+security)", "Cybersecurity & Information Security"),
            (r"(regulatory\s+compliance|litigation|statutory\s+changes|compliance\s+risk)", "Regulatory & Legal Compliance"),
            (r"(foreign\s+exchange|currency\s+volatility|forex)", "Foreign Exchange & Currency Volatility"),
            (r"(talent\s+attrition|human\s+capital|key\s+personnel|wage\s+inflation)", "Talent Retention & Human Capital"),
            (r"(geopolitical|macroeconomic|inflationary\s+pressures|global\s+slowdown)", "Macroeconomic & Geopolitical Uncertainty"),
            (r"(climate\s+change|esg|environmental\s+sustainability)", "Climate Change & ESG Governance"),
            (r"(supply\s+chain|vendor\s+concentration|logistics)", "Supply Chain & Third-Party Reliance"),
            (r"(technological\s+obsolescence|ai\s+disruption|disruptive\s+technology)", "Technological Disruption & AI Adoption"),
        ]

        # Scan pages for high-probability risk sections
        for page in pages:
            text = page.get("text", "")
            page_num = page.get("page_number", 1)
            text_lower = text.lower()

            # Skip table of contents or index
            if "table of contents" in text_lower or "index" in text_lower and len(text) < 300:
                continue

            for pattern, category in risk_indicators:
                if category in seen_titles:
                    continue

                match = re.search(pattern, text_lower)
                if match:
                    # Extract surrounding sentence as description
                    start_pos = max(0, match.start() - 50)
                    end_pos = min(len(text), match.end() + 250)
                    snippet = text[start_pos:end_pos].strip()

                    # Clean snippet
                    clean_desc = re.sub(r"\s+", " ", snippet)
                    if len(clean_desc) > 200:
                        clean_desc = clean_desc[:197] + "..."

                    risks.append({
                        "risk": category,
                        "description": clean_desc or f"Key disclosures regarding {category.lower()} monitored in annual filing.",
                        "page_number": page_num,
                    })
                    seen_titles.add(category)

                    if len(risks) >= max_risks:
                        break

            if len(risks) >= max_risks:
                break

        # If no specific regex matched, add general risk disclosure
        if not risks:
            risks.append({
                "risk": "Operational & Market Volatility",
                "description": f"Standard operational, macroeconomic, and competitive uncertainties disclosed in {ticker} annual filing.",
                "page_number": 1,
            })

        logger.info("Extracted %d risk disclosures with page citations for %s", len(risks), ticker)
        return risks
