"""Screener.in Scraper for searching companies, parsing financials, and downloading annual reports."""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx
from bs4 import BeautifulSoup

from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class ScreenerScraper:
    """Automates company research, financial statements extraction, and PDF scraping from Screener.in."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = "https://www.screener.in"
        self.download_dir = self.settings.DOWNLOAD_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def search_company(self, query: str) -> List[Dict[str, Any]]:
        """Search for a company on Screener.in by name or ticker."""
        logger.info("Searching Screener.in for query: '%s'", query)
        url = f"{self.base_url}/api/company/search/?q={query}"
        try:
            with httpx.Client(timeout=10.0, headers=DEFAULT_HEADERS) as client:
                res = client.get(url)
                if res.status_code == 200:
                    results = res.json()
                    parsed = []
                    for item in results:
                        item_url = item.get("url", "")
                        # Extract ticker from URL like /company/INFY/consolidated/
                        ticker_match = re.search(r"/company/([^/]+)/", item_url)
                        ticker = ticker_match.group(1).upper() if ticker_match else item.get("name", "")[:6].upper()
                        parsed.append({
                            "id": item.get("id"),
                            "name": item.get("name"),
                            "ticker": ticker,
                            "url": item_url,
                        })
                    logger.info("Found %d matching companies for query '%s'", len(parsed), query)
                    return parsed
                else:
                    logger.warning("Screener search API returned status %s for query '%s'", res.status_code, query)
                    return []
        except Exception as exc:
            logger.exception("Error querying Screener.in search API: %s", exc)
            return []

    def fetch_company_data(self, relative_url_or_ticker: str) -> Dict[str, Any]:
        """Fetch and parse company profile, financial metrics, and PDF links."""
        try:
            if relative_url_or_ticker.startswith("/company/"):
                target_url = f"{self.base_url}{relative_url_or_ticker}"
            elif "screener.in" in relative_url_or_ticker:
                target_url = relative_url_or_ticker
            else:
                ticker = relative_url_or_ticker.strip().upper()
                target_url = f"{self.base_url}/company/{ticker}/consolidated/"

            logger.info("Fetching Screener company page: %s", target_url)
            with httpx.Client(timeout=20.0, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
                res = client.get(target_url)
                if res.status_code != 200:
                    # Fallback to standalone if consolidated redirects or errors
                    if "/consolidated/" in target_url:
                        target_url = target_url.replace("/consolidated/", "/")
                        logger.info("Retrying standalone URL: %s", target_url)
                        res = client.get(target_url)

                if res.status_code != 200:
                    raise RuntimeError(f"Screener returned HTTP {res.status_code} for {target_url}")

                html = res.text
                soup = BeautifulSoup(html, "html.parser")

                # 1. Company Name & Ticker
                h1_el = soup.find("h1")
                company_name = h1_el.text.strip() if h1_el else "Unknown Company"

                ticker_match = re.search(r"/company/([^/]+)/", str(res.url))
                ticker = ticker_match.group(1).upper() if ticker_match else company_name[:6].upper()

                # 2. Company Website
                website = None
                links_container = soup.find("div", class_="company-links") or soup
                for a in links_container.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith("http") and "screener.in" not in href and "bseindia" not in href:
                        website = href
                        break

                if not website:
                    website = f"https://www.google.com/search?q={company_name}+investor+relations"

                # 3. Parse Financial Metrics (P&L Table)
                financial_data = self._parse_profit_loss(soup, ticker)

                # 4. Extract Key Financial Ratios (Market Cap, P/E, ROCE, ROE, etc.)
                ratios = self._parse_ratios(soup)

                # 5. Extract Company Description / About
                about = self._parse_about(soup)

                # 6. Extract Strengths (Pros) & Limitations (Cons)
                pros, cons = self._parse_pros_cons(soup)

                # 7. Extract Sector / Industry
                sector = self._parse_sector(soup)

                # 8. Extract Quarterly Results
                quarterly_data = self._parse_quarterly_results(soup)

                # 9. Extract Annual Report PDF Links
                annual_reports = self._extract_annual_reports(soup)

                # 10. Extract Concall Transcripts
                concalls = self._extract_concall_transcripts(soup)

                return {
                    "name": company_name,
                    "ticker": ticker,
                    "website": website,
                    "currency": "INR",
                    "source_url": str(res.url),
                    "about": about,
                    "ratios": ratios,
                    "pros": pros,
                    "cons": cons,
                    "sector": sector,
                    "financial_data": financial_data,
                    "quarterly_data": quarterly_data,
                    "annual_reports": annual_reports,
                    "concalls": concalls,
                }
        except Exception as exc:
            logger.exception("Failed to parse Screener data for %s: %s", relative_url_or_ticker, exc)
            raise

    def _parse_ratios(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract key valuation and return ratios from Screener's #top-ratios section."""
        ratios: Dict[str, str] = {}
        try:
            for li in soup.select("#top-ratios li"):
                name_el = li.select_one(".name")
                val_el = li.select_one(".value")
                if name_el and val_el:
                    key = name_el.text.strip()
                    val = re.sub(r"\s+", " ", val_el.text).strip()
                    ratios[key] = val
        except Exception as exc:
            logger.warning("Error parsing top ratios: %s", exc)
        return ratios

    def _parse_about(self, soup: BeautifulSoup) -> str:
        """Extract business description and background overview."""
        try:
            about_el = soup.select_one(".about .sub") or soup.select_one(".about")
            if about_el:
                return re.sub(r"\s+", " ", about_el.text).strip()
        except Exception as exc:
            logger.warning("Error parsing company about text: %s", exc)
        return ""

    def _parse_pros_cons(self, soup: BeautifulSoup) -> Tuple[List[str], List[str]]:
        """Extract automated pros and cons analysis items."""
        pros: List[str] = []
        cons: List[str] = []
        try:
            pros = [re.sub(r"\s+", " ", li.text).strip() for li in soup.select(".pros li")]
            cons = [re.sub(r"\s+", " ", li.text).strip() for li in soup.select(".cons li")]
        except Exception as exc:
            logger.warning("Error parsing pros and cons: %s", exc)
        return pros, cons

    def _parse_sector(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract peer sector / industry categorization."""
        try:
            sector_el = soup.select_one("#peers a") or soup.select_one(".peers a")
            if sector_el:
                return sector_el.text.strip()
        except Exception as exc:
            logger.warning("Error parsing sector: %s", exc)
        return None

    def _parse_quarterly_results(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract recent quarterly P&L results from Screener #quarters section."""
        quarters_list: List[Dict[str, Any]] = []
        try:
            q_sec = soup.find("section", id="quarters")
            if not q_sec:
                return quarters_list
            table = q_sec.find("table")
            if not table:
                return quarters_list
            thead = table.find("thead")
            tbody = table.find("tbody")
            if not thead or not tbody:
                return quarters_list
            headers = [th.text.strip() for th in thead.find_all("th") if th.text.strip()]
            if not headers:
                return quarters_list

            rows_data: Dict[str, List[str]] = {}
            for tr in tbody.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) > 1:
                    row_title = tds[0].text.strip().replace("\xa0+", "").strip().lower()
                    values = [td.text.strip().replace(",", "") for td in tds[1:]]
                    rows_data[row_title] = values

            num_q = len(headers)
            recent_idx = range(max(0, num_q - 5), num_q)
            for idx in recent_idx:
                q_period = headers[idx] if idx < len(headers) else f"Q{idx+1}"

                def _get_q_val(k: str) -> Optional[float]:
                    for r_key, vals in rows_data.items():
                        if k in r_key and idx < len(vals):
                            try:
                                v_clean = re.sub(r"[^\d.-]", "", vals[idx])
                                return float(v_clean) if v_clean else None
                            except ValueError:
                                return None
                    return None

                sales = _get_q_val("sales")
                op_profit = _get_q_val("operating profit")
                opm = _get_q_val("opm")
                net_profit = _get_q_val("net profit")
                eps = _get_q_val("eps")

                quarters_list.append({
                    "period": q_period,
                    "revenue": sales * 1e7 if sales is not None else None,
                    "operating_profit": op_profit * 1e7 if op_profit is not None else None,
                    "operating_margin": (opm / 100.0) if opm is not None else None,
                    "net_profit": net_profit * 1e7 if net_profit is not None else None,
                    "eps": eps,
                    "currency": "INR",
                })
        except Exception as exc:
            logger.warning("Error parsing quarterly results: %s", exc)
        return quarters_list

    def _parse_profit_loss(self, soup: BeautifulSoup, ticker: str) -> List[Dict[str, Any]]:
        """Parse multi-year P&L statements table from Screener HTML."""
        metrics_list: List[Dict[str, Any]] = []
        try:
            pl_section = soup.find("section", id="profit-loss")
            if not pl_section:
                logger.warning("No profit-loss section found in HTML for %s", ticker)
                return metrics_list

            table = pl_section.find("table")
            if not table:
                return metrics_list

            thead = table.find("thead")
            tbody = table.find("tbody")
            if not thead or not tbody:
                return metrics_list

            # Column periods: e.g. ['Mar 2020', 'Mar 2021', ..., 'TTM']
            headers = [th.text.strip() for th in thead.find_all("th")]
            periods = [h for h in headers if h and h.lower() != "ttm"]

            # Row mappings
            rows_data: Dict[str, List[str]] = {}
            for tr in tbody.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) > 1:
                    row_title = tds[0].text.strip().replace("\xa0+", "").strip().lower()
                    values = [td.text.strip().replace(",", "") for td in tds[1:]]
                    rows_data[row_title] = values

            # Map into structured periods (take last 4 reported fiscal years, excluding TTM)
            num_periods = len(periods)
            recent_indices = range(max(0, num_periods - 4), num_periods)

            prev_revenue = None
            prev_profit = None

            for i in recent_indices:
                period_name = periods[i].replace("Mar ", "FY") if "Mar " in periods[i] else periods[i]

                def _get_val(key: str) -> Optional[float]:
                    for r_key, vals in rows_data.items():
                        if key in r_key and i < len(vals):
                            try:
                                v_clean = re.sub(r"[^\d.-]", "", vals[i])
                                return float(v_clean) if v_clean else None
                            except ValueError:
                                return None
                    return None

                sales_cr = _get_val("sales")
                net_profit_cr = _get_val("net profit")
                operating_profit_cr = _get_val("operating profit")
                opm_pct = _get_val("opm")
                eps = _get_val("eps")

                # Screener values are in ₹ Crores (1 Cr = 10,000,000 INR)
                revenue_inr = sales_cr * 1e7 if sales_cr is not None else None
                net_profit_inr = net_profit_cr * 1e7 if net_profit_cr is not None else None
                operating_profit_inr = operating_profit_cr * 1e7 if operating_profit_cr is not None else None

                # Calculate YoY growth
                rev_growth = None
                if revenue_inr and prev_revenue and prev_revenue > 0:
                    rev_growth = round((revenue_inr - prev_revenue) / prev_revenue, 4)

                profit_growth = None
                if net_profit_inr and prev_profit and prev_profit > 0:
                    profit_growth = round((net_profit_inr - prev_profit) / prev_profit, 4)

                margin = (opm_pct / 100.0) if opm_pct is not None else None
                if margin is None and revenue_inr and operating_profit_inr:
                    margin = round(operating_profit_inr / revenue_inr, 4)

                metrics_list.append({
                    "period": period_name,
                    "revenue": revenue_inr,
                    "revenue_growth": rev_growth,
                    "net_profit": net_profit_inr,
                    "profit_growth": profit_growth,
                    "operating_profit": operating_profit_inr,
                    "operating_margin": margin,
                    "eps": eps,
                    "currency": "INR",
                })

                if revenue_inr:
                    prev_revenue = revenue_inr
                if net_profit_inr:
                    prev_profit = net_profit_inr

            logger.info("Successfully extracted %d financial periods for %s", len(metrics_list), ticker)
        except Exception as exc:
            logger.exception("Error parsing P&L table: %s", exc)

        return metrics_list

    def _extract_annual_reports(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract official PDF Annual Report download links."""
        reports: List[Dict[str, str]] = []
        seen_urls = set()

        try:
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href.lower().endswith(".pdf") and ".pdf" not in href.lower():
                    continue

                if href in seen_urls:
                    continue
                seen_urls.add(href)

                link_text = a.text.strip().replace("\n", " ")
                link_text = re.sub(r"\s+", " ", link_text).strip()

                is_annual = "annual" in link_text.lower() or "annual" in href.lower() or "bseplus" in href.lower()

                if is_annual or "corpfiling" in href.lower():
                    label = link_text if len(link_text) > 3 else "Annual Report"
                    reports.append({
                        "title": label,
                        "url": href,
                    })

            logger.info("Found %d annual report PDF links on page", len(reports))
        except Exception as exc:
            logger.exception("Error extracting report links: %s", exc)

        return reports

    def _extract_concall_transcripts(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract quarterly concall transcript links and periods from Screener HTML."""
        concalls: List[Dict[str, Any]] = []
        try:
            concall_div = soup.find("div", class_="concalls")
            if not concall_div:
                logger.info("No concalls section found on page")
                return concalls

            for li in concall_div.find_all("li"):
                period_el = li.find("div", class_="ink-600")
                period = period_el.text.strip() if period_el else "Unknown Period"

                transcript_url = None
                for a in li.find_all("a", href=True):
                    href = a["href"].strip()
                    text = a.text.strip().lower()
                    title = (a.get("title") or "").lower()

                    # Exclude audio/video links
                    if href.lower().endswith((".mp3", ".mp4", ".wav", ".m4a", ".ogg")):
                        continue
                    if "youtu" in href.lower():
                        continue

                    if text == "transcript" or "transcript" in title:
                        transcript_url = href
                        break

                if transcript_url:
                    concalls.append({
                        "period": period,
                        "title": f"Concall Transcript {period}",
                        "url": transcript_url,
                    })

            logger.info("Extracted %d concall transcripts with downloadable PDFs", len(concalls))
        except Exception as exc:
            logger.exception("Error extracting concall transcripts: %s", exc)

        return concalls

    def download_pdf(
        self,
        pdf_url: str,
        ticker: str,
        report_title: str = "Annual_Report",
        timeout: float = 45.0,
    ) -> Path:
        """Download official PDF report to local downloads directory."""
        # Strip URL fragment like #page=169
        pdf_url = pdf_url.split("#")[0].strip()
        clean_title = re.sub(r"[^\w\-]", "_", report_title).strip("_")
        file_name = f"{ticker}_{clean_title}.pdf"
        target_path = self.download_dir / file_name

        logger.info("Downloading PDF from %s to %s...", pdf_url, target_path)

        try:
            with httpx.Client(timeout=timeout, headers=DEFAULT_HEADERS, follow_redirects=True) as client:
                res = client.get(pdf_url)
                if res.status_code != 200:
                    raise RuntimeError(f"HTTP error {res.status_code} downloading PDF from {pdf_url}")

                target_path.write_bytes(res.content)
                logger.info("Successfully downloaded %d bytes to %s", len(res.content), target_path)
                return target_path
        except Exception as exc:
            logger.exception("Failed to download PDF from %s: %s", pdf_url, exc)
            raise
