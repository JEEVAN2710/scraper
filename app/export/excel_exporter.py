"""Excel and CSV export module for financial reports and sector KPI review.

Provides:
1. generate_sector_master_excel(companies_data)
   - Sheet 'MASTER': Cross-company KPI comparison (Revenue, EBITDA, EBITDA Margin %, PAT)
   - Sheet 'Company Breakdown': Stacked company-by-company detailed KPI tables matching Image 2,
     with exact 29 data fields and empty space when data is not in transcript.
   - Per-company sheets: Individual detailed KPI breakdown tab for each company.

2. generate_company_excel(company_data)
   - Sheet 'KPI Breakdown': Dedicated sheet with the exact 29 data fields from Image 2.
   - Sheet 'Company Overview': High-level company dossier and metadata.
   - Sheet 'Financial Metrics': Standard tabular financial figures.
   - Sheet 'Risk Factors': Extracted risks with source page citations.
   - Sheet 'Document Registry': Tracked reports with SHA-256 hashes.
   - Sheet 'PDF Extracted Content': Chunks extracted from annual report (if present).

3. generate_company_csv(company_data)
   - Standard CSV export.
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.config.settings import get_settings
from app.database.repositories import format_fiscal_period_display

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Visual Styling Palette (Matching Target Financial Design)
# ---------------------------------------------------------------------------
C_NAVY_BANNER   = "1F3864"  # Dark navy blue (Title banner & company cards)
C_NAVY_TEXT     = "FFFFFF"  # White text for dark banners
C_SECTION_BG    = "BDD7EE"  # Soft slate/ice blue for section headers (Revenue, EBITDA...)
C_SECTION_FG    = "1F3864"  # Dark navy text for section headers
C_QTR_BG        = "2E75B6"  # Professional blue for quarter column headers
C_QTR_FG        = "FFFFFF"  # White text for quarter headers
C_ACTUAL_BG     = "FFFFFF"  # White background for ACTUAL sub-label
C_ACTUAL_FG     = "595959"  # Medium gray text for ACTUAL
C_TOTAL_BG      = "E9ECEF"  # Soft muted gray for Total rows
C_TOTAL_FG      = "000000"  # Black text for Total rows
C_ZEBRA_ODD     = "FFFFFF"  # White
C_ZEBRA_EVEN    = "F8FAFC"  # Very soft off-white/gray for alternating rows
C_TEXT_MAIN     = "1E293B"  # Primary dark data font
C_YELLOW_KPI    = "FFFF00"  # Bright yellow highlight for key headline metrics
C_YELLOW_TEXT   = "000000"  # Black text on yellow highlight
C_SUBHDR_BG     = "D9D9D9"  # Light gray for subcategory groupings (e.g. REVENUE BY VERTICAL)
C_SUBHDR_FG     = "000000"  # Dark text on subcategory headers
C_RATIOS_BG     = "475569"  # Dark slate gray for ratios block
C_RATIOS_FG     = "FFFFFF"  # White text on ratios header
C_BORDER_LIGHT  = "D0D5DD"  # Thin clean border
C_BORDER_DARK   = "94A3B8"  # Medium border
C_BLUE_FONT     = "2E75B6"  # Blue font for seat counts


def _get_thin_border(color: str = C_BORDER_LIGHT) -> Border:
    s = Side(border_style="thin", color=color)
    return Border(top=s, left=s, right=s, bottom=s)


def _get_total_border(color: str = C_BORDER_DARK) -> Border:
    top_side = Side(border_style="thin", color=color)
    bottom_side = Side(border_style="double", color=color)
    side_border = Side(border_style="thin", color=color)
    return Border(top=top_side, bottom=bottom_side, left=side_border, right=side_border)


def _fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _font(
    name: str = "Calibri",
    size: int = 10,
    bold: bool = False,
    italic: bool = False,
    color: str = "000000",
) -> Font:
    return Font(name=name, size=size, bold=bold, italic=italic, color=color)


def _align(
    horizontal: str = "left",
    vertical: str = "center",
    wrap: bool = False,
) -> Alignment:
    return Alignment(horizontal=horizontal, vertical=vertical, wrap_text=wrap)


def _style_cell(
    cell,
    value: Any = None,
    bg: str = C_ZEBRA_ODD,
    fg: str = C_TEXT_MAIN,
    bold: bool = False,
    italic: bool = False,
    size: int = 10,
    h_align: str = "left",
    wrap: bool = False,
    border: Optional[Border] = None,
    num_format: Optional[str] = None,
) -> None:
    """Apply thorough font, fill, alignment, and formatting styles to a cell."""
    cell.value = value
    cell.font = _font(size=size, bold=bold, italic=italic, color=fg)
    cell.fill = _fill(bg)
    cell.alignment = _align(horizontal=h_align, wrap=wrap)
    cell.border = border if border is not None else _get_thin_border()
    if num_format:
        cell.number_format = num_format


def _auto_fit_columns(sheet, min_width: int = 12, max_width: int = 40) -> None:
    """Adjust column widths based on cell content length."""
    try:
        for col in sheet.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            sheet.column_dimensions[col_letter].width = max(min(max_len + 3, max_width), min_width)
    except Exception as exc:
        logger.warning("Auto-fit columns error: %s", exc)


def _quarter_sort_key(period_str: str) -> Tuple[int, int, str]:
    """Parse period like 'Q3 FY24' or 'FY2024' into a sortable tuple."""
    p = str(period_str).strip()
    # Match Q[1-4] FY[0-9]+
    m = re.search(r"Q([1-4])\s*(?:FY)?(\d+)", p, re.IGNORECASE)
    if m:
        q_num = int(m.group(1))
        yr_val = int(m.group(2))
        if yr_val < 100:
            yr_val += 2000
        return (yr_val, q_num, p)
    # Match FY[0-9]+
    m_fy = re.search(r"FY\s*(\d+)", p, re.IGNORECASE)
    if m_fy:
        yr_val = int(m_fy.group(1))
        if yr_val < 100:
            yr_val += 2000
        return (yr_val, 5, p)
    return (9999, 9, p)


def _collect_periods(companies_data: List[Dict[str, Any]]) -> List[str]:
    """Return a chronologically ordered, unique list of quarters/periods.
    Prioritizes quarterly periods (Qx FYxx) matching the sector review format.
    """
    default_qtrs = ["Q3 FY24", "Q4 FY24", "Q1 FY25", "Q2 FY25", "Q3 FY25", "Q4 FY25"]
    seen: set[str] = set()
    found: List[str] = []

    for co in companies_data:
        for key in ("quarterly_data", "operational_data", "transcript_data", "financial_data"):
            for row in co.get(key, []):
                p = row.get("period")
                if p and str(p) not in seen:
                    seen.add(str(p))
                    found.append(str(p))

    if not found:
        return default_qtrs

    # Sort found periods chronologically
    sorted_found = sorted(found, key=_quarter_sort_key)
    # Prefer quarterly periods if available
    q_periods = [p for p in sorted_found if re.search(r"Q[1-4]", p, re.I)]
    if q_periods:
        # If Q3 FY24 is in the set, start from Q3 FY24 to align with the active research coverage window
        if any(p.strip().upper().startswith("Q3 FY24") for p in q_periods):
            q_periods = [p for p in q_periods if p.strip().upper() not in ("Q1 FY24", "Q2 FY24")]
        return q_periods
    return sorted_found


def _build_period_data_map(company_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Map period -> {metric_key: value} combining financial_data, quarterly_data,
    operational_data, and transcript_data.
    """
    res: Dict[str, Dict[str, Any]] = {}
    for key in ("financial_data", "quarterly_data", "operational_data", "transcript_data"):
        for r in company_data.get(key, []):
            p = str(r.get("period", "")).strip()
            if p:
                if p in res:
                    res[p].update(r)
                else:
                    res[p] = {**r}
    return res


