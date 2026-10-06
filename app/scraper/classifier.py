"""Deterministic rule-based document classifier and financial relevance filter."""

import re
from typing import Optional, Tuple

# Positive patterns indicating official financial reporting
FINANCIAL_KEYWORDS = [
    r"annual[\s_\-]*report",
    r"integrated[\s_\-]*report",
    r"financial[\s_\-]*statement",
    r"financial[\s_\-]*result",
    r"quarterly[\s_\-]*result",
    r"investor[\s_\-]*presentation",
    r"earnings[\s_\-]*presentation",
    r"corporate[\s_\-]*presentation",
    r"concall[\s_\-]*transcript",
    r"conference[\s_\-]*call",
    r"earnings[\s_\-]*call",
    r"analyst[\s_\-]*meet",
    r"shareholder[\s_\-]*letter",
    r"audited[\s_\-]*result",
    r"unaudited[\s_\-]*result",
    r"corpfiling",
    r"bseplus",
    r"q[1-4][\s_\-]*fy",
    r"fy\d{2,4}",
    r"balance[\s_\-]*sheet",
    r"profit[\s_\-]*and[\s_\-]*loss",
    r"p&l",
]

# Negative patterns indicating non-financial corporate / legal boilerplate
IRRELEVANT_PATTERNS = [
    r"privacy[\s_\-]*policy",
    r"terms[\s_\-]*and[\s_\-]*conditions",
    r"terms[\s_\-]*of[\s_\-]*use",
    r"cookie[\s_\-]*policy",
    r"whistle[\s_\-]*blower",
    r"code[\s_\-]*of[\s_\-]*conduct",
    r"sexual[\s_\-]*harassment",
    r"posh[\s_\-]*policy",
    r"nomination[\s_\-]*policy",
    r"remuneration[\s_\-]*policy",
    r"csr[\s_\-]*policy",
    r"corporate[\s_\-]*social[\s_\-]*responsibility[\s_\-]*policy",
    r"dividend[\s_\-]*distribution[\s_\-]*policy",
    r"insider[\s_\-]*trading[\s_\-]*code",
    r"familiarization[\s_\-]*programme",
    r"product[\s_\-]*brochure",
    r"product[\s_\-]*catalog",
    r"user[\s_\-]*manual",
    r"job[\s_\-]*description",
    r"recruitment",
    r"career[\s_\-]*guide",
    r"iso[\s_\-]*certificate",
    r"compliance[\s_\-]*certificate",
]


def is_financial_document(title: str, url: str) -> bool:
    """Determine if a candidate document link is a relevant financial filing.

    Returns False if matching known irrelevant corporate boilerplate (policies, brochures).
    Returns True if matching financial reporting keywords or filing repositories.
    """
    text = f"{title} {url}".lower()

    # 1. Reject clear irrelevant documents first
    for pattern in IRRELEVANT_PATTERNS:
        if re.search(pattern, text):
            return False

    # 2. Check for positive financial keywords
    for pattern in FINANCIAL_KEYWORDS:
        if re.search(pattern, text):
            return True

    # 3. If URL ends with .pdf and has report/statement/results indicators
    if ".pdf" in url.lower():
        if any(term in text for term in ("report", "result", "presentation", "financial", "annual", "concall", "investor")):
            return True

    return False


def extract_period_heuristic(text: str) -> Optional[str]:
    """Extract fiscal period (e.g. FY2024, Q1-FY25, FY24) from title or URL text."""
    # Pattern 1: Q1 FY25, Q2-FY2024, Q3 2024
    q_match = re.search(r"\b(Q[1-4])[\s_\-]*(?:FY)?[\s_\-]*(\d{2,4})\b", text, re.IGNORECASE)
    if q_match:
        quarter = q_match.group(1).upper()
        yr = q_match.group(2)
        year_full = f"20{yr}" if len(yr) == 2 else yr
        return f"{quarter}-FY{year_full}"

    # Pattern 2: FY2024, FY24, FY-2024
    fy_match = re.search(r"\bFY[\s_\-]*(\d{2,4})\b", text, re.IGNORECASE)
    if fy_match:
        yr = fy_match.group(1)
        year_full = f"20{yr}" if len(yr) == 2 else yr
        return f"FY{year_full}"

    # Pattern 3: 2023-24, 2023-2024
    span_match = re.search(r"\b(20\d{2})[-_/](\d{2,4})\b", text)
    if span_match:
        end_yr = span_match.group(2)
        year_full = f"20{end_yr}" if len(end_yr) == 2 else end_yr
        return f"FY{year_full}"

    # Pattern 4: Standalone 4-digit year like Annual Report 2024
    yr_match = re.search(r"\b(20[12]\d)\b", text)
    if yr_match:
        return f"FY{yr_match.group(1)}"

    return None


def classify_document(title: str, url: str) -> Tuple[str, Optional[str]]:
    """Deterministically classify a document title and URL into a standard type and fiscal period."""
    combined = f"{title} {url}".lower()
    period = extract_period_heuristic(f"{title} {url}")

    # Annual Report
    if re.search(r"annual[\s_\-]*report|integrated[\s_\-]*report|\bar[-_]?\d{2,4}\b|bseplus", combined):
        return "ANNUAL_REPORT", period

    # Concall / Transcript
    if re.search(r"concall|transcript|conference[\s_\-]*call|earnings[\s_\-]*call", combined):
        return "CONCALL_TRANSCRIPT", period

    # Investor / Corporate Presentation
    if re.search(r"investor[\s_\-]*presentation|analyst[\s_\-]*presentation", combined):
        return "INVESTOR_PRESENTATION", period
    if re.search(r"corporate[\s_\-]*presentation|company[\s_\-]*presentation", combined):
        return "CORPORATE_PRESENTATION", period

    # Quarterly / Financial Results
    if re.search(r"quarterly[\s_\-]*result|q[1-4][\s_\-]*result", combined):
        return "QUARTERLY_REPORT", period
    if re.search(r"financial[\s_\-]*result|audited[\s_\-]*result|financial[\s_\-]*statement", combined):
        return "FINANCIAL_RESULTS", period

    # Fallback to OTHER
    return "OTHER", period
