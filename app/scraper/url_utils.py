"""URL safety, normalization, and path sanitization utilities."""

import html
import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

DISALLOWED_SCHEMES = {"file", "ftp", "data", "javascript", "mailto", "gopher", "ldap"}
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "_ga",
    "_gl",
    "ref",
}
BLOCKED_HOSTNAMES = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def is_safe_url(url: Optional[str]) -> bool:
    """Validate that a URL uses HTTP/HTTPS and does not target prohibited protocols or local files."""
    if not url or not isinstance(url, str):
        return False

    url_clean = url.strip()
    if not url_clean:
        return False

    try:
        parsed = urlparse(url_clean)
        # Scheme must be strictly http or https
        if parsed.scheme.lower() not in ("http", "https"):
            return False

        # Hostname must exist and not be a prohibited local address
        host = (parsed.hostname or "").lower().strip()
        if not host:
            return False

        if host in BLOCKED_HOSTNAMES:
            return False

        return True
    except Exception:
        return False


def normalize_url(base_url: str, candidate_url: str) -> Optional[str]:
    """Normalize a relative or absolute candidate link into a clean, safe absolute URL.

    Handles:
    - HTML entity decoding (&amp; -> &)
    - Relative URL resolution (e.g. ../files/report.pdf -> https://example.com/files/report.pdf)
    - Fragment removal (#page=1)
    - Safe tracking parameter stripping (utm_*, fbclid) while preserving operational query params
    - Duplicate slash normalization
    """
    if not candidate_url or not isinstance(candidate_url, str):
        return None

    # 1. Unescape HTML entities
    unescaped = html.unescape(candidate_url.strip())
    if not unescaped:
        return None

    # 2. Resolve relative URL against base_url
    try:
        resolved = urljoin(base_url.strip(), unescaped)
        parsed = urlparse(resolved)
    except Exception:
        return None

    if not is_safe_url(resolved):
        return None

    # 3. Clean path: collapse multiple slashes (e.g. //path///to -> /path/to)
    clean_path = re.sub(r"/{2,}", "/", parsed.path) if parsed.path else "/"

    # 4. Strip safe tracking query parameters while keeping functional params
    query_parts = []
    if parsed.query:
        try:
            for k, v in parse_qsl(parsed.query, keep_blank_values=True):
                if k.lower() not in TRACKING_PARAMS:
                    query_parts.append((k, v))
        except Exception:
            # If query string cannot be parsed as pairs, retain original
            query_parts = None

    clean_query = urlencode(query_parts) if query_parts is not None else parsed.query

    # 5. Reconstruct without fragment (#...)
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        clean_path,
        parsed.params,
        clean_query,
        "",  # Fragment explicitly stripped
    ))

    return normalized


def sanitize_filename(name: str, max_length: int = 150) -> str:
    """Sanitize a filename for Windows and POSIX filesystem safety."""
    if not name:
        return "unnamed_document.pdf"

    # Separate extension if present
    match = re.search(r"(\.[a-zA-Z0-9]{1,8})$", name)
    ext = match.group(1).lower() if match else ".pdf"
    stem = name[: -len(ext)] if match else name

    # Replace invalid filesystem characters (\ / : * ? " < > | and non-printables)
    clean_stem = re.sub(r'[\\/*?:"<>|#%&{}\\<>*?/$!\'":@+`|=]', "_", stem)
    clean_stem = re.sub(r"\s+", "_", clean_stem)
    clean_stem = re.sub(r"_{2,}", "_", clean_stem).strip("._ ")

    if not clean_stem:
        clean_stem = "document"

    # Truncate to max_length including extension
    allowed_stem_len = max_length - len(ext)
    if len(clean_stem) > allowed_stem_len:
        clean_stem = clean_stem[:allowed_stem_len].rstrip("._ ")

    return f"{clean_stem}{ext}"


def sanitize_log_url(url: str) -> str:
    """Strip query parameters and user credentials from a URL for privacy-preserving audit logging."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        # Reconstruct only scheme, host, and path
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return f"{parsed.scheme}://{host}{parsed.path}"
    except Exception:
        return "[sanitized_url]"