def _normalize_metric_val(val: Any, is_pct: bool = False, scale_cr: bool = False) -> Any:
    """Convert metric value into displayable float. Returns None if missing/unavailable."""
    if val is None or val == "" or val == "-" or str(val).strip() == "—":
        return None
    try:
        f = float(val)
        if scale_cr and abs(f) >= 1e7:
            f = f / 1e7
        if is_pct:
            # If percentage value was stored as whole number (e.g. 30.6 for 30.6%), normalize to fraction
            if abs(f) > 1.0:
                f = f / 100.0
        return f
    except (ValueError, TypeError):
        return str(val)


def _extract_metric_for_period(pmap: Dict[str, Dict[str, Any]], period: str, aliases: List[str]) -> Any:
    """Extract metric value from period map checking all known alias variations."""
    period_dict = pmap.get(period, {})
    # 1. Exact alias or label match
    for a in aliases:
        if a in period_dict and period_dict[a] is not None and period_dict[a] != "":
            return period_dict[a]
    # 2. Punctuation/casing normalized match (preventing substring collision on generic terms)
    clean_aliases = [re.sub(r"[^a-z0-9]", "", str(a).lower()) for a in aliases if a]
    for k, v in period_dict.items():
        if v is None or v == "":
            continue
        clean_k = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if not clean_k:
            continue
        for ca in clean_aliases:
            if not ca:
                continue
            if clean_k == ca or ca in clean_k:
                return v
    return None


# ---------------------------------------------------------------------------
# EXACT 29 Coworking KPI Data Fields (Matching Image 2 Exactly)
# ---------------------------------------------------------------------------

EXACT_COWORKING_FIELDS = [
    # (Label, key_aliases, is_pct, num_format, is_yellow_headline, font_color)
    ("Revenue from Ops (₹ Cr)", ["revenue_from_ops", "revenue from ops", "total_revenue", "sales", "revenue"], False, "#,##0.0", True, "000000"),
    ("Operating EBITDA (₹ Cr)", ["operating_ebitda", "operating ebitda", "operating_profit", "ebitda", "op_profit"], False, "#,##0.0", True, "000000"),
    ("Op. EBITDA Margin (%)", ["op_ebitda_margin", "op. ebitda margin", "operating_margin", "ebitda_margin", "opm"], True, "0.00%", True, "000000"),
    ("Reported PAT (₹ Cr)", ["reported_pat", "reported pat", "net_profit", "pat", "profit_after_tax"], False, "#,##0.0", True, "000000"),
    ("Cities", ["cities", "num_cities", "total_cities"], False, "#,##0", False, "000000"),
    ("Signed Supply Centers", ["signed_supply_centers", "signed supply centers", "signed_centers"], False, "#,##0", True, "000000"),
    ("Signed Supply Seats", ["signed_supply_seats", "signed supply seats", "signed_seats"], False, "#,##0", True, C_BLUE_FONT),
    ("Signed Supply Area (incl. LOI)", ["signed_supply_area_incl_loi", "signed_supply_area", "signed supply area", "signed_area_loi"], False, "0.0", True, "000000"),
    ("Total Centers (Op+Fitout)", ["total_centers_op_fitout", "total centers (op+fitout)", "total_centers", "total_supply_centers"], False, "#,##0", True, "000000"),
    ("Total Seats (Op+Fitout)", ["total_seats_op_fitout", "total seats (op+fitout)", "total_seats", "total_supply_seats"], False, "#,##0", False, C_BLUE_FONT),
    ("Operational Seats", ["operational_seats", "operational seats", "op_seats"], False, "#,##0", False, C_BLUE_FONT),
    ("MA Portfolio % (Seats)", ["ma_portfolio_pct", "ma portfolio % (seats)", "ma_portfolio_seats", "ma_portfolio"], True, "0%", False, "000000"),
    ("Blended Occupancy %", ["blended_occupancy", "blended occupancy %", "occupancy_pct", "occupancy"], True, "0%", False, "000000"),
    (">12m Vintage Occ. %", [">12m_vintage_occ", ">12m vintage occ. %", "vintage_occ", "vintage_occupancy_pct", "mature_occupancy"], True, "0%", False, "000000"),
    ("W. Avg Total Tenure (Mos)", ["w_avg_total_tenure_mos", "w. avg total tenure (mos)", "tenure_mos", "avg_tenure"], False, "#,##0", False, "000000"),
    ("Active Clients", ["active_clients", "active clients", "total_clients", "unique_clients"], False, "#,##0", False, "000000"),
    ("% Multi-Center Clients", ["multi_center_clients_pct", "% multi-center clients", "multi_center_pct"], True, "0%", False, "000000"),
    ("100+ Seats (Enterprise)", ["100+_seats_enterprise", "100+ seats (enterprise)", "100+ seats", "enterprise_seats", "enterprise"], True, "0%", False, "000000"),
    ("51-100 Seats", ["51_100_seats", "51-100 seats", "seats_51_100", "51-100"], True, "0%", False, "000000"),
    ("1-50 Seats", ["1_50_seats", "1-50 seats", "seats_1_50", "1-50"], True, "0%", False, "000000"),
    (">= 24 Months", [">=_24_months", ">= 24 months", "tenure_ge_24m", "months_24_plus", "24_months"], True, "0%", False, "000000"),
    ("12-23 Months", ["12_23_months", "12-23 months", "tenure_12_23m", "months_12_23"], True, "0%", False, "000000"),
    ("< 12 Months", ["<_12_months", "< 12 months", "tenure_lt_12m", "months_lt_12"], True, "0%", False, "000000"),
    ("IT/ITES", ["it_ites", "it/ites", "client_mix_it_ites", "industry_it", "ites", "information_technology"], True, "0%", False, "000000"),
    ("Prof. Services/Consulting", ["prof_services_consulting", "prof. services/consulting", "client_mix_prof_services", "professional_services", "consulting"], True, "0%", False, "000000"),
    ("BFSI", ["bfsi", "client_mix_bfsi", "industry_bfsi", "financial_services"], True, "0%", False, "000000"),
    ("Co-working & Allied Revenue (₹ Cr)", ["coworking_allied_revenue", "co-working & allied revenue", "coworking_revenue", "co-working space on rent"], False, "#,##0", False, "000000"),
    ("Construction & Fit-out Revenue (₹ Cr)", ["fitout_revenue", "construction & fit-out revenue", "construction_fitout_revenue", "construction and fit-out"], False, "#,##0", False, "000000"),
    ("Others Revenue (₹ Cr)", ["others_revenue", "others revenue", "other_operating_revenue", "other_revenue"], False, "#,##0", False, "000000"),
]


# ---------------------------------------------------------------------------
# MASTER Sheet Builder (Image 1 Format)
# ---------------------------------------------------------------------------

MASTER_SECTIONS = [
    ("Revenue (Reported)", "revenue", False, "#,##0"),
    ("EBITDA (Reported)", "operating_profit", False, "#,##0"),
    ("EBITDA Margin % (Reported)", "operating_margin", True, "0.0%"),
    ("PAT / Net Profit (Reported)", "net_profit", False, "#,##0"),
]


