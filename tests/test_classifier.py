"""Unit tests for deterministic document classifier and relevance filter."""

from app.scraper.classifier import classify_document, extract_period_heuristic, is_financial_document


def test_classify_annual_report():
    """Verify Annual Report classification and period extraction."""
    doc_type, period = classify_document("Annual Report 2023-24", "https://example.com/reports/ar24.pdf")
    assert doc_type == "ANNUAL_REPORT"
    assert period == "FY2024"

    doc_type2, period2 = classify_document("Integrated Annual Report FY2025", "https://example.com/ir2025.pdf")
    assert doc_type2 == "ANNUAL_REPORT"
    assert period2 == "FY2025"


def test_classify_quarterly_and_concall():
    """Verify Quarterly results and Concall transcripts classification."""
    doc_type, period = classify_document("Q1 FY25 Earnings Call Transcript", "https://example.com/concall_q1.pdf")
    assert doc_type == "CONCALL_TRANSCRIPT"
    assert period == "Q1-FY2025"

    doc_type2, period2 = classify_document("Quarterly Financial Results Q2 FY2024", "https://example.com/q2_results.pdf")
    assert doc_type2 == "QUARTERLY_REPORT"
    assert period2 == "Q2-FY2024"


def test_classify_presentations():
    """Verify Investor and Corporate Presentation classification."""
    doc_type, period = classify_document("Investor Presentation Nov 2024", "https://example.com/deck.pdf")
    assert doc_type == "INVESTOR_PRESENTATION"

    doc_type2, _ = classify_document("Corporate Presentation FY24", "https://example.com/corp.pdf")
    assert doc_type2 == "CORPORATE_PRESENTATION"


def test_period_extraction_heuristics():
    """Verify various fiscal year string formats map to standardized periods."""
    assert extract_period_heuristic("Report FY2023") == "FY2023"
    assert extract_period_heuristic("Report FY24") == "FY2024"
    assert extract_period_heuristic("Filing 2022-2023") == "FY2023"
    assert extract_period_heuristic("Results Q3 FY26") == "Q3-FY2026"
    assert extract_period_heuristic("No Period Mentioned") is None


def test_is_financial_document_filtering():
    """Verify positive inclusion of financial reports and negative exclusion of corporate boilerplate."""
    # Positive
    assert is_financial_document("Annual Report", "https://example.com/ar.pdf") is True
    assert is_financial_document("Audited Financial Results", "https://example.com/results.pdf") is True
    assert is_financial_document("Earnings Call Transcript", "https://example.com/transcript.pdf") is True
    assert is_financial_document("Balance Sheet Details", "https://example.com/accounts.pdf") is True

    # Negative / Irrelevant
    assert is_financial_document("Privacy Policy", "https://example.com/privacy-policy.pdf") is False
    assert is_financial_document("Terms and Conditions", "https://example.com/terms.pdf") is False
    assert is_financial_document("Whistle Blower Policy", "https://example.com/whistleblower.pdf") is False
    assert is_financial_document("CSR Policy and Guidelines", "https://example.com/csr_policy.pdf") is False
    assert is_financial_document("Product Catalog 2024", "https://example.com/catalog.pdf") is False
    assert is_financial_document("Career Guide / Recruitment", "https://example.com/jobs.pdf") is False
