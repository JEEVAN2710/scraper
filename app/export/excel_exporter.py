"""Excel and CSV export module for financial reports and metrics with comprehensive error handling."""

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def _apply_header_style(cell, text: str, bg_color: str = "0F172A", text_color: str = "FFFFFF") -> None:
    """Apply consistent styling to table header cells."""
    try:
        cell.value = text
        cell.font = Font(name="Segoe UI", size=11, bold=True, color=text_color)
        cell.fill = PatternFill(start_color=bg_color, end_color=bg_color, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    except Exception as exc:
        logger.exception("Failed to apply header style to cell: %s", exc)
        raise


def _apply_data_style(
    cell,
    value: Any,
    alignment: str = "left",
    is_zebra: bool = False,
    num_format: Optional[str] = None,
) -> None:
    """Apply consistent styling to data cells."""
    try:
        cell.value = value
        cell.font = Font(name="Segoe UI", size=10, color="1E293B")
        cell.alignment = Alignment(horizontal=alignment, vertical="center")

        thin_border = Side(border_style="thin", color="E2E8F0")
        cell.border = Border(top=thin_border, left=thin_border, right=thin_border, bottom=thin_border)

        if is_zebra:
            cell.fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        if num_format:
            cell.number_format = num_format
    except Exception as exc:
        logger.exception("Failed to apply data style to cell: %s", exc)
        raise


def _auto_fit_columns(sheet, min_width: int = 12, max_width: int = 60) -> None:
    """Dynamically adjust column widths based on cell content length."""
    try:
        for col in sheet.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            adjusted_width = max(min(max_len + 4, max_width), min_width)
            sheet.column_dimensions[col_letter].width = adjusted_width
    except Exception as exc:
        logger.warning("Auto-fit columns encountered minor error (non-fatal): %s", exc)


def generate_company_excel(
    company_data: Dict[str, Any],
    output_path: Optional[Path] = None,
) -> Union[Path, io.BytesIO]:
    """Generate a multi-sheet, beautifully formatted Excel workbook for a company.

    Sheets created:
    1. Overview (Company Dossier)
    2. Financial Metrics (Key figures and growth percentages)
    3. Risk Factors (Detailed risks with source citations)
    4. Document Registry (PDF metadata and SHA-256 hashes)

    Returns:
        Path if output_path is provided, otherwise io.BytesIO buffer.
    """
    try:
        settings = get_settings()
        settings.EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        company_name = company_data.get("name", "Unknown Company")
        ticker = company_data.get("ticker", "N/A")

        logger.info("Generating Excel workbook for company '%s' (%s)", company_name, ticker)
        wb = openpyxl.Workbook()

        # -------------------------------------------------------------
        # Sheet 1: Overview
        # -------------------------------------------------------------
        ws_overview = wb.active
        ws_overview.title = "Company Overview"
        ws_overview.views.sheetView[0].showGridLines = True

        # Title Banner
        ws_overview.merge_cells("A1:D2")
        title_cell = ws_overview["A1"]
        title_cell.value = f"Financial Dossier: {company_name} ({ticker})"
        title_cell.font = Font(name="Segoe UI", size=15, bold=True, color="FFFFFF")
        title_cell.fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        title_cell.alignment = Alignment(horizontal="center", vertical="center")

        overview_rows = [
            ("Company Name", company_name),
            ("Ticker / Symbol", ticker),
            ("Investor Website", company_data.get("website", "N/A")),
            ("Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("Primary Currency", company_data.get("currency", "USD")),
            ("Latest Report Period", company_data.get("latest_period", "N/A")),
            ("Total Reports Tracked", len(company_data.get("documents", []))),
            ("Total Identified Risks", len(company_data.get("risks", []))),
        ]

        for idx, (label, val) in enumerate(overview_rows, start=4):
            c1 = ws_overview.cell(row=idx, column=1)
            c2 = ws_overview.cell(row=idx, column=2)
            _apply_header_style(c1, label, bg_color="1E293B")
            c1.alignment = Alignment(horizontal="left", vertical="center")
            _apply_data_style(c2, val, alignment="left", is_zebra=(idx % 2 == 0))

        _auto_fit_columns(ws_overview, min_width=18)

        # -------------------------------------------------------------
        # Sheet 2: Financial Metrics
        # -------------------------------------------------------------
        ws_fin = wb.create_sheet(title="Financial Metrics")
        ws_fin.views.sheetView[0].showGridLines = True

        fin_headers = [
            "Period",
            "Revenue",
            "Revenue Growth",
            "Net Profit",
            "Profit Growth",
            "Operating Profit",
            "Operating Margin",
            "EPS",
            "Total Assets",
            "Total Liabilities",
            "Cash Flow",
            "Currency",
        ]

        for col_num, header in enumerate(fin_headers, start=1):
            cell = ws_fin.cell(row=1, column=col_num)
            _apply_header_style(cell, header, bg_color="0F172A")

        metrics_list = company_data.get("financial_data", [])
        for row_idx, metric in enumerate(metrics_list, start=2):
            is_zebra = (row_idx % 2 == 0)
            curr = metric.get("currency", "USD")

            _apply_data_style(ws_fin.cell(row=row_idx, column=1), metric.get("period", "N/A"), "center", is_zebra)
            _apply_data_style(ws_fin.cell(row=row_idx, column=2), metric.get("revenue"), "right", is_zebra, "$#,##0.00")
            _apply_data_style(ws_fin.cell(row=row_idx, column=3), metric.get("revenue_growth"), "right", is_zebra, "0.00%")
            _apply_data_style(ws_fin.cell(row=row_idx, column=4), metric.get("net_profit"), "right", is_zebra, "$#,##0.00")
            _apply_data_style(ws_fin.cell(row=row_idx, column=5), metric.get("profit_growth"), "right", is_zebra, "0.00%")
            _apply_data_style(ws_fin.cell(row=row_idx, column=6), metric.get("operating_profit"), "right", is_zebra, "$#,##0.00")
            _apply_data_style(ws_fin.cell(row=row_idx, column=7), metric.get("operating_margin"), "right", is_zebra, "0.00%")
            _apply_data_style(ws_fin.cell(row=row_idx, column=8), metric.get("eps"), "right", is_zebra, "$#,##0.00")
            _apply_data_style(ws_fin.cell(row=row_idx, column=9), metric.get("total_assets"), "right", is_zebra, "$#,##0.00")
            _apply_data_style(ws_fin.cell(row=row_idx, column=10), metric.get("total_liabilities"), "right", is_zebra, "$#,##0.00")
            _apply_data_style(ws_fin.cell(row=row_idx, column=11), metric.get("cash_flow"), "right", is_zebra, "$#,##0.00")
            _apply_data_style(ws_fin.cell(row=row_idx, column=12), curr, "center", is_zebra)

        _auto_fit_columns(ws_fin, min_width=14)

        # -------------------------------------------------------------
        # Sheet 3: Risk Factors
        # -------------------------------------------------------------
        ws_risks = wb.create_sheet(title="Risk Factors")
        ws_risks.views.sheetView[0].showGridLines = True

        risk_headers = ["ID", "Category / Risk Title", "Description & Impact", "Source Page", "Detected Period"]
        for col_num, header in enumerate(risk_headers, start=1):
            cell = ws_risks.cell(row=1, column=col_num)
            _apply_header_style(cell, header, bg_color="0F172A")

        risks_list = company_data.get("risks", [])
        for row_idx, risk in enumerate(risks_list, start=2):
            is_zebra = (row_idx % 2 == 0)
            _apply_data_style(ws_risks.cell(row=row_idx, column=1), row_idx - 1, "center", is_zebra)
            _apply_data_style(ws_risks.cell(row=row_idx, column=2), risk.get("risk", "Unknown Risk"), "left", is_zebra)
            _apply_data_style(ws_risks.cell(row=row_idx, column=3), risk.get("description", ""), "left", is_zebra)
            _apply_data_style(ws_risks.cell(row=row_idx, column=4), f"Page {risk.get('page_number', 'N/A')}", "center", is_zebra)
            _apply_data_style(ws_risks.cell(row=row_idx, column=5), risk.get("period", company_data.get("latest_period", "N/A")), "center", is_zebra)

        _auto_fit_columns(ws_risks, min_width=14)
        ws_risks.column_dimensions["C"].width = 50

        # -------------------------------------------------------------
        # Sheet 4: Document Registry
        # -------------------------------------------------------------
        ws_docs = wb.create_sheet(title="Document Registry")
        ws_docs.views.sheetView[0].showGridLines = True

        doc_headers = ["Doc ID", "Report Filename", "Document Type", "Period", "SHA-256 Hash", "Status", "Downloaded At"]
        for col_num, header in enumerate(doc_headers, start=1):
            cell = ws_docs.cell(row=1, column=col_num)
            _apply_header_style(cell, header, bg_color="0F172A")

        docs_list = company_data.get("documents", [])
        for row_idx, doc in enumerate(docs_list, start=2):
            is_zebra = (row_idx % 2 == 0)
            _apply_data_style(ws_docs.cell(row=row_idx, column=1), doc.get("id", row_idx - 1), "center", is_zebra)
            _apply_data_style(ws_docs.cell(row=row_idx, column=2), doc.get("file_name", "report.pdf"), "left", is_zebra)
            _apply_data_style(ws_docs.cell(row=row_idx, column=3), doc.get("document_type", "annual_report"), "center", is_zebra)
            _apply_data_style(ws_docs.cell(row=row_idx, column=4), doc.get("report_period", "N/A"), "center", is_zebra)
            _apply_data_style(ws_docs.cell(row=row_idx, column=5), doc.get("file_hash", "N/A"), "left", is_zebra)
            _apply_data_style(ws_docs.cell(row=row_idx, column=6), doc.get("processing_status", "processed").upper(), "center", is_zebra)
            _apply_data_style(ws_docs.cell(row=row_idx, column=7), str(doc.get("downloaded_at", datetime.now().strftime("%Y-%m-%d"))), "center", is_zebra)

        _auto_fit_columns(ws_docs, min_width=16)

        # -------------------------------------------------------------
        # Sheet 5: PDF Extracted Content (Full text from annual report)
        # -------------------------------------------------------------
        pdf_chunks = company_data.get("pdf_chunks", [])
        if pdf_chunks:
            ws_pdf = wb.create_sheet(title="PDF Extracted Content")
            ws_pdf.views.sheetView[0].showGridLines = True

            pdf_headers = ["Chunk #", "Doc ID", "Page Start", "Page End", "Extracted Text Content"]
            for col_num, header in enumerate(pdf_headers, start=1):
                cell = ws_pdf.cell(row=1, column=col_num)
                _apply_header_style(cell, header, bg_color="0F172A")

            for row_idx, chunk in enumerate(pdf_chunks, start=2):
                is_zebra = (row_idx % 2 == 0)
                _apply_data_style(ws_pdf.cell(row=row_idx, column=1), chunk.get("chunk_index", row_idx - 2), "center", is_zebra)
                _apply_data_style(ws_pdf.cell(row=row_idx, column=2), chunk.get("document_id", "-"), "center", is_zebra)
                _apply_data_style(ws_pdf.cell(row=row_idx, column=3), chunk.get("page_start", 1), "center", is_zebra)
                _apply_data_style(ws_pdf.cell(row=row_idx, column=4), chunk.get("page_end", 1), "center", is_zebra)

                # Truncate very long chunks for Excel cell limits (max 32767 chars)
                content = chunk.get("content", "")
                if len(content) > 32000:
                    content = content[:32000] + "... [TRUNCATED]"
                _apply_data_style(ws_pdf.cell(row=row_idx, column=5), content, "left", is_zebra)

            _auto_fit_columns(ws_pdf, min_width=12)
            ws_pdf.column_dimensions["E"].width = 80  # Wide column for text content

            logger.info("Added 'PDF Extracted Content' sheet with %d chunks to Excel workbook", len(pdf_chunks))

        # Output routing
        if output_path is not None:
            wb.save(output_path)
            logger.info("Saved company Excel workbook to file: %s", output_path)
            return output_path
        else:
            buffer = io.BytesIO()
            wb.save(buffer)
            buffer.seek(0)
            logger.info("Generated Excel workbook in-memory buffer (%d bytes)", len(buffer.getvalue()))
            return buffer

    except Exception as exc:
        logger.exception("Exception occurred during Excel generation for '%s': %s", company_data.get("name"), exc)
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