def _build_master_sheet(ws, companies_data: List[Dict[str, Any]], periods: List[str]) -> None:
    """Build the cross-company MASTER comparison sheet matching Image 1."""
    n_periods = len(periods)
    LABEL_COL = 1
    DATA_START_COL = 2
    END_COL = DATA_START_COL + n_periods - 1

    # 1. Main Title Banner (Dark Navy, Bold, White)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=END_COL)
    title_cell = ws.cell(row=1, column=1)
    _style_cell(
        title_cell,
        value="MASTER — Coworking Sector Review (Cross-Company KPI Comparison)",
        bg=C_NAVY_BANNER, fg=C_NAVY_TEXT,
        bold=True, size=13, h_align="left",
    )
    ws.row_dimensions[1].height = 26

    current_row = 3  # row 2 is blank spacer

    for section_label, data_key, is_pct, num_fmt in MASTER_SECTIONS:
        has_any_data = False
        for co in companies_data:
            pmap = _build_period_data_map(co)
            for p in periods:
                if pmap.get(p, {}).get(data_key) is not None:
                    has_any_data = True
                    break
            if has_any_data:
                break

        if not has_any_data and data_key == "net_profit":
            continue

        # A. Section Header Bar (Light Blue, Bold Navy text)
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=END_COL)
        _style_cell(
            ws.cell(row=current_row, column=1),
            value=section_label,
            bg=C_SECTION_BG, fg=C_SECTION_FG,
            bold=True, size=11, h_align="left",
        )
        ws.row_dimensions[current_row].height = 20
        current_row += 1

        # B. ACTUAL Sub-label row
        _style_cell(ws.cell(row=current_row, column=LABEL_COL), value="", bg=C_ACTUAL_BG, fg=C_ACTUAL_FG)
        if n_periods > 0:
            ws.merge_cells(start_row=current_row, start_column=DATA_START_COL, end_row=current_row, end_column=END_COL)
            _style_cell(
                ws.cell(row=current_row, column=DATA_START_COL),
                value="ACTUAL",
                bg=C_ACTUAL_BG, fg=C_ACTUAL_FG,
                bold=True, size=9, h_align="center",
            )
        ws.row_dimensions[current_row].height = 16
        current_row += 1

        # C. Quarter Column Headers
        _style_cell(ws.cell(row=current_row, column=LABEL_COL), value="", bg=C_QTR_BG, fg=C_QTR_FG)
        for p_idx, p in enumerate(periods):
            _style_cell(
                ws.cell(row=current_row, column=DATA_START_COL + p_idx),
                value=p,
                bg=C_QTR_BG, fg=C_QTR_FG,
                bold=True, size=10, h_align="center",
            )
        ws.row_dimensions[current_row].height = 18
        current_row += 1

        # D. Company Data Rows
        totals: Dict[str, float] = {p: 0.0 for p in periods}
        counts: Dict[str, int] = {p: 0 for p in periods}
        has_val: Dict[str, bool] = {p: False for p in periods}

        for row_idx, co in enumerate(companies_data):
            pmap = _build_period_data_map(co)
            is_even = (row_idx % 2 == 0)
            row_bg = C_ZEBRA_EVEN if is_even else C_ZEBRA_ODD

            # Company name in italic font
            _style_cell(
                ws.cell(row=current_row, column=LABEL_COL),
                value=co.get("name", "Unknown Company"),
                bg=row_bg, fg=C_TEXT_MAIN,
                italic=True, size=10, h_align="left",
            )

            for p_idx, p in enumerate(periods):
                raw = pmap.get(p, {}).get(data_key)
                norm_val = _normalize_metric_val(raw, is_pct=is_pct, scale_cr=True)
                cell = ws.cell(row=current_row, column=DATA_START_COL + p_idx)

                if norm_val is None:
                    # Space is kept empty if data is not available
                    _style_cell(cell, value=None, bg=row_bg, fg=C_TEXT_MAIN, h_align="center")
                else:
                    _style_cell(cell, value=norm_val, bg=row_bg, fg=C_TEXT_MAIN, h_align="right", num_format=num_fmt)
                    if isinstance(norm_val, (int, float)):
                        totals[p] += norm_val
                        counts[p] += 1
                        has_val[p] = True

            ws.row_dimensions[current_row].height = 18
            current_row += 1

        # E. Total Row (Bold, Soft Gray Fill, Double Bottom Border)
        total_label = f"Total {section_label}"
        _style_cell(
            ws.cell(row=current_row, column=LABEL_COL),
            value=total_label,
            bg=C_TOTAL_BG, fg=C_TOTAL_FG,
            bold=True, size=10, h_align="left",
            border=_get_total_border(),
        )

        for p_idx, p in enumerate(periods):
            cell = ws.cell(row=current_row, column=DATA_START_COL + p_idx)
            if is_pct:
                avg_val = (totals[p] / counts[p]) if counts[p] > 0 else None
                if avg_val is not None:
                    _style_cell(cell, value=avg_val, bg=C_TOTAL_BG, fg=C_TOTAL_FG, bold=True, h_align="right", num_format=num_fmt, border=_get_total_border())
                else:
                    _style_cell(cell, value=None, bg=C_TOTAL_BG, fg=C_TOTAL_FG, bold=True, h_align="center", border=_get_total_border())
            else:
                if has_val[p]:
                    _style_cell(cell, value=totals[p], bg=C_TOTAL_BG, fg=C_TOTAL_FG, bold=True, h_align="right", num_format=num_fmt, border=_get_total_border())
                else:
                    _style_cell(cell, value=None, bg=C_TOTAL_BG, fg=C_TOTAL_FG, bold=True, h_align="center", border=_get_total_border())

        ws.row_dimensions[current_row].height = 19
        current_row += 2

    # Column widths
    ws.column_dimensions[get_column_letter(LABEL_COL)].width = 38
    for p_idx in range(n_periods):
        ws.column_dimensions[get_column_letter(DATA_START_COL + p_idx)].width = 14

    ws.freeze_panes = "B4"
    ws.views.sheetView[0].showGridLines = True


# ---------------------------------------------------------------------------
# Coworking vs Adaptive Model Detection & Data Fields
# ---------------------------------------------------------------------------

COWORKING_EXCLUSIVE_ALIASES = [
    "signed_supply_centers", "signed_supply_seats", "signed_supply_area_incl_loi",
    "signed_supply_area", "total_centers_op_fitout", "total_seats_op_fitout",
    "operational_seats", "ma_portfolio_pct", "blended_occupancy", ">12m_vintage_occ",
    "100+_seats_enterprise", "51_100_seats", "1_50_seats", ">=_24_months",
    "12_23_months", "<_12_months", "coworking_allied_revenue", "fitout_revenue",
    "cities", "w_avg_total_tenure_mos", "multi_center_clients_pct"
]

ADAPTIVE_HEADLINE_FIELDS = [
    # (Label, key_aliases, is_pct, num_format, is_yellow_headline, font_color)
    ("Revenue from Ops (₹ Cr)", ["revenue_from_ops", "revenue from ops", "total_revenue", "sales", "revenue"], False, "#,##0.0", True, "000000"),
    ("Operating EBITDA (₹ Cr)", ["operating_ebitda", "operating ebitda", "operating_profit", "ebitda", "op_profit"], False, "#,##0.0", True, "000000"),
    ("Op. EBITDA Margin (%)", ["op_ebitda_margin", "op. ebitda margin", "operating_margin", "ebitda_margin", "opm"], True, "0.00%", True, "000000"),
    ("Reported PAT (₹ Cr)", ["reported_pat", "reported pat", "net_profit", "pat", "profit_after_tax"], False, "#,##0.0", True, "000000"),
    ("Diluted EPS (₹)", ["diluted_eps", "eps"], False, "#,##0.00", True, "000000"),
]

