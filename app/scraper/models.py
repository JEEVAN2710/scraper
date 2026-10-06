"""Pydantic data models for document discovery, candidate filtering, and streaming downloads."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DiscoveredDocument(BaseModel):
    """Candidate document discovered from an external source before acquisition."""

    url: str = Field(..., description="Normalized absolute URL of the candidate document")
    source_url: str = Field(..., description="Origin web page where the document was discovered")
    title: str = Field(..., description="Document title, anchor text, or cleaned filename")
    document_type: str = Field(default="OTHER", description="Classified document type (e.g. ANNUAL_REPORT, QUARTERLY_REPORT)")
    report_period: Optional[str] = Field(None, description="Inferred fiscal period (e.g. FY2024, Q1-FY25)")
    report_date: Optional[str] = Field(None, description="Inferred publication or reporting date (YYYY-MM-DD)")
    company_identifier: Optional[str] = Field(None, description="Company ticker or identifier associated with source")
    source_name: str = Field(default="generic_web", description="Name/type of the discovery provider")
    discovered_at: datetime = Field(default_factory=datetime.now, description="Timestamp of discovery")


class DownloadedDocument(BaseModel):
    """Metadata for a successfully acquired and hashed document on local disk."""

    url: str = Field(..., description="Source URL downloaded from")
    local_path: str = Field(..., description="Relative or absolute filesystem path to the downloaded file")
    file_name: str = Field(..., description="Sanitized filename on disk")
    file_size: int = Field(..., description="Exact file size in bytes")
    sha256: str = Field(..., description="Computed 64-character hexadecimal SHA-256 fingerprint")
    content_type: Optional[str] = Field(None, description="HTTP Content-Type response header")
    downloaded_at: datetime = Field(default_factory=datetime.now, description="Timestamp of completed download")
