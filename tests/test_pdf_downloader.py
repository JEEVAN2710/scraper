"""Unit tests for streaming PDFDownloader, magic byte validation, and SHA-256 calculation."""

import hashlib
import io
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.config.settings import Settings
from app.scraper.pdf_downloader import DownloadError, InvalidPDFError, OversizedFileError, PDFDownloader


@pytest.fixture
def temp_downloader(tmp_path):
    """Create a PDFDownloader with isolated temporary download and staging directories."""
    settings = Settings()
    settings.DOWNLOAD_DIR = tmp_path / "downloads"
    downloader = PDFDownloader(settings=settings)
    return downloader


def test_pdf_downloader_success(temp_downloader):
    """Test streaming download of a valid PDF with %PDF- header and SHA-256 fingerprinting."""
    mock_pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF"
    expected_hash = hashlib.sha256(mock_pdf_content).hexdigest()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/pdf"}
    mock_response.iter_bytes.return_value = [mock_pdf_content[:20], mock_pdf_content[20:]]

    mock_client.stream.return_value.__enter__.return_value = mock_response

    result = temp_downloader.download(
        url="https://example.com/reports/tcs_ar24.pdf",
        preferred_name="Annual_Report_2024",
        company_identifier="TCS",
        client=mock_client,
    )

    assert result.file_size == len(mock_pdf_content)
    assert result.sha256 == expected_hash
    assert result.file_name.startswith("TCS_Annual_Report_2024_")
    assert Path(result.local_path).exists()
    assert Path(result.local_path).read_bytes() == mock_pdf_content


def test_pdf_downloader_invalid_pdf_signature(temp_downloader):
    """Test rejection of non-PDF responses (e.g. HTML 200 error pages)."""
    mock_html = b"<!DOCTYPE html><html><body>Error 404 File Not Found</body></html>"

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.iter_bytes.return_value = [mock_html]

    mock_client.stream.return_value.__enter__.return_value = mock_response

    with pytest.raises(InvalidPDFError):
        temp_downloader.download(
            url="https://example.com/bad_link.pdf",
            client=mock_client,
        )

    # Ensure staging file was cleaned up
    staging_files = list(temp_downloader.staging_dir.glob("*.tmp"))
    assert len(staging_files) == 0


def test_pdf_downloader_oversized_file(temp_downloader):
    """Test abortion of download when stream exceeds max configured size."""
    temp_downloader.max_size_bytes = 100  # 100 bytes ceiling

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/pdf"}
    # Stream sends 150 bytes total
    mock_response.iter_bytes.return_value = [b"%PDF-1.4 header padding padding " * 5]

    mock_client.stream.return_value.__enter__.return_value = mock_response

    with pytest.raises(OversizedFileError):
        temp_downloader.download(
            url="https://example.com/oversized.pdf",
            client=mock_client,
        )

    # Staging files should be cleaned up
    assert len(list(temp_downloader.staging_dir.glob("*.tmp"))) == 0


def test_pdf_downloader_http_error(temp_downloader):
    """Test handling of HTTP error response codes (e.g. 500 Internal Server Error)."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_client.stream.return_value.__enter__.return_value = mock_response

    with pytest.raises(DownloadError) as exc_info:
        temp_downloader.download(
            url="https://example.com/server_error.pdf",
            client=mock_client,
        )
    assert "HTTP 500" in str(exc_info.value)


def test_pdf_downloader_unsafe_url_rejection(temp_downloader):
    """Test immediate rejection of unsafe protocols without making network requests."""
    with pytest.raises(DownloadError) as exc_info:
        temp_downloader.download("file:///etc/shadow")
    assert "unsafe or unsupported" in str(exc_info.value)