ADAPTIVE_STATEMENT_FIELDS = [
    ("Operating Expenses (₹ Cr)", ["operating_expenses", "expenses"], False, "#,##0.0", False, "000000"),
    ("Other Income (₹ Cr)", ["other_income"], False, "#,##0.0", False, "000000"),
    ("Interest / Finance Costs (₹ Cr)", ["interest_/_finance_costs", "interest", "finance_costs"], False, "#,##0.0", False, "000000"),
    ("Depreciation (₹ Cr)", ["depreciation"], False, "#,##0.0", False, "000000"),
    ("Profit before tax (PBT) (₹ Cr)", ["profit_before_tax_pbt", "profit_before_tax", "pbt"], False, "#,##0.0", False, "000000"),
    ("Effective Tax Rate (%)", ["effective_tax_rate_pct", "tax_pct", "tax_rate"], True, "0.00%", False, "000000"),
]


def _is_coworking_company(company_data: Dict[str, Any]) -> bool:
    """Determine whether the company has real Coworking / Managed Workspace operational data."""
    # 1. Sector or About metadata match
    sector_str = str(company_data.get("sector", "")).lower()
    about_str = str(company_data.get("about", "")).lower()
    name_str = str(company_data.get("name", "")).lower()
    for kw in ("coworking", "co-working", "flexible workspace", "flex space", "managed workspace"):
        if kw in sector_str or kw in about_str or kw in name_str:
            return True

    # 2. Check if any period has real non-null data for coworking-exclusive metrics
    pmap = _build_period_data_map(company_data)
    for p in pmap:
        for alias in COWORKING_EXCLUSIVE_ALIASES:
            raw = _extract_metric_for_period(pmap, p, [alias])
            if raw is not None and str(raw).strip() not in ("", "-", "—", "None", "0", "0.0"):
                return True
    return False


# ---------------------------------------------------------------------------
# Per-Company Breakdown Builders (Coworking Model & Adaptive Disclosed Model)
# ---------------------------------------------------------------------------

def _build_coworking_company_block(
    ws,
    company_data: Dict[str, Any],
    periods: List[str],
    start_row: int,
) -> int:
    """Write the complete company table with ALL EXACT DATA FIELDS from Image 2 (Coworking Model).
    If a field is not available in the transcript/data for that period, the cell
    value is left empty.
    Returns the next available row index.
    """
    n_periods = len(periods)
    METRIC_COL = 1
    DATA_START_COL = 2
    END_COL = DATA_START_COL + max(n_periods - 1, 0)
    company_name = company_data.get("name", "Unknown Company")
    ticker = company_data.get("ticker", "")

    # 1. Company Navy Header Banner
    ws.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=END_COL)
    banner_text = company_name if not ticker else f"{company_name}  ({ticker})"
    _style_cell(
        ws.cell(row=start_row, column=1),
        value=banner_text,
        bg=C_NAVY_BANNER, fg=C_NAVY_TEXT,
        bold=True, size=12, h_align="left",
    )
    ws.row_dimensions[start_row].height = 22
    cur_row = start_row + 1

    # 2. Metric & Quarter Column Headers
    _style_cell(
        ws.cell(row=cur_row, column=METRIC_COL),
        value="Metric",
        bg=C_QTR_BG, fg=C_QTR_FG,
        bold=True, size=10, h_align="left",
    )
    for p_idx, p in enumerate(periods):
        _style_cell(
            ws.cell(row=cur_row, column=DATA_START_COL + p_idx),
            value=p,
            bg=C_QTR_BG, fg=C_QTR_FG,
            bold=True, size=10, h_align="center",
        )
    ws.row_dimensions[cur_row].height = 18
    cur_row += 1

    pmap = _build_period_data_map(company_data)

    # Check if this company uses EFC-style labels ("Total Revenue", "EBITDA") or Awfis-style
    is_efc = "efc" in str(company_name).lower() or "efc" in str(ticker).lower()

    # 3. Write ALL EXACT DATA FIELDS (unconditional row creation)
    for row_idx, (label, aliases, is_pct, num_fmt, is_yellow, font_color) in enumerate(EXACT_COWORKING_FIELDS):
        display_label = label
        if is_efc:
            if "Revenue from Ops" in label:
                display_label = "Total Revenue (₹ Cr)"
            elif "Operating EBITDA" in label:
                display_label = "EBITDA (₹ Cr)"
            elif "Op. EBITDA Margin" in label:
                display_label = "EBITDA Margin (%)"
            elif "Reported PAT" in label:
                display_label = "PAT (₹ Cr)"

        lbl_bg = C_YELLOW_KPI if is_yellow else (C_ZEBRA_EVEN if row_idx % 2 == 0 else C_ZEBRA_ODD)
        lbl_fg = C_YELLOW_TEXT if is_yellow else C_TEXT_MAIN
        data_bg = C_ZEBRA_EVEN if row_idx % 2 == 0 else C_ZEBRA_ODD
        is_bold = is_yellow

        # Write Metric Label (Only Column A gets yellow highlight if headline)
        _style_cell(
            ws.cell(row=cur_row, column=METRIC_COL),
            value=display_label,
            bg=lbl_bg, fg=lbl_fg,
            bold=is_bold, size=10, h_align="left",
        )

        # Write Data for each Period; if not available, KEEP CELL VALUE EMPTY (None)
        for p_idx, p in enumerate(periods):
            raw = _extract_metric_for_period(pmap, p, aliases)
            norm_val = _normalize_metric_val(raw, is_pct=is_pct, scale_cr=True)
            cell = ws.cell(row=cur_row, column=DATA_START_COL + p_idx)

            if norm_val is None:
                # Cell value is kept empty (None) with clean white/zebra background and borders
                _style_cell(cell, value=None, bg=data_bg, fg=font_color, h_align="center")
            else:
                _style_cell(
                    cell,
                    value=norm_val,
                    bg=data_bg,
                    fg=font_color,
                    bold=is_bold,
                    h_align="right",
                    num_format=num_fmt,
                )

        ws.row_dimensions[cur_row].height = 18
        cur_row += 1

    # Column Widths
    ws.column_dimensions[get_column_letter(METRIC_COL)].width = 38
    for p_idx in range(n_periods):
        ws.column_dimensions[get_column_letter(DATA_START_COL + p_idx)].width = 14

    return cur_row + 2


