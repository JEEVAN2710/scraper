"""Unit tests for URL safety, normalization, and sanitization utilities."""

from app.scraper.url_utils import is_safe_url, normalize_url, sanitize_filename, sanitize_log_url


def test_is_safe_url():
    """Verify safe HTTP/HTTPS URL acceptance and rejection of dangerous protocols."""
    assert is_safe_url("https://www.screener.in/company/TCS/") is True
    assert is_safe_url("http://example.com/reports/ar2024.pdf") is True

    # Reject unsupported protocols
    assert is_safe_url("file:///C:/Windows/System32/calc.exe") is False
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("ftp://ftp.example.com/report.pdf") is False
    assert is_safe_url("data:application/pdf;base64,JVBERi0xLjQK") is False
    assert is_safe_url("javascript:alert(1)") is False

    # Reject localhost / loopback addresses
    assert is_safe_url("http://localhost:8000/internal") is False
    assert is_safe_url("http://127.0.0.1/admin") is False
    assert is_safe_url("http://0.0.0.0:3306") is False

    # Reject invalid types / empty strings
    assert is_safe_url("") is False
    assert is_safe_url(None) is False
    assert is_safe_url("not a url") is False


def test_normalize_url_relative_resolution():
    """Verify relative URL resolution against base page URL."""
    base = "https://example.com/investors/financials/"

    # Relative path with parent traversal
    assert normalize_url(base, "../reports/ar2024.pdf") == "https://example.com/investors/reports/ar2024.pdf"

    # Relative path from root
    assert normalize_url(base, "/downloads/report.pdf") == "https://example.com/downloads/report.pdf"

    # Current directory relative
    assert normalize_url(base, "q1_results.pdf") == "https://example.com/investors/financials/q1_results.pdf"


def test_normalize_url_fragment_and_tracking_params():
    """Verify stripping of URL fragments and marketing tracking tags while preserving operational query params."""
    base = "https://example.com"
    raw_url = "https://example.com/filings.pdf?utm_source=newsletter&utm_medium=email&doc_id=987#page=12"

    normalized = normalize_url(base, raw_url)
    assert "#page=12" not in normalized
    assert "utm_source" not in normalized
    assert "utm_medium" not in normalized
    assert "doc_id=987" in normalized


def test_normalize_url_html_entities():
    """Verify unescaping of HTML entities in candidate links."""
    base = "https://example.com"
    raw_url = "https://example.com/view.php?ticker=TCS&amp;type=annual&amp;year=2024"

    normalized = normalize_url(base, raw_url)
    assert "&amp;" not in normalized
    assert "ticker=TCS" in normalized
    assert "type=annual" in normalized
    assert "year=2024" in normalized


def test_sanitize_filename():
    """Verify removal of dangerous filesystem characters and safe truncation."""
    raw = 'Tata Motors: Q1 & Q2 / Results * 2024? "Draft" <v1>|final.pdf'
    clean = sanitize_filename(raw)
    assert ":" not in clean
    assert "/" not in clean
    assert "*" not in clean
    assert "?" not in clean
    assert '"' not in clean
    assert "<" not in clean
    assert ">" not in clean
    assert "|" not in clean
    assert clean.endswith(".pdf")

    # Length truncation test
    long_name = "a" * 200 + ".pdf"
    short_clean = sanitize_filename(long_name, max_length=50)
    assert len(short_clean) <= 50
    assert short_clean.endswith(".pdf")


def test_sanitize_log_url():
    """Verify query parameters and sensitive tokens are excluded from log strings."""
    url = "https://api.example.com/download.php?token=secret123&signature=abc456"
    log_safe = sanitize_log_url(url)
    assert "secret123" not in log_safe
    assert "signature" not in log_safe
    assert log_safe == "https://api.example.com/download.php"
