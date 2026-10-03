"""Unit tests for PDFExtractor module."""

import pytest
from pathlib import Path
from app.extraction.pdf_extractor import PDFExtractor


def test_pdf_extractor_compute_sha256(tmp_path):
    """Test SHA-256 calculation for document fingerprinting."""
    extractor = PDFExtractor()
    test_file = tmp_path / "sample.pdf"
    test_file.write_bytes(b"Mock PDF content for SHA-256 testing")

    file_hash = extractor.compute_sha256(test_file)
    assert len(file_hash) == 64
    # Deterministic hash of above string
    assert isinstance(file_hash, str)


def test_pdf_extractor_chunking():
    """Test character-aware chunking with overlap."""
    extractor = PDFExtractor()
    sample_pages = [
        {
            "page_number": 1,
            "text": "This is page one text. " * 30,  # ~690 chars
        },
        {
            "page_number": 2,
            "text": "This is page two text with different content. " * 30,  # ~1380 chars
        }
    ]

    chunks = extractor.chunk_document(sample_pages, chunk_size=500, overlap=100)
    assert len(chunks) >= 3
    assert chunks[0]["page_start"] == 1
    assert "page one text" in chunks[0]["content"]
    assert len(chunks[0]["content"]) <= 500


def test_pdf_extractor_risk_extraction():
    """Test extraction of risk factors and page provenance."""
    extractor = PDFExtractor()
    sample_pages = [
        {
            "page_number": 15,
            "text": "The company is subject to strict regulatory compliance and potential litigation across international jurisdictions.",
        },
        {
            "page_number": 22,
            "text": "Foreign exchange and currency volatility between USD and INR may adversely affect operating margins.",
        },
        {
            "page_number": 28,
            "text": "Cybersecurity and information security threats continue to evolve with cloud migration.",
        }
    ]

    risks = extractor.extract_risk_factors(sample_pages, "TEST")
    assert len(risks) == 3
    risk_names = [r["risk"] for r in risks]
    assert "Regulatory & Legal Compliance" in risk_names
    assert "Foreign Exchange & Currency Volatility" in risk_names
    assert "Cybersecurity & Information Security" in risk_names

    # Check page citations
    reg_risk = next(r for r in risks if r["risk"] == "Regulatory & Legal Compliance")
    assert reg_risk["page_number"] == 15