def _build_adaptive_company_block(
    ws,
    company_data: Dict[str, Any],
    periods: List[str],
    start_row: int,
) -> int:
    """Write an adaptive company table displaying all real extracted financial and
    operational metrics without forcing inapplicable coworking fields.
    """
    n_periods = len(periods)
    METRIC_COL = 1
    DATA_START_COL = 2
    END_COL = DATA_START_COL + max(n_periods - 1, 0)
    company_name = company_data.get("name", "Unknown Company")
    ticker = company_data.get("ticker", "")
    sector = company_data.get("sector") or "Financial & Operational Review"

    # 1. Company Navy Header Banner
    ws.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=END_COL)
    banner_text = company_name if not ticker else f"{company_name}  ({ticker}) — {sector}"
    _style_cell(
        ws.cell(row=start_row, column=1),
        value=banner_text,
        bg=C_NAVY_BANNER, fg=C_NAVY_TEXT,
        bold=True, size=12, h_align="left",
    )
    ws.row_dimensions[start_row].height = 22
    cur_row = start_row + 1

    # 2. Metric & Quarter Column Headers
    _style_cell(
        ws.cell(row=cur_row, column=METRIC_COL),
        value="Metric",
        bg=C_QTR_BG, fg=C_QTR_FG,
        bold=True, size=10, h_align="left",
    )
    for p_idx, p in enumerate(periods):
        _style_cell(
            ws.cell(row=cur_row, column=DATA_START_COL + p_idx),
            value=p,
            bg=C_QTR_BG, fg=C_QTR_FG,
            bold=True, size=10, h_align="center",
        )
    ws.row_dimensions[cur_row].height = 18
    cur_row += 1

    pmap = _build_period_data_map(company_data)

    # 3. Section 1: Headline Financial Highlights (Yellow Rows)
    for row_idx, (label, aliases, is_pct, num_fmt, is_yellow, font_color) in enumerate(ADAPTIVE_HEADLINE_FIELDS):
        lbl_bg = C_YELLOW_KPI if is_yellow else (C_ZEBRA_EVEN if row_idx % 2 == 0 else C_ZEBRA_ODD)
        lbl_fg = C_YELLOW_TEXT if is_yellow else C_TEXT_MAIN
        data_bg = C_ZEBRA_EVEN if row_idx % 2 == 0 else C_ZEBRA_ODD
        is_bold = is_yellow

        _style_cell(
            ws.cell(row=cur_row, column=METRIC_COL),
            value=label,
            bg=lbl_bg, fg=lbl_fg,
            bold=is_bold, size=10, h_align="left",
        )
        for p_idx, p in enumerate(periods):
            raw = _extract_metric_for_period(pmap, p, aliases)
            norm_val = _normalize_metric_val(raw, is_pct=is_pct, scale_cr=True)
            cell = ws.cell(row=cur_row, column=DATA_START_COL + p_idx)
            if norm_val is None:
                _style_cell(cell, value=None, bg=data_bg, fg=font_color, h_align="center")
            else:
                _style_cell(cell, value=norm_val, bg=data_bg, fg=font_color, bold=is_bold, h_align="right", num_format=num_fmt)
        ws.row_dimensions[cur_row].height = 18
        cur_row += 1

    # 4. Section 2: Complete Operating & P&L Statement
    ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=END_COL)
    _style_cell(
        ws.cell(row=cur_row, column=1),
        value="FINANCIAL PERFORMANCE STATEMENT",
        bg=C_SECTION_BG, fg=C_SECTION_FG,
        bold=True, size=10, h_align="left",
    )
    ws.row_dimensions[cur_row].height = 18
    cur_row += 1

    for row_idx, (label, aliases, is_pct, num_fmt, is_yellow, font_color) in enumerate(ADAPTIVE_STATEMENT_FIELDS):
        row_bg = C_ZEBRA_EVEN if row_idx % 2 == 0 else C_ZEBRA_ODD
        _style_cell(
            ws.cell(row=cur_row, column=METRIC_COL),
            value=label,
            bg=row_bg, fg=C_TEXT_MAIN,
            bold=False, size=10, h_align="left",
        )
        for p_idx, p in enumerate(periods):
            raw = _extract_metric_for_period(pmap, p, aliases)
            norm_val = _normalize_metric_val(raw, is_pct=is_pct, scale_cr=True)
            cell = ws.cell(row=cur_row, column=DATA_START_COL + p_idx)
            if norm_val is None:
                _style_cell(cell, value=None, bg=row_bg, fg=font_color, h_align="center")
            else:
                _style_cell(cell, value=norm_val, bg=row_bg, fg=font_color, bold=False, h_align="right", num_format=num_fmt)
        ws.row_dimensions[cur_row].height = 18
        cur_row += 1

    # 5. Section 3: Disclosed Operational & Business Metrics (Only if actually present)
    known_clean = set()
    for label, aliases, _, _, _, _ in ADAPTIVE_HEADLINE_FIELDS + ADAPTIVE_STATEMENT_FIELDS:
        known_clean.add(re.sub(r"[^a-z0-9]", "", label.lower()))
        for a in aliases:
            known_clean.add(re.sub(r"[^a-z0-9]", "", a.lower()))

    ignore_clean = {
        "period", "id", "companyid", "documentid", "createdat", "currency",
        "revenuegrowth", "profitgrowth", "totalassets", "totalliabilities", "cashflow",
        "salescr", "expensescr", "operatingprofitcr", "otherincomecr", "interestcr",
        "depreciationcr", "pbtcr", "taxpct", "netprofitcr", "opmpct", "eps",
    }

    discovered_metrics: List[str] = []
    seen_disc: set[str] = set()
    for p in periods:
        p_dict = pmap.get(p, {})
        for k, v in p_dict.items():
            if v is None or v == "" or str(v).strip() in ("-", "—", "None"):
                continue
            clean_k = re.sub(r"[^a-z0-9]", "", str(k).lower())
            if not clean_k or clean_k in known_clean or clean_k in ignore_clean:
                continue
            if "_" in str(k) and any(re.sub(r"[^a-z0-9]", "", str(x).lower()) == clean_k for x in p_dict if "_" not in str(x)):
                continue
            if clean_k not in seen_disc:
                seen_disc.add(clean_k)
                discovered_metrics.append(str(k))

    if discovered_metrics:
        ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=END_COL)
        _style_cell(
            ws.cell(row=cur_row, column=1),
            value="DISCLOSED OPERATIONAL & BUSINESS METRICS",
            bg=C_SUBHDR_BG, fg=C_SUBHDR_FG,
            bold=True, size=10, h_align="left",
        )
        ws.row_dimensions[cur_row].height = 18
        cur_row += 1

        for row_idx, m_name in enumerate(discovered_metrics):
            row_bg = C_ZEBRA_EVEN if row_idx % 2 == 0 else C_ZEBRA_ODD
            is_pct = "%" in m_name or "pct" in m_name.lower() or "margin" in m_name.lower()
            num_fmt = "0.0%" if is_pct else ("#,##0.0" if "cr" in m_name.lower() else "#,##0")

            _style_cell(
                ws.cell(row=cur_row, column=METRIC_COL),
                value=m_name,
                bg=row_bg, fg=C_TEXT_MAIN,
                bold=False, size=10, h_align="left",
            )
            for p_idx, p in enumerate(periods):
                raw = _extract_metric_for_period(pmap, p, [m_name])
                norm_val = _normalize_metric_val(raw, is_pct=is_pct, scale_cr=True)
                cell = ws.cell(row=cur_row, column=DATA_START_COL + p_idx)
                if norm_val is None:
                    _style_cell(cell, value=None, bg=row_bg, fg=C_TEXT_MAIN, h_align="center")
                else:
                    _style_cell(cell, value=norm_val, bg=row_bg, fg=C_TEXT_MAIN, h_align="right", num_format=num_fmt)
            ws.row_dimensions[cur_row].height = 18
            cur_row += 1

    # 6. Key Valuation & Return Ratios
    ratios = company_data.get("ratios") or {}
    if ratios:
        ws.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=END_COL)
        _style_cell(
            ws.cell(row=cur_row, column=1),
            value="KEY VALUATION & RETURN RATIOS",
            bg=C_RATIOS_BG, fg=C_RATIOS_FG,
            bold=True, size=10, h_align="left",
        )
        ws.row_dimensions[cur_row].height = 18
        cur_row += 1

        for r_idx, (k, v) in enumerate(ratios.items()):
            bg = C_ZEBRA_EVEN if r_idx % 2 == 0 else C_ZEBRA_ODD
            _style_cell(ws.cell(row=cur_row, column=1), value=str(k), bg=bg, fg=C_TEXT_MAIN, h_align="left")
            _style_cell(ws.cell(row=cur_row, column=2), value=str(v), bg=bg, fg=C_TEXT_MAIN, h_align="left")
            for c_idx in range(3, END_COL + 1):
                _style_cell(ws.cell(row=cur_row, column=c_idx), value="", bg=bg, fg=C_TEXT_MAIN)
            ws.row_dimensions[cur_row].height = 17
            cur_row += 1

    # Column Widths
    ws.column_dimensions[get_column_letter(METRIC_COL)].width = 38
    for p_idx in range(n_periods):
        ws.column_dimensions[get_column_letter(DATA_START_COL + p_idx)].width = 14

    return cur_row + 2


