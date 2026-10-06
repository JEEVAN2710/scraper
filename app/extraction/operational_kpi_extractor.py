"""Operational KPI Extractor for flexible workspace, coworking, and sector-specific operational disclosures.

Pure Python / PyMuPDF implementation (No LLM required):
1. Investor Presentation Parsing: High-fidelity regex and visual card structure extraction across quarterly PPT slides.
2. PyMuPDF Native Table Extraction: Directly parses structured tables from financial and operational slides.
3. Deterministic Regex Parsing: Extracts management opening remarks and disclosures from Concall Transcripts.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

from app.database.connection import DatabaseManager, get_db_manager
from app.database.repositories import OperationalMetricRepository

logger = logging.getLogger(__name__)


class OperationalKPIExtractor:
    """Extracts granular operational metrics (seats, centers, occupancy %, client tenure,
    segment revenues, client concentration) from Earnings Call Transcripts and Investor Presentations without an LLM.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or get_db_manager()
        self.op_repo = OperationalMetricRepository(self.db)

    def extract_from_pdf(
        self,
        pdf_path: Path,
        company_id: int,
        period_override: Optional[str] = None,
        document_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Extract operational metrics from a concall transcript or presentation PDF."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            logger.warning("PDF path does not exist: %s", pdf_path)
            return []

        try:
            doc = pymupdf.open(str(pdf_path))
            pages_text: List[str] = []
            for i in range(min(45, len(doc))):
                txt = doc[i].get_text() or ""
                pages_text.append(txt)

            full_text = " \n ".join(pages_text)
            period = self.detect_period_from_text(full_text, pdf_path.name)
            if not period and period_override:
                period = self.detect_period_from_text(full_text, period_override) or period_override
            if not period:
                logger.warning("Could not determine period for %s", pdf_path.name)
                return []

            metrics: List[Dict[str, Any]] = []
            seen_names: set = set()

            def add_metric(cat: str, name: str, val_str: str, num_val: Optional[float], unit: str):
                if name not in seen_names and num_val is not None:
                    seen_names.add(name)
                    metrics.append({
                        "period": period,
                        "metric_category": cat,
                        "metric_name": name,
                        "metric_value": str(val_str),
                        "numeric_value": float(num_val),
                        "unit": unit,
                        "document_id": document_id,
                    })

            # Check if this document is an Investor Presentation (PPT)
            is_ppt = (
                "PPT" in pdf_path.name.upper()
                or "PRESENTATION" in pdf_path.name.upper()
                or "SUPPLY HIGHLIGHTS" in full_text.upper()
                or "DEMAND METRICS" in full_text.upper()
                or "INVESTOR PRESENTATION" in full_text.upper()
            )

            # 1. High-fidelity Investor Presentation extraction
            if is_ppt:
                ppt_metrics = self._extract_from_presentation(doc, period, company_id, document_id)
                for pm in ppt_metrics:
                    add_metric(
                        pm["metric_category"],
                        pm["metric_name"],
                        pm["metric_value"],
                        pm["numeric_value"],
                        pm["unit"],
                    )

            # 2. PyMuPDF native table extraction
            tbl_metrics = self.extract_from_tables(doc, period, document_id)
            for tm in tbl_metrics:
                add_metric(
                    tm["metric_category"],
                    tm["metric_name"],
                    tm["metric_value"],
                    tm["numeric_value"],
                    tm["unit"],
                )

            # 3. Concall Transcripts / narrative text parsing
            txt_metrics = self.extract_metrics_from_text(full_text, period, company_id, document_id)
            for tm in txt_metrics:
                add_metric(
                    tm["metric_category"],
                    tm["metric_name"],
                    tm["metric_value"],
                    tm["numeric_value"],
                    tm["unit"],
                )

            if metrics:
                try:
                    self.op_repo.create_batch(company_id, metrics)
                    logger.info(
                        "Extracted and saved %d operational metrics for company %s in period %s",
                        len(metrics),
                        company_id,
                        period,
                    )
                except Exception as db_err:
                    logger.warning("Database batch save error: %s", db_err)

            return metrics
        except Exception as exc:
            logger.exception("Error extracting operational KPIs from %s: %s", pdf_path.name, exc)
            return []

    def _extract_from_presentation(
        self,
        doc: pymupdf.Document,
        period: str,
        company_id: int,
        document_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Specialized extractor for quarterly investor presentation slides."""
        results: List[Dict[str, Any]] = []
        found: Dict[str, Tuple[str, float, str]] = {}  # name -> (val_str, num_val, unit, category)
        categories: Dict[str, str] = {}

        def record(cat: str, name: str, val_str: str, num_val: float, unit: str):
            if name not in found:
                found[name] = (val_str, num_val, unit)
                categories[name] = cat

        for p_no in range(len(doc)):
            page = doc[p_no]
            t = page.get_text()

            # --- 1. Cities ---
            m_cit = re.search(r"(\d{1,2})\s+Cities", t)
            if not m_cit:
                m_cit = re.search(r"(?:Cities\s*\n\s*(\d{1,2})|(\d{1,2})\s*\n\s*Cities)", t, re.I)
            if m_cit:
                c_val = int(m_cit.group(1) or m_cit.group(2))
                if 10 <= c_val <= 35:
                    record("Capacity & Footprint", "Cities", str(c_val), float(c_val), "Cities")

            # --- 2. Signed Supply Centers, Seats, Area ---
            m_sc = re.search(r"(\d{2,4})\s*centres[,\s\n]+incl[.\s\n]+signed\s*loi", t, re.I)
            if not m_sc:
                m_sc = re.search(r"(?:Total\s*\+\s*Signed\s*LOI|Total\s*\+\s*Committed\s*Pipeline)[^\n]*?\n.*?(\d{2,4})", t, re.S)
            if m_sc:
                sc_int = int(m_sc.group(1))
                if sc_int > 100:
                    record("Capacity & Footprint", "Signed Supply Centers", str(sc_int), float(sc_int), "Centers")

            m_ss = re.search(r"([0-9,]{5,8})\s*seats[,\s\n]+incl[.\s\n]+signed\s*loi", t, re.I)
            if not m_ss:
                m_ss = re.search(r"([0-9,]{6,8})\s*Seats\s*\n\s*incl\.\s*signed\s*LOI", t, re.I)
            if not m_ss:
                m_ss = re.search(r"(?:Total\s*\+\s*Signed\s*LOI|Total\s*\+\s*Committed\s*Pipeline)[^\n]*?\n.*?\n.*?([0-9,]{6,8})", t, re.S)
            if m_ss:
                clean_s = m_ss.group(1).replace(",", "")
                if clean_s.isdigit() and int(clean_s) > 50000:
                    ss_int = int(clean_s)
                    record("Capacity & Footprint", "Signed Supply Seats", f"{ss_int:,}", float(ss_int), "Seats")

            m_sa = re.search(r"([0-9.]+)\s*mn[.\s]+sq[.\s]+ft[,\s\n]+incl[.\s\n]+signed\s*loi", t, re.I)
            if m_sa:
                sa_float = float(m_sa.group(1))
                record("Capacity & Footprint", "Signed Supply Area (incl. LOI)", f"{sa_float:.1f}", sa_float, "Mn Sq. Ft.")

            # --- 3. Total Centers & Total Seats & Operational Seats ---
            m_tc = re.search(r"total\s+supply\s+of\s+(\d+)\s+centers", t, re.I)
            if not m_tc:
                m_tc = re.search(r"(\d+)\s*\n\s*Centres", t, re.I)
            if m_tc:
                tc_int = int(m_tc.group(1))
                if 100 <= tc_int <= 400:
                    record("Capacity & Footprint", "Total Centers (Op+Fitout)", str(tc_int), float(tc_int), "Centers")

            # Seat walk-through extraction (e.g. Supply Highlights / Walkthrough slide)
            lines_page = [l.strip() for l in t.split("\n") if l.strip()]
            if "Operational" in lines_page:
                op_idx = lines_page.index("Operational")
                pre_digits = [
                    int(l.replace(",", ""))
                    for l in lines_page[:op_idx]
                    if l.replace(",", "").isdigit() and int(l.replace(",", "")) > 30000
                ]
                if len(pre_digits) == 2:
                    # [prior_operational, current_operational]
                    ops_num = pre_digits[1]
                    record("Capacity & Footprint", "Operational Seats", f"{ops_num:,}", float(ops_num), "Seats")
                elif len(pre_digits) >= 4:
                    # [mar24_operational, cur_operational, cur_total, cur_signed]
                    ops_num = pre_digits[1]
                    tot_num = pre_digits[2]
                    sign_num = pre_digits[3]
                    record("Capacity & Footprint", "Operational Seats", f"{ops_num:,}", float(ops_num), "Seats")
                    record("Capacity & Footprint", "Total Seats (Op+Fitout)", f"{tot_num:,}", float(tot_num), "Seats")
                    record("Capacity & Footprint", "Signed Supply Seats", f"{sign_num:,}", float(sign_num), "Seats")

            m_ts = re.search(r"(?:total\s+seats|supply\s+of)[^\n]*?([0-9,]{6,8})", t, re.I)
            if not m_ts:
                m_ts = re.search(r"([0-9,]{6,8})\s*(?:\n\s*Growth in\s+Operational\s+Seats|\n\s*Total\s+Seats)", t, re.I)
            if m_ts:
                clean_ts = m_ts.group(1).replace(",", "")
                if clean_ts.isdigit() and int(clean_ts) > 50000:
                    ts_int = int(clean_ts)
                    record("Capacity & Footprint", "Total Seats (Op+Fitout)", f"{ts_int:,}", float(ts_int), "Seats")

            m_ops = re.search(r"(?:Crossed|surpassed|have)\s*([0-9,]{6,7})\s*operational\s*seats", t, re.I)
            if m_ops:
                clean_ops = m_ops.group(1).replace(",", "")
                if clean_ops.isdigit() and int(clean_ops) > 50000:
                    ops_int = int(clean_ops)
                    record("Capacity & Footprint", "Operational Seats", f"{ops_int:,}", float(ops_int), "Seats")

            # --- 4. MA Portfolio % ---
            m_ma = re.search(r"(\d+)%\s+(?:total\s+seats|seats)[^\n]*?under\s+MA\s+model", t, re.I)
            if not m_ma:
                m_ma = re.search(r"Managed\s+Aggregation\s+Portfolio[^\n]*?\n.*?(\d+)%", t, re.S)
            if not m_ma:
                m_ma = re.search(r"(\d+)%\s*seats\s*in\s*MA\s*model", t, re.I)
            if m_ma:
                ma_val = float(m_ma.group(1))
                record("Capacity & Footprint", "MA Portfolio % (Seats)", f"{ma_val:.1f}%", ma_val, "%")

            # --- 5. Occupancy ---
            m_occ_slide = re.search(r"Blended\s+Occupancy\s*/>12m\s+Vintage\s+Centres[^\n]*?\n.*?(\d+)%\s*/\s*(\d+)%", t, re.S)
            if m_occ_slide:
                b_occ = float(m_occ_slide.group(1))
                v_occ = float(m_occ_slide.group(2))
                record("Occupancy & Tenure", "Blended Occupancy %", f"{b_occ:.1f}%", b_occ, "%")
                record("Occupancy & Tenure", ">12m Vintage Occ. %", f"{v_occ:.1f}%", v_occ, "%")
            else:
                m_blended = re.search(r"(?:exit\s+month\s+occupancy|blended\s+occupancy)[^\n]*?(?:at|of|to)?\s*(\d+)%", t, re.I)
                if m_blended:
                    b_occ = float(m_blended.group(1))
                    record("Occupancy & Tenure", "Blended Occupancy %", f"{b_occ:.1f}%", b_occ, "%")
                m_vint = re.search(r"(\d+)%\s*occupancy\s*at\s*centers\s*with\s*>\s*12", t, re.I)
                if not m_vint:
                    m_vint = re.search(r">\s*12\s*months\s*vintage[^\n]*?(\d+)%", t, re.I)
                if m_vint:
                    v_occ = float(m_vint.group(1))
                    record("Occupancy & Tenure", ">12m Vintage Occ. %", f"{v_occ:.1f}%", v_occ, "%")

            # --- 6. Demand, Tenure & Active Clients ---
            m_mc = re.search(r"Multi\s+Center\s+Clients\s*\n\s*(\d+)%", t, re.I)
            if m_mc:
                mc_val = float(m_mc.group(1))
                record("Occupancy & Tenure", "% Multi-Center Clients", f"{mc_val:.1f}%", mc_val, "%")

            m_cli = re.search(r"Active\s+Clients\s*\n\s*(\d+)K\+?", t, re.I)
            if not m_cli:
                m_cli = re.search(r"([0-9,]{3,6})\s*unique\s*clients", t, re.I)
            if m_cli:
                if "K" in m_cli.group(0).upper():
                    cli_cnt = int(m_cli.group(1)) * 1000
                else:
                    cli_cnt = int(m_cli.group(1).replace(",", ""))
                record("Occupancy & Tenure", "Active Clients", f"{cli_cnt:,}", float(cli_cnt), "Clients")

            m_ten = re.search(r"Weighted\s+Average\s+Total\s*\n\s*Tenure\s*\(months\)\s*\n\s*(\d+)", t, re.I)
            if not m_ten:
                m_ten = re.search(r"Avg\.?\s*Tenure\s*of\s*(\d+)\s*months", t, re.I)
            if m_ten:
                ten_val = float(m_ten.group(1))
                record("Occupancy & Tenure", "W. Avg Total Tenure (Mos)", f"{int(ten_val)} Mos", ten_val, "Months")

            # --- 7. Seat Cohorts, Tenure Buckets, Industry Mix ---
            if "DIVERSE DEMAND STRATEGY" in t:
                # Seat cohorts
                m_sc_coh = re.search(r"100\+\s*Seats\s*\n\s*51-100\s*Seats\s*\n\s*1-50\s*Seats\s*\n\s*(\d+)%\s*\n\s*(\d+)%\s*\n\s*(\d+)%", t)
                if m_sc_coh:
                    s100 = float(m_sc_coh.group(1))
                    s51 = float(m_sc_coh.group(2))
                    s1 = float(m_sc_coh.group(3))
                    record("Client Concentration & Size", "100+ Seats (Enterprise)", f"{s100:.1f}%", s100, "%")
                    record("Client Concentration & Size", "51-100 Seats", f"{s51:.1f}%", s51, "%")
                    record("Client Concentration & Size", "1-50 Seats", f"{s1:.1f}%", s1, "%")

                # Tenure buckets
                m_tb = re.search(r"(\d+)%\s*\n\s*(\d+)%\s*\n\s*(\d+)%\s*\n\s*(\d+)%\s*\n[^\n]*\n\s*>=24\s*months\s*\n\s*12-23\s*months\s*\n\s*6-11\s*months\s*\n\s*<=5\s*months", t)
                if m_tb:
                    t24 = float(m_tb.group(1))
                    t12 = float(m_tb.group(2))
                    t_lt = float(m_tb.group(3)) + float(m_tb.group(4))
                    record("Client Tenure Buckets", ">= 24 Months", f"{t24:.1f}%", t24, "%")
                    record("Client Tenure Buckets", "12-23 Months", f"{t12:.1f}%", t12, "%")
                    record("Client Tenure Buckets", "< 12 Months", f"{t_lt:.1f}%", t_lt, "%")

                # Industry Mix (IT, Professional Services, BFSI)
                m_sec = re.search(r"(\d+)%\s*\n\s*(\d+)%\s*\n\s*(\d+)%\s*\n\s*(\d+)%\s*\n\s*(\d+)%\s*\n\s*(\d+)%\s*\n\s*(\d+)%\s*\n\s*Across\s*various\s*\n\s*sectors\s*\n\s*IT\s*\n\s*Professional\s*Services[^\n]*\n[^\n]*\n[^\n]*\n\s*Financial\s*Services", t)
                if m_sec:
                    it_val = float(m_sec.group(1))
                    prof_val = float(m_sec.group(2))
                    bfsi_val = float(m_sec.group(5))
                    record("Industry Sector Concentration", "IT/ITES", f"{it_val:.1f}%", it_val, "%")
                    record("Industry Sector Concentration", "Prof. Services/Consulting", f"{prof_val:.1f}%", prof_val, "%")
                    record("Industry Sector Concentration", "BFSI", f"{bfsi_val:.1f}%", bfsi_val, "%")

            # --- 8. Segmental Revenue ---
            if "SEGMENTAL" in t.upper() and "REVENUE" in t.upper():
                q_clean = re.sub(r"[^A-Za-z0-9]", "", period).upper()
                lines = [line.strip() for line in t.split("\n") if line.strip()]
                cw_val = None
                fit_val = None
                oth_val = None

                for idx, line in enumerate(lines):
                    if line.upper() == q_clean:
                        k = idx - 1
                        while k >= 0 and not lines[k].isdigit():
                            k -= 1
                        digits = []
                        while k >= 0 and lines[k].isdigit():
                            digits.insert(0, float(lines[k]))
                            k -= 1
                        val = None
                        if len(digits) == 2:
                            val = digits[1]
                        elif len(digits) >= 4:
                            val = digits[1]
                        elif len(digits) == 1:
                            val = digits[0]

                        if val is not None:
                            if cw_val is None:
                                cw_val = val
                            elif fit_val is None:
                                fit_val = val
                            elif oth_val is None:
                                oth_val = val

                if cw_val is not None:
                    record("Segment Revenue Breakdown", "Co-working & Allied Revenue (₹ Cr)", f"₹{cw_val:.0f} Cr", cw_val, "₹ Cr")
                if fit_val is not None:
                    record("Segment Revenue Breakdown", "Construction & Fit-out Revenue (₹ Cr)", f"₹{fit_val:.0f} Cr", fit_val, "₹ Cr")
                if oth_val is not None:
                    record("Segment Revenue Breakdown", "Others Revenue (₹ Cr)", f"₹{oth_val:.0f} Cr", oth_val, "₹ Cr")

        for name, (val_str, num_val, unit) in found.items():
            results.append({
                "period": period,
                "metric_category": categories.get(name, "Operational KPIs"),
                "metric_name": name,
                "metric_value": val_str,
                "numeric_value": num_val,
                "unit": unit,
                "document_id": document_id,
            })

        return results

    def extract_from_tables(
        self,
        doc: pymupdf.Document,
        period: str,
        document_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Extract tabular operational KPIs using PyMuPDF native table detection."""
        metrics: List[Dict[str, Any]] = []
        seen_metrics: set = set()

        for page_num in range(min(40, len(doc))):
            page = doc[page_num]
            text = page.get_text().lower()

            if not any(k in text for k in ["signed supply", "occupancy", "centers", "seats", "tenure", "active clients", "fitout"]):
                continue

            try:
                tables = list(page.find_tables())
                for table in tables:
                    matrix = table.extract()
                    if not matrix or len(matrix) < 2:
                        continue

                    header = [str(c or "").strip() for c in matrix[0]]
                    target_col_idx = None
                    for c_idx, h in enumerate(header[1:], start=1):
                        clean_h = re.sub(r"[^A-Za-z0-9]", "", h).upper()
                        clean_p = re.sub(r"[^A-Za-z0-9]", "", period).upper()
                        if clean_h and (clean_h in clean_p or clean_p in clean_h):
                            target_col_idx = c_idx
                            break

                    if target_col_idx is None:
                        target_col_idx = len(header) - 1 if len(header) > 1 else 1

                    for row in matrix[1:]:
                        if not row or len(row) <= target_col_idx:
                            continue
                        label = str(row[0] or "").strip()
                        raw_val = str(row[target_col_idx] or "").strip().replace(",", "")
                        if not label or not raw_val or raw_val in ("-", "—", "N/A"):
                            continue

                        parsed = self._map_table_label(label, raw_val, period, document_id)
                        if parsed and parsed["metric_name"] not in seen_metrics:
                            seen_metrics.add(parsed["metric_name"])
                            metrics.append(parsed)
            except Exception as t_err:
                logger.debug("Table detection on page %d encountered error: %s", page_num + 1, t_err)

        return metrics

    def _map_table_label(
        self,
        label: str,
        val_str: str,
        period: str,
        document_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Map extracted table row label to standardized metric definition."""
        clean_lbl = label.lower()
        val_clean = re.sub(r"[^0-9.]", "", val_str)
        if not val_clean:
            return None
        try:
            num_val = float(val_clean)
        except ValueError:
            return None

        # 1. Capacity & Footprint
        if "signed supply centers" in clean_lbl or ("signed" in clean_lbl and "centers" in clean_lbl):
            return {"period": period, "metric_category": "Capacity & Footprint", "metric_name": "Signed Supply Centers", "metric_value": str(int(num_val)), "numeric_value": num_val, "unit": "Centers", "document_id": document_id}
        if "signed supply seats" in clean_lbl or ("signed" in clean_lbl and "seats" in clean_lbl):
            return {"period": period, "metric_category": "Capacity & Footprint", "metric_name": "Signed Supply Seats", "metric_value": f"{int(num_val):,}", "numeric_value": num_val, "unit": "Seats", "document_id": document_id}
        if "signed supply area" in clean_lbl or ("signed" in clean_lbl and "area" in clean_lbl):
            return {"period": period, "metric_category": "Capacity & Footprint", "metric_name": "Signed Supply Area (incl. LOI)", "metric_value": f"{num_val:.1f}", "numeric_value": num_val, "unit": "Mn Sq. Ft.", "document_id": document_id}
        if "total centers" in clean_lbl or "centers (op+fitout)" in clean_lbl:
            return {"period": period, "metric_category": "Capacity & Footprint", "metric_name": "Total Centers (Op+Fitout)", "metric_value": str(int(num_val)), "numeric_value": num_val, "unit": "Centers", "document_id": document_id}
        if "total seats" in clean_lbl or "seats (op+fitout)" in clean_lbl:
            return {"period": period, "metric_category": "Capacity & Footprint", "metric_name": "Total Seats (Op+Fitout)", "metric_value": f"{int(num_val):,}", "numeric_value": num_val, "unit": "Seats", "document_id": document_id}
        if "operational seats" in clean_lbl:
            return {"period": period, "metric_category": "Capacity & Footprint", "metric_name": "Operational Seats", "metric_value": f"{int(num_val):,}", "numeric_value": num_val, "unit": "Seats", "document_id": document_id}
        if "cities" in clean_lbl:
            return {"period": period, "metric_category": "Capacity & Footprint", "metric_name": "Cities", "metric_value": str(int(num_val)), "numeric_value": num_val, "unit": "Cities", "document_id": document_id}
        if "ma portfolio" in clean_lbl:
            return {"period": period, "metric_category": "Capacity & Footprint", "metric_name": "MA Portfolio % (Seats)", "metric_value": f"{num_val:.1f}%", "numeric_value": num_val, "unit": "%", "document_id": document_id}

        # 2. Occupancy & Tenure
        if "blended occupancy" in clean_lbl or ("occupancy" in clean_lbl and "vintage" not in clean_lbl):
            return {"period": period, "metric_category": "Occupancy & Tenure", "metric_name": "Blended Occupancy %", "metric_value": f"{num_val:.1f}%", "numeric_value": num_val, "unit": "%", "document_id": document_id}
        if "vintage" in clean_lbl or "12m" in clean_lbl or ">12m" in clean_lbl:
            return {"period": period, "metric_category": "Occupancy & Tenure", "metric_name": ">12m Vintage Occ. %", "metric_value": f"{num_val:.1f}%", "numeric_value": num_val, "unit": "%", "document_id": document_id}
        if "tenure" in clean_lbl:
            return {"period": period, "metric_category": "Occupancy & Tenure", "metric_name": "W. Avg Total Tenure (Mos)", "metric_value": f"{int(num_val)} Mos", "numeric_value": num_val, "unit": "Months", "document_id": document_id}
        if "active clients" in clean_lbl:
            return {"period": period, "metric_category": "Occupancy & Tenure", "metric_name": "Active Clients", "metric_value": f"{int(num_val):,}", "numeric_value": num_val, "unit": "Clients", "document_id": document_id}
        if "multi-center" in clean_lbl or "multi center" in clean_lbl:
            return {"period": period, "metric_category": "Occupancy & Tenure", "metric_name": "% Multi-Center Clients", "metric_value": f"{num_val:.1f}%", "numeric_value": num_val, "unit": "%", "document_id": document_id}

        # 3. Client Concentration
        if "100+" in clean_lbl or "enterprise" in clean_lbl:
            return {"period": period, "metric_category": "Client Concentration & Size", "metric_name": "100+ Seats (Enterprise)", "metric_value": f"{num_val:.1f}%", "numeric_value": num_val, "unit": "%", "document_id": document_id}
        if "51-100" in clean_lbl:
            return {"period": period, "metric_category": "Client Concentration & Size", "metric_name": "51-100 Seats", "metric_value": f"{num_val:.1f}%", "numeric_value": num_val, "unit": "%", "document_id": document_id}
        if "1-50" in clean_lbl:
            return {"period": period, "metric_category": "Client Concentration & Size", "metric_name": "1-50 Seats", "metric_value": f"{num_val:.1f}%", "numeric_value": num_val, "unit": "%", "document_id": document_id}

        # 4. Segment Revenue
        if "co-working" in clean_lbl or "coworking" in clean_lbl:
            return {"period": period, "metric_category": "Segment Revenue Breakdown", "metric_name": "Co-working & Allied Revenue (₹ Cr)", "metric_value": f"₹{num_val:.0f} Cr", "numeric_value": num_val, "unit": "₹ Cr", "document_id": document_id}
        if "fit-out" in clean_lbl or "fitout" in clean_lbl or "construction" in clean_lbl:
            return {"period": period, "metric_category": "Segment Revenue Breakdown", "metric_name": "Construction & Fit-out Revenue (₹ Cr)", "metric_value": f"₹{num_val:.0f} Cr", "numeric_value": num_val, "unit": "₹ Cr", "document_id": document_id}
        if "others" in clean_lbl and "revenue" in clean_lbl:
            return {"period": period, "metric_category": "Segment Revenue Breakdown", "metric_name": "Others Revenue (₹ Cr)", "metric_value": f"₹{num_val:.0f} Cr", "numeric_value": num_val, "unit": "₹ Cr", "document_id": document_id}

        return None

    def detect_period_from_text(self, text: str, filename: str) -> Optional[str]:
        """Detect fiscal quarter from filename or transcript header text."""
        # 1. Direct Qx FYxx in filename
        m_fn = re.search(r"Q([1-4])[-_\s]?FY[-_\s]?(\d{2,4})", filename, re.IGNORECASE)
        if m_fn:
            q = m_fn.group(1)
            yr = m_fn.group(2)
            if len(yr) == 4:
                yr = yr[-2:]
            return f"Q{q} FY{yr}"

        # 2. Direct Qx FYxx in document header text
        header_sample = text[:4000]
        m_txt = re.search(r"(?:Q([1-4])\s*(?:of\s*|&\s*\d+M\s*)?FY\s*['’]?(\d{2,4})|FY\s*['’]?(\d{2,4})\s*Q([1-4]))", header_sample, re.IGNORECASE)
        if m_txt:
            if m_txt.group(1):
                q = m_txt.group(1)
                yr = m_txt.group(2)[-2:]
            else:
                yr = m_txt.group(3)[-2:]
                q = m_txt.group(4)
            return f"Q{q} FY{yr}"

        # 3. Quarter ending month-year in header text
        m_ended = re.search(r"quarter\s+ended\s+([A-Za-z]+)\s+\d{1,2},?\s+(\d{4})", header_sample, re.IGNORECASE)
        if m_ended:
            mon = m_ended.group(1)[:3].title()
            yr = int(m_ended.group(2))
            if mon in ["Apr", "May", "Jun"]:
                return f"Q1 FY{(yr + 1) % 100:02d}"
            elif mon in ["Jul", "Aug", "Sep"]:
                return f"Q2 FY{(yr + 1) % 100:02d}"
            elif mon in ["Oct", "Nov", "Dec"]:
                return f"Q3 FY{(yr + 1) % 100:02d}"
            elif mon in ["Jan", "Feb", "Mar"]:
                return f"Q4 FY{yr % 100:02d}"

        # 4. Month-year in filename (concall timing mapping)
        month_yr_fn = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[_-](\d{4})", filename, re.IGNORECASE)
        if month_yr_fn:
            mon = month_yr_fn.group(1).title()
            yr = int(month_yr_fn.group(2))
            if mon in ["Oct", "Nov", "Dec"]:
                return f"Q2 FY{(yr + 1) % 100:02d}"
            elif mon in ["Jan", "Feb", "Mar"]:
                return f"Q3 FY{yr % 100:02d}"
            elif mon in ["Apr", "May", "Jun"]:
                return f"Q4 FY{yr % 100:02d}"
            elif mon in ["Jul", "Aug", "Sep"]:
                return f"Q1 FY{(yr + 1) % 100:02d}"

        return None

    def extract_metrics_from_text(
        self,
        text: str,
        period: str,
        company_id: int,
        document_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Extract structured operational metrics from raw text using targeted regex patterns."""
        metrics: List[Dict[str, Any]] = []

        def add_metric(cat: str, name: str, val_str: str, num_val: Optional[float], unit: str):
            metrics.append({
                "period": period,
                "metric_category": cat,
                "metric_name": name,
                "metric_value": str(val_str),
                "numeric_value": num_val,
                "unit": unit,
                "document_id": document_id,
            })

        # --- Capacity & Footprint ---
        # Signed Supply Seats & Centers
        m_cap = re.search(r"(?:total\s+capacity\s+now\s+exceeds|total\s+capacity\s+now\s+stands\s+at\s+over|capacity\s+now\s+stands\s+at|capacity\s+stands\s+at|capacity\s+of)\s*([0-9,]+)\s*seats\s+across\s*([0-9,]+)\s*centers", text, re.I)
        if m_cap:
            seats = int(m_cap.group(1).replace(",", ""))
            centers = int(m_cap.group(2).replace(",", ""))
            add_metric("Capacity & Footprint", "Signed Supply Seats", f"{seats:,}", float(seats), "Seats")
            add_metric("Capacity & Footprint", "Signed Supply Centers", str(centers), float(centers), "Centers")
        else:
            m_signed_s = re.search(r"([0-9,]{4,7})\s*(?:signed\s+supply\s+seats|signed\s+seats|seats\s+under\s+LOI)", text, re.IGNORECASE)
            if m_signed_s:
                clean_s = m_signed_s.group(1).replace(",", "")
                if clean_s.isdigit():
                    s_int = int(clean_s)
                    add_metric("Capacity & Footprint", "Signed Supply Seats", f"{s_int:,}", float(s_int), "Seats")

            m_signed_c = re.search(r"(?:signed\s+supply\s+centers|signed\s+centers)\s*(?:stood\s+at|reached|of)?\s*([0-9]{2,4})", text, re.I)
            if m_signed_c:
                c_int = int(m_signed_c.group(1))
                add_metric("Capacity & Footprint", "Signed Supply Centers", str(c_int), float(c_int), "Centers")

        # Signed Supply Area (Mn Sq. Ft.)
        m_area = re.search(r"(?:covering|spanning)[^.\n]*?([0-9]+(?:\.[0-9]+)?)\s*(?:million\s*square\s*feet|mn\s*sq\s*ft|msf)", text, re.I)
        if m_area:
            a_val = float(m_area.group(1))
            add_metric("Capacity & Footprint", "Signed Supply Area (incl. LOI)", f"{a_val:.1f}", a_val, "Mn Sq. Ft.")

        # Total Centers & Total Seats (Operational + Under fit-out)
        m_port = re.search(r"(?:total\s+portfolio|portfolio)\s*(?:now\s+)?stands\s+at\s*([0-9,]+)\s*centers[^.\n]*?([0-9,]+)\s*seats", text, re.I)
        if m_port:
            c_val = int(m_port.group(1).replace(",", ""))
            s_val = int(m_port.group(2).replace(",", ""))
            add_metric("Capacity & Footprint", "Total Centers (Op+Fitout)", str(c_val), float(c_val), "Centers")
            add_metric("Capacity & Footprint", "Total Seats (Op+Fitout)", f"{s_val:,}", float(s_val), "Seats")
        else:
            m_cntr = re.search(r"(?:total\s+network\s+to|network\s+of|stands?\s+at|reach(?:ed)?|now\s+have|closed\s+with|operated)\s*([0-9]{2,4})\s*(?:Gold\s+and\s+Elite\s+)?centers", text, re.IGNORECASE)
            if not m_cntr:
                m_cntr = re.search(r"(?:with|reach(?:ed)?)\s*([0-9]{2,4})\s*centers", text, re.IGNORECASE)
            if m_cntr:
                c_val = int(m_cntr.group(1))
                add_metric("Capacity & Footprint", "Total Centers (Op+Fitout)", str(c_val), float(c_val), "Centers")

            m_tot_seats = re.search(r"(?:capacity\s+including\s+centers\s+under\s+fit-?out\s+reached|total\s+capacity|total\s+seats|supply\s+of|nearly|over)\s*([0-9,]{5,7})\s*seats", text, re.IGNORECASE)
            if m_tot_seats:
                clean_s = m_tot_seats.group(1).replace(",", "")
                if clean_s.isdigit() and int(clean_s) >= 10000:
                    s_int = int(clean_s)
                    add_metric("Capacity & Footprint", "Total Seats (Op+Fitout)", f"{s_int:,}", float(s_int), "Seats")

        # Operational Seats
        m_op_seats = re.search(r"(?:surpassed|reached|stands\s+at|at)\s*([0-9,]{4,7})\s*operational\s*seats", text, re.IGNORECASE)
        if not m_op_seats:
            m_op_seats = re.search(r"([0-9,]{4,7})\s*(?:operational\s+seats|seats\s+operational)", text, re.IGNORECASE)
        if m_op_seats:
            clean_s = m_op_seats.group(1).replace(",", "")
            if clean_s.isdigit():
                s_int = int(clean_s)
                add_metric("Capacity & Footprint", "Operational Seats", f"{s_int:,}", float(s_int), "Seats")

        # Cities Count
        m_t1_t2 = re.search(r"([0-9]{1,2})\s*(?:major\s*)?Tier\s*1[^\n.]*?(?:and|&)\s*([0-9]{1,2})\s*Tier\s*2\s*cities", text, re.IGNORECASE)
        if m_t1_t2:
            cit_val = int(m_t1_t2.group(1)) + int(m_t1_t2.group(2))
            add_metric("Capacity & Footprint", "Cities", str(cit_val), float(cit_val), "Cities")
        else:
            m_cities = re.search(r"(?:presence\s+across|footprint\s+across|operating\s+in|presence\s+in)\s*([0-9]{1,3})\s*cities", text, re.IGNORECASE)
            if m_cities:
                cit_val = int(m_cities.group(1))
                if cit_val >= 10:
                    add_metric("Capacity & Footprint", "Cities", str(cit_val), float(cit_val), "Cities")

        # MA Portfolio %
        m_ma = re.search(r"([0-9]{2}(?:\.[0-9]+)?)\s*%\s*(?:of\s*(?:our\s*)?(?:seats|portfolio)\s*(?:is|under)\s*(?:managed\s+aggregation|asset\s*light|MA))", text, re.I)
        if m_ma:
            ma_val = float(m_ma.group(1))
            add_metric("Capacity & Footprint", "MA Portfolio % (Seats)", f"{ma_val:.1f}%", ma_val, "%")

        # --- Occupancy & Tenure ---
        # Blended Occupancy %
        m_occ = re.search(r"(?:blended\s*(?:exit\s*month\s*)?occupancy)[^.\n]{0,50}?(?:at|remained\s+consistent\s+at|is|reached|stood\s+at)\s*([0-9]{2}(?:\.[0-9]+)?)\s*%", text, re.IGNORECASE)
        if not m_occ:
            m_occ = re.search(r"(?:blended\s+occupancy|portfolio\s+occupancy|overall\s+(?:portfolio\s+)?occupancy|exit\s+month\s+occupancy|occupancy\s+stood\s+at)[^.\n]{0,40}?([0-9]{2}(?:\.[0-9]+)?)\s*%", text, re.IGNORECASE)
        if m_occ:
            occ_val = float(m_occ.group(1))
            add_metric("Occupancy & Tenure", "Blended Occupancy %", f"{occ_val:.1f}%", occ_val, "%")

        # >12m Vintage Occupancy %
        m_vint = re.search(r"(?:older\s+than\s+12\s+months|vintage|over\s+12\s+months|centers\s+operational\s+for\s+over\s+12\s+months)[^.\n]{0,80}?(?:stands\s+at|recorded\s+a\s+solid|at|of)?\s*([0-9]{2}(?:\.[0-9]+)?)\s*%", text, re.IGNORECASE)
        if not m_vint:
            m_vint = re.search(r"occupancy[^.\n]{0,80}?(?:12\s*months?|mature)[^.\n]{0,80}?(?:at|of|to)?\s*([0-9]{2}(?:\.[0-9]+)?)\s*%", text, re.IGNORECASE)
        if m_vint:
            v_val = float(m_vint.group(1))
            add_metric("Occupancy & Tenure", ">12m Vintage Occ. %", f"{v_val:.1f}%", v_val, "%")

        # Client Tenure (Months)
        m_tenure = re.search(r"(?:total\s+average\s+client\s+tenure|average\s+client\s+tenure|client\s+tenure)[^.\n]{0,40}?(?:is|stood\s+at)?\s*([0-9]{1,3})\s*months", text, re.IGNORECASE)
        if m_tenure:
            t_val = int(m_tenure.group(1))
            add_metric("Occupancy & Tenure", "W. Avg Total Tenure (Mos)", f"{t_val} Mos", float(t_val), "Months")

        # Active Clients
        m_clients = re.search(r"(?:more\s+than|over)\s*([0-9,]{3,6})\s*active\s*clients", text, re.I)
        if not m_clients:
            m_clients = re.search(r"([0-9,]{3,6})(?:\+|\s*-?\s*plus)?\s*(?:active\s+clients|client\s+companies|unique\s+clients)", text, re.IGNORECASE)
        if m_clients:
            c_clean = m_clients.group(1).replace(",", "")
            if c_clean.isdigit() and int(c_clean) >= 100:
                c_num = int(c_clean)
                add_metric("Occupancy & Tenure", "Active Clients", f"{c_num:,}", float(c_num), "Clients")

        # Multi-Center %
        m_mc = re.search(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*(?:of\s*(?:our\s*)?clients\s*operat(?:e|ing)\s*across\s*multiple\s*centers|of\s*clients\s*across\s*multiple\s*centers)", text, re.IGNORECASE)
        if m_mc:
            mc_val = float(m_mc.group(1))
            add_metric("Occupancy & Tenure", "% Multi-Center Clients", f"{mc_val:.1f}%", mc_val, "%")

        # --- Client Concentration & Seat Buckets ---
        m_ent = re.search(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*(?:of\s*occupied\s*seats\s*are\s*taken\s*by\s*large\s*corporates|from\s*large\s*corporates|from\s*100\s*(?:-|–|\+)?\s*plus\s*seats?|enterprise)", text, re.IGNORECASE)
        if not m_ent:
            m_ent = re.search(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*from\s*100-plus\s*seat", text, re.IGNORECASE)
        if m_ent:
            ent_val = float(m_ent.group(1))
            add_metric("Client Concentration & Size", "100+ Seats (Enterprise)", f"{ent_val:.1f}%", ent_val, "%")

        m_s51 = re.search(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*(?:from\s*)?51\s*[-–]\s*100\s*seats?", text, re.I)
        if m_s51:
            val = float(m_s51.group(1))
            add_metric("Client Concentration & Size", "51-100 Seats", f"{val:.1f}%", val, "%")

        m_s1 = re.search(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*(?:from\s*)?1\s*[-–]\s*50\s*seats?", text, re.I)
        if m_s1:
            val = float(m_s1.group(1))
            add_metric("Client Concentration & Size", "1-50 Seats", f"{val:.1f}%", val, "%")

        # --- Segment Revenue Breakdown ---
        m_cw_rev = re.search(r"co-?working\s*(?:and\s*allied\s*services)?\s*(?:segment|business)?[^.\n]*?(?:to|stood\s*at|revenue\s*at|delivered)[^.\n]*?INR\s*([0-9]{2,4})\s*crores?", text, re.IGNORECASE)
        if m_cw_rev:
            cw_val = float(m_cw_rev.group(1))
            add_metric("Segment Revenue Breakdown", "Co-working & Allied Revenue (₹ Cr)", f"₹{cw_val:.0f} Cr", cw_val, "₹ Cr")

        m_fit_rev = re.search(r"(?:construction\s*(?:and\s*)?fit-?out|fit-?out\s+projects|fit-?out\s+solutions|transform)[^.\n]*?(?:reaching\s+a\s+total\s+of|stood\s+at|at|delivered)?[^.\n]*?INR\s*([0-9]{2,4})\s*crores?", text, re.IGNORECASE)
        if m_fit_rev:
            fit_val = float(m_fit_rev.group(1))
            add_metric("Segment Revenue Breakdown", "Construction & Fit-out Revenue (₹ Cr)", f"₹{fit_val:.0f} Cr", fit_val, "₹ Cr")

        m_oth_rev = re.search(r"(?:others?\s+revenue|other\s+operating\s+revenue)[^.\n]*?INR\s*([0-9]{1,3})\s*crores?", text, re.I)
        if m_oth_rev:
            oth_val = float(m_oth_rev.group(1))
            add_metric("Segment Revenue Breakdown", "Others Revenue (₹ Cr)", f"₹{oth_val:.0f} Cr", oth_val, "₹ Cr")

        # --- Industry Diversification ---
        m_it = re.search(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*(?:from\s*)?IT\s*/?\s*ITES", text, re.I)
        if m_it:
            add_metric("Industry Sector Concentration", "IT/ITES", f"{float(m_it.group(1)):.1f}%", float(m_it.group(1)), "%")

        m_bfsi = re.search(r"([0-9]{1,2}(?:\.[0-9]+)?)\s*%\s*(?:from\s*)?BFSI", text, re.I)
        if m_bfsi:
            add_metric("Industry Sector Concentration", "BFSI", f"{float(m_bfsi.group(1)):.1f}%", float(m_bfsi.group(1)), "%")

        # --- Capital Markets & Financial Services Disclosures ---
        # MTF Book (Margin Trading Facility)
        m_mtf = re.search(r"(?:MTF\s+book\s+(?:of|stood\s+at|reached|around|at)|MTF\s+of)[^.\n]*?(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:cr|crore)", text, re.I)
        if not m_mtf:
            m_mtf = re.search(r"(?:MTF\s+book)[^.\n]*?([0-9,]+(?:\.[0-9]+)?)\s*(?:cr|crore)", text, re.I)
        if m_mtf:
            mtf_val = float(m_mtf.group(1).replace(",", ""))
            if 10.0 <= mtf_val <= 100000.0:
                add_metric("Operational & Business Disclosures", "MTF Book (₹ Cr)", f"₹{mtf_val:.0f} Cr", mtf_val, "₹ Cr")

        # ADTO (Average Daily Turnover)
        m_adto = re.search(r"(?:ADTO|average\s+daily\s+turnover)[^.\n]*?(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:cr|crore|lakh)", text, re.I)
        if m_adto:
            adto_val = float(m_adto.group(1).replace(",", ""))
            add_metric("Operational & Business Disclosures", "Average Daily Turnover (ADTO) (₹ Cr)", f"₹{adto_val:.0f} Cr", adto_val, "₹ Cr")

        # Demat Accounts / Broking Clients
        m_demat = re.search(r"([0-9,]+(?:\.[0-9]+)?)\s*(?:lakh|mn|million)?\s*(?:demat\s+accounts|active\s+clients|trading\s+clients|retail\s+accounts)", text, re.I)
        if m_demat and m_demat.group(1):
            raw_str = m_demat.group(1).replace(",", "").strip()
            if raw_str:
                try:
                    num_part = float(raw_str)
                    raw_dm = m_demat.group(0)
                    if "lakh" in raw_dm.lower():
                        num_part *= 100000
                    elif "mn" in raw_dm.lower() or "million" in raw_dm.lower():
                        num_part *= 1000000
                    if num_part >= 100:
                        add_metric("Operational & Business Disclosures", "Active Demat Accounts / Clients", f"{int(num_part):,}", float(num_part), "Clients")
                except ValueError:
                    pass

        # AUM (Assets Under Management)
        m_aum = re.search(r"(?:AUM|assets\s+under\s+management)[^.\n]*?(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:cr|crore)", text, re.I)
        if m_aum:
            aum_val = float(m_aum.group(1).replace(",", ""))
            add_metric("Operational & Business Disclosures", "AUM (₹ Cr)", f"₹{aum_val:.0f} Cr", aum_val, "₹ Cr")

        # Branches / Outlets Network
        m_br = re.search(r"(?:network\s+of|stands\s+at|reach(?:ed)?|has)\s*([0-9,]+)\s*(?:branches|franchisees|outlets|stores)", text, re.I)
        if m_br:
            br_val = int(m_br.group(1).replace(",", ""))
            if 5 <= br_val <= 50000:
                add_metric("Operational & Business Disclosures", "Branches / Outlets Network", f"{br_val:,}", float(br_val), "Units")

        # Headcount / Total Employees
        m_emp = re.search(r"(?:headcount\s+(?:of|stands\s+at)|team\s+of|workforce\s+of)\s*([0-9,]+)\s*(?:employees|professionals|members|people)?", text, re.I)
        if m_emp:
            emp_val = int(m_emp.group(1).replace(",", ""))
            if 50 <= emp_val <= 1000000:
                add_metric("Operational & Business Disclosures", "Headcount / Employees", f"{emp_val:,}", float(emp_val), "Employees")

        # Order Book / Deal TCV
        m_ob = re.search(r"(?:order\s+book|deal\s+TCV|total\s+contract\s+value)[^.\n]*?(?:INR|Rs\.?|₹|\$)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:cr|crore|mn|million|billion)", text, re.I)
        if m_ob:
            ob_val = float(m_ob.group(1).replace(",", ""))
            add_metric("Operational & Business Disclosures", "Order Book / TCV (₹ Cr)", f"₹{ob_val:.0f} Cr", ob_val, "₹ Cr")

        return metrics