def _build_single_company_block(
    ws,
    company_data: Dict[str, Any],
    periods: List[str],
    start_row: int,
    template: str = "auto",
) -> int:
    """Dispatch to the Coworking Model or Adaptive General Model based on data or explicit selection."""
    if template == "coworking":
        return _build_coworking_company_block(ws, company_data, periods, start_row)
    elif template == "adaptive":
        return _build_adaptive_company_block(ws, company_data, periods, start_row)
    else:
        # auto-detect
        if _is_coworking_company(company_data):
            return _build_coworking_company_block(ws, company_data, periods, start_row)
        else:
            return _build_adaptive_company_block(ws, company_data, periods, start_row)


# ---------------------------------------------------------------------------
# Auxiliary Sheets (Company Overview, Standard Financials, Risks, Docs)
# ---------------------------------------------------------------------------

def _build_overview_sheet(ws, company_data: Dict[str, Any]) -> None:
    """Company Dossier Overview sheet (preserving compatibility and full info)."""
    company_name = company_data.get("name", "Unknown Company")
    ticker = company_data.get("ticker", "N/A")
    ws.views.sheetView[0].showGridLines = True

    ws.merge_cells("A1:D2")
    title_cell = ws["A1"]
    title_cell.value = f"Financial Dossier: {company_name} ({ticker})"
    title_cell.font = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color=C_NAVY_BANNER, end_color=C_NAVY_BANNER, fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    rows = [
        ("Company Name", company_name),
        ("Ticker / Symbol", ticker),
        ("Investor Website", company_data.get("website", "N/A")),
        ("Sector", company_data.get("sector", "Coworking / Real Estate")),
        ("Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("Primary Currency", company_data.get("currency", "INR")),
        ("Latest Report Period", company_data.get("latest_period", "N/A")),
        ("Total Reports Tracked", len(company_data.get("documents", []))),
        ("Total Identified Risks", len(company_data.get("risks", []))),
    ]
    for idx, (label, val) in enumerate(rows, start=4):
        c1 = ws.cell(row=idx, column=1)
        c2 = ws.cell(row=idx, column=2)
        _style_cell(c1, label, bg="1E293B", fg="FFFFFF", bold=True)
        _style_cell(c2, val, bg=C_ZEBRA_EVEN if idx % 2 == 0 else C_ZEBRA_ODD, fg=C_TEXT_MAIN)

    _auto_fit_columns(ws, min_width=18)


def _build_standard_financials_sheet(ws, company_data: Dict[str, Any]) -> None:
    """Standard Financial Metrics sheet (preserving 'Financial Metrics' sheet name for tests)."""
    ws.views.sheetView[0].showGridLines = True
    headers = [
        "Period", "Revenue", "Revenue Growth", "Net Profit", "Profit Growth",
        "Operating Profit", "Operating Margin", "EPS", "Total Assets", "Total Liabilities", "Cash Flow", "Currency"
    ]
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        _style_cell(cell, h, bg=C_NAVY_BANNER, fg="FFFFFF", bold=True, h_align="center")

    metrics = company_data.get("financial_data", [])
    for row_idx, m in enumerate(metrics, start=2):
        is_even = (row_idx % 2 == 0)
        bg = C_ZEBRA_EVEN if is_even else C_ZEBRA_ODD
        curr = m.get("currency", company_data.get("currency", "INR"))
        _style_cell(ws.cell(row=row_idx, column=1), m.get("period", "N/A"), bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=2), m.get("revenue"), bg=bg, h_align="right", num_format="#,##0")
        _style_cell(ws.cell(row=row_idx, column=3), m.get("revenue_growth"), bg=bg, h_align="right", num_format="0.00%")
        _style_cell(ws.cell(row=row_idx, column=4), m.get("net_profit"), bg=bg, h_align="right", num_format="#,##0")
        _style_cell(ws.cell(row=row_idx, column=5), m.get("profit_growth"), bg=bg, h_align="right", num_format="0.00%")
        _style_cell(ws.cell(row=row_idx, column=6), m.get("operating_profit"), bg=bg, h_align="right", num_format="#,##0")
        _style_cell(ws.cell(row=row_idx, column=7), m.get("operating_margin"), bg=bg, h_align="right", num_format="0.00%")
        _style_cell(ws.cell(row=row_idx, column=8), m.get("eps"), bg=bg, h_align="right", num_format="#,##0.00")
        _style_cell(ws.cell(row=row_idx, column=9), m.get("total_assets"), bg=bg, h_align="right", num_format="#,##0")
        _style_cell(ws.cell(row=row_idx, column=10), m.get("total_liabilities"), bg=bg, h_align="right", num_format="#,##0")
        _style_cell(ws.cell(row=row_idx, column=11), m.get("cash_flow"), bg=bg, h_align="right", num_format="#,##0")
        _style_cell(ws.cell(row=row_idx, column=12), curr, bg=bg, h_align="center")

    _auto_fit_columns(ws, min_width=14)


def _build_risks_sheet(ws, risks: List[Dict[str, Any]]) -> None:
    ws.views.sheetView[0].showGridLines = True
    headers = ["ID", "Category / Risk Title", "Description & Impact", "Source Page", "Detected Period"]
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        _style_cell(cell, h, bg=C_NAVY_BANNER, fg="FFFFFF", bold=True, h_align="center")

    for row_idx, r in enumerate(risks, start=2):
        is_even = (row_idx % 2 == 0)
        bg = C_ZEBRA_EVEN if is_even else C_ZEBRA_ODD
        _style_cell(ws.cell(row=row_idx, column=1), row_idx - 1, bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=2), r.get("risk", "Unknown Risk"), bg=bg)
        _style_cell(ws.cell(row=row_idx, column=3), r.get("description", ""), bg=bg, wrap=True)
        _style_cell(ws.cell(row=row_idx, column=4), f"Page {r.get('page_number', 'N/A')}", bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=5), r.get("period", "N/A"), bg=bg, h_align="center")

    _auto_fit_columns(ws, min_width=14)
    ws.column_dimensions["C"].width = 50


def _build_documents_sheet(ws, docs: List[Dict[str, Any]]) -> None:
    ws.views.sheetView[0].showGridLines = True
    headers = ["Doc ID", "Report Filename", "Document Type", "Period", "SHA-256 Hash", "Status", "Downloaded At"]
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        _style_cell(cell, h, bg=C_NAVY_BANNER, fg="FFFFFF", bold=True, h_align="center")

    for row_idx, d in enumerate(docs, start=2):
        is_even = (row_idx % 2 == 0)
        bg = C_ZEBRA_EVEN if is_even else C_ZEBRA_ODD
        _style_cell(ws.cell(row=row_idx, column=1), d.get("id", row_idx - 1), bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=2), d.get("file_name", "report.pdf"), bg=bg)
        _style_cell(ws.cell(row=row_idx, column=3), d.get("document_type", "annual_report"), bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=4), d.get("report_period", "N/A"), bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=5), d.get("file_hash", "N/A"), bg=bg)
        _style_cell(ws.cell(row=row_idx, column=6), str(d.get("processing_status", "processed")).upper(), bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=7), str(d.get("downloaded_at", "")), bg=bg, h_align="center")

    _auto_fit_columns(ws, min_width=16)


def _build_pdf_chunks_sheet(ws, pdf_chunks: List[Dict[str, Any]]) -> None:
    ws.views.sheetView[0].showGridLines = True
    headers = ["Chunk #", "Doc ID", "Page Start", "Page End", "Extracted Text Content"]
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        _style_cell(cell, h, bg=C_NAVY_BANNER, fg="FFFFFF", bold=True, h_align="center")

    for row_idx, chunk in enumerate(pdf_chunks, start=2):
        is_even = (row_idx % 2 == 0)
        bg = C_ZEBRA_EVEN if is_even else C_ZEBRA_ODD
        _style_cell(ws.cell(row=row_idx, column=1), chunk.get("chunk_index", row_idx - 2), bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=2), chunk.get("document_id", "-"), bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=3), chunk.get("page_start", 1), bg=bg, h_align="center")
        _style_cell(ws.cell(row=row_idx, column=4), chunk.get("page_end", 1), bg=bg, h_align="center")

        content = chunk.get("content", "")
        if len(content) > 32000:
            content = content[:32000] + "... [TRUNCATED]"
        _style_cell(ws.cell(row=row_idx, column=5), content, bg=bg, wrap=True)

    _auto_fit_columns(ws, min_width=12)
    ws.column_dimensions["E"].width = 80


# ---------------------------------------------------------------------------
# Public Export Functions
# ---------------------------------------------------------------------------

def generate_sector_master_excel(
    companies_data: List[Dict[str, Any]],
    output_path: Optional[Path] = None,
    template: str = "auto",
) -> Union[Path, io.BytesIO]:
    """Generate the complete Sector Review workbook.

    Sheets:
      1. 'MASTER' -> Cross-company KPI comparison (Revenue, EBITDA, EBITDA Margin %, PAT)
      2. 'Company Breakdown' -> All companies stacked with dark navy banners & sector/adaptive data fields
      3. Per-company sheets with detailed KPI breakdown tabs

    Args:
        companies_data: List of company dictionaries.
        output_path: Optional output file path. Returns in-memory BytesIO if None.
        template: 'auto' (auto-detects each company), 'coworking', or 'adaptive'.
    """
    try:
        settings = get_settings()
        settings.EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("Generating sector master Excel workbook for %d companies (template=%s)", len(companies_data), template)
        wb = openpyxl.Workbook()
        periods = _collect_periods(companies_data)

        # Sheet 1: MASTER
        ws_master = wb.active
        ws_master.title = "MASTER"
        _build_master_sheet(ws_master, companies_data, periods)

        # Sheet 2: Company Breakdown (All companies stacked)
        ws_breakdown = wb.create_sheet(title="Company Breakdown")
        ws_breakdown.views.sheetView[0].showGridLines = True
        next_row = 1
        for co in companies_data:
            next_row = _build_single_company_block(ws_breakdown, co, periods, start_row=next_row, template=template)

        # Per-Company dedicated sheets
        existing_names = {"MASTER", "Company Breakdown"}
        for co in companies_data:
            raw_title = (co.get("ticker") or co.get("name", "Company"))[:30]
            sheet_title = raw_title
            suffix = 2
            while sheet_title in existing_names:
                sheet_title = f"{raw_title[:27]}_{suffix}"
                suffix += 1
            existing_names.add(sheet_title)
            ws_co = wb.create_sheet(title=sheet_title)
            ws_co.views.sheetView[0].showGridLines = True
            _build_single_company_block(ws_co, co, periods, start_row=1, template=template)

        return _save_or_stream(wb, output_path, label="sector master")

    except Exception as exc:
        logger.exception("Failed to generate sector master Excel: %s", exc)
        raise


def generate_company_excel(
    company_data: Dict[str, Any],
    output_path: Optional[Path] = None,
    template: str = "auto",
    include_auxiliary_sheets: bool = False,
) -> Union[Path, io.BytesIO]:
    """Generate a clean Excel workbook for a single company.

    By default, generates ONLY the primary 'KPI Breakdown' sheet containing the
    exact financial & operational model. Auxiliary sheets (Overview, Risks, Docs, PDF content)
    are excluded unless include_auxiliary_sheets=True.
    """
    try:
        settings = get_settings()
        settings.EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        company_name = company_data.get("name", "Unknown Company")
        ticker = company_data.get("ticker", "N/A")
        logger.info(
            "Generating company Excel workbook for '%s' (%s) [template=%s, aux_sheets=%s]",
            company_name, ticker, template, include_auxiliary_sheets,
        )

        wb = openpyxl.Workbook()
        periods = _collect_periods([company_data])

        # Sheet 1: KPI Breakdown (Primary analyst research matrix)
        ws_kpi = wb.active
        ws_kpi.title = "KPI Breakdown"
        ws_kpi.views.sheetView[0].showGridLines = True
        _build_single_company_block(ws_kpi, company_data, periods, start_row=1, template=template)

        # Optional auxiliary sheets (only when requested)
        if include_auxiliary_sheets:
            ws_overview = wb.create_sheet(title="Company Overview")
            _build_overview_sheet(ws_overview, company_data)

            ws_fin = wb.create_sheet(title="Financial Metrics")
            _build_standard_financials_sheet(ws_fin, company_data)

            ws_risks = wb.create_sheet(title="Risk Factors")
            _build_risks_sheet(ws_risks, company_data.get("risks", []))

            ws_docs = wb.create_sheet(title="Document Registry")
            _build_documents_sheet(ws_docs, company_data.get("documents", []))

            pdf_chunks = company_data.get("pdf_chunks", [])
            if pdf_chunks:
                ws_pdf = wb.create_sheet(title="PDF Extracted Content")
                _build_pdf_chunks_sheet(ws_pdf, pdf_chunks)

        return _save_or_stream(wb, output_path, label=f"company '{company_name}'")

    except Exception as exc:
        logger.exception("Failed to generate company Excel for '%s': %s", company_data.get("name"), exc)
        raise


def generate_company_csv(company_data: Dict[str, Any]) -> str:
    """Generate a clean CSV string of the company's financial metrics."""
    try:
        metrics_list = company_data.get("financial_data", [])
        if not metrics_list:
            return "period,revenue,revenue_growth,net_profit,profit_growth,operating_profit,operating_margin,eps,currency\n"

        lines = ["period,revenue,revenue_growth,net_profit,profit_growth,operating_profit,operating_margin,eps,currency"]
        for m in metrics_list:
            line = (
                f'"{m.get("period", "")}",'
                f'{m.get("revenue", "")},'
                f'{m.get("revenue_growth", "")},'
                f'{m.get("net_profit", "")},'
                f'{m.get("profit_growth", "")},'
                f'{m.get("operating_profit", "")},'
                f'{m.get("operating_margin", "")},'
                f'{m.get("eps", "")},'
                f'"{m.get("currency", "USD")}"'
            )
            lines.append(line)

        csv_result = "\n".join(lines)
        logger.info("Generated CSV metrics string for '%s' (%d lines)", company_data.get("name"), len(lines))
        return csv_result
    except Exception as exc:
        logger.exception("Failed to generate CSV for '%s': %s", company_data.get("name"), exc)
        raise


def _save_or_stream(
    wb: openpyxl.Workbook,
    output_path: Optional[Path],
    label: str = "",
) -> Union[Path, io.BytesIO]:
    if output_path is not None:
        wb.save(output_path)
        logger.info("Saved %s Excel workbook to file: %s", label, output_path)
        return output_path
    else:
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        logger.info("Generated %s Excel workbook in-memory buffer (%d bytes)", label, len(buffer.getvalue()))
        return buffer


def generate_operational_matrix_excel(
    matrix_data: Dict[str, Any],
    output_path: Optional[Path] = None,
) -> Union[Path, io.BytesIO]:
    """Generate Excel workbook replicating the equity research analyst operational model.
    Supports either single company matrix or sector stacked matrices.
    """
    wb = openpyxl.Workbook()
    if wb.active:
        wb.remove(wb.active)

    thin = Side(border_style="thin", color="D3D3D3")
    data_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    font_bold = Font(name="Calibri", size=10, bold=True)
    font_regular = Font(name="Calibri", size=10)
    font_company = Font(name="Calibri", size=11, bold=True, color=C_NAVY_TEXT)

    fill_company = PatternFill(start_color=C_NAVY_BANNER, end_color=C_NAVY_BANNER, fill_type="solid")
    fill_qtr = PatternFill(start_color=C_QTR_BG, end_color=C_QTR_BG, fill_type="solid")
    fill_cat = PatternFill(start_color=C_SECTION_BG, end_color=C_SECTION_BG, fill_type="solid")
    fill_highlight = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")

    companies = matrix_data.get("companies", [])
    is_sector = bool(companies)
    if not is_sector:
        companies = [matrix_data]

    global_periods = matrix_data.get("global_periods") or (companies[0].get("periods", []) if companies else [])

    ws_master = wb.create_sheet(title="Operational Research Model")
    ws_master.views.sheetView[0].showGridLines = True

    current_row = 2
    ws_master.cell(
        row=current_row, column=1, value="EQUITY RESEARCH OPERATIONAL MATRIX & FINANCIAL MODEL"
    ).font = Font(name="Calibri", size=13, bold=True, color=C_NAVY_BANNER)
    current_row += 2

    total_cols = max(len(global_periods) + 2, 8)

    for comp in companies:
        c_name = comp.get("company_name") or comp.get("name") or "Company"
        c_ticker = comp.get("ticker", "")
        periods = comp.get("periods") or global_periods
        categories = comp.get("categories", [])
        total_cols = max(len(periods) + 2, 8)

        # 1. Company Banner
        ws_master.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_cols)
        banner_cell = ws_master.cell(
            row=current_row, column=1, value=f"{c_name} ({c_ticker}) - Multi-Quarter Operational Model"
        )
        banner_cell.font = font_company
        banner_cell.fill = fill_company
        banner_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_master.row_dimensions[current_row].height = 24
        current_row += 1

        # 2. Period Headers
        h_name = ws_master.cell(row=current_row, column=1, value="Metric / KPI")
        h_name.font = font_bold
        h_name.fill = fill_qtr
        h_name.alignment = Alignment(horizontal="left", vertical="center")
        h_name.border = data_border

        h_unit = ws_master.cell(row=current_row, column=2, value="Unit")
        h_unit.font = font_bold
        h_unit.fill = fill_qtr
        h_unit.alignment = Alignment(horizontal="center", vertical="center")
        h_unit.border = data_border

        col_idx = 3
        for p in periods:
            p_display = format_fiscal_period_display(p)
            p_cell = ws_master.cell(row=current_row, column=col_idx, value=p_display)
            p_cell.font = font_bold
            p_cell.fill = fill_qtr
            p_cell.alignment = Alignment(horizontal="center", vertical="center")
            p_cell.border = data_border
            col_idx += 1
        ws_master.row_dimensions[current_row].height = 20
        current_row += 1

        # 3. Categories & Metrics
        for cat in categories:
            cat_name = cat.get("category", "")
            ws_master.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=total_cols)
            cat_cell = ws_master.cell(row=current_row, column=1, value=cat_name.upper())
            cat_cell.font = Font(name="Calibri", size=10, bold=True, color=C_SECTION_FG)
            cat_cell.fill = fill_cat
            cat_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
            ws_master.row_dimensions[current_row].height = 19
            current_row += 1

            for m in cat.get("metrics", []):
                m_name = m.get("name", "")
                m_unit = m.get("unit", "")
                is_hi = m.get("is_highlight", False)
                vals = m.get("values", {})
                num_vals = m.get("numeric_values", {})

                row_fill = fill_highlight if is_hi else None
                row_font = font_bold if is_hi else font_regular

                c_metric = ws_master.cell(row=current_row, column=1, value=m_name)
                c_metric.font = row_font
                if row_fill:
                    c_metric.fill = row_fill
                c_metric.alignment = Alignment(horizontal="left", vertical="center", indent=1)
                c_metric.border = data_border

                c_u = ws_master.cell(row=current_row, column=2, value=m_unit)
                c_u.font = font_regular
                if row_fill:
                    c_u.fill = row_fill
                c_u.alignment = Alignment(horizontal="center", vertical="center")
                c_u.border = data_border

                col_idx = 3
                for p in periods:
                    val = vals.get(p, "-")
                    num_val = num_vals.get(p)
                    cell = ws_master.cell(row=current_row, column=col_idx)
                    cell.border = data_border
                    if row_fill:
                        cell.fill = row_fill

                    if num_val is not None:
                        if "%" in m_unit or "Margin" in m_name or "Occ" in m_name or "Attrition" in m_name or "SSSG" in m_name or "Utilization" in m_name or "Rate" in m_name:
                            cell.value = num_val / 100.0 if abs(num_val) > 1.0 else num_val
                            cell.number_format = "0.0%"
                        elif "Cr" in m_unit or "Revenue" in m_name or "EBITDA" in m_name or "PAT" in m_name or "Expenses" in m_name or "Profit" in m_name or "Income" in m_name or "Depreciation" in m_name:
                            cell.value = num_val
                            cell.number_format = '[$₹-4009]#,##0.0;([$₹-4009]#,##0.0);"-"'
                        elif "EPS" in m_name or m_unit == "₹":
                            cell.value = num_val
                            cell.number_format = '[$₹-4009]#,##0.00;([$₹-4009]#,##0.00);"-"'
                        elif any(u in m_unit for u in ["Seats", "Clients", "Centers", "Employees", "Stores", "Rooms", "Units", "Months"]):
                            cell.value = int(num_val)
                            cell.number_format = '#,##0;(#,##0);"-"'
                        else:
                            cell.value = num_val
                            cell.number_format = '#,##0.0;(#,##0.0);"-"'
                    else:
                        cell.value = val

                    cell.font = row_font
                    cell.alignment = Alignment(horizontal="center" if val == "-" else "right", vertical="center")
                    col_idx += 1

                ws_master.row_dimensions[current_row].height = 18
                current_row += 1

        current_row += 2

    ws_master.column_dimensions["A"].width = 38
    ws_master.column_dimensions["B"].width = 14
    for c_i in range(3, total_cols + 1):
        col_letter = get_column_letter(c_i)
        ws_master.column_dimensions[col_letter].width = 18

    return _save_or_stream(wb, output_path, label="Operational Research Model")
