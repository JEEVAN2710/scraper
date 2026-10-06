"""Unit tests for ScreenerScraper module."""

import pytest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

from app.scraper.screener_scraper import ScreenerScraper

SAMPLE_SCREENER_HTML = """
<html>
<head><title>Infosys Ltd share price | Screener</title></head>
<body>
    <h1>Infosys Ltd</h1>
    <div class="company-links">
        <a href="https://www.infosys.com">Website</a>
    </div>
    <section id="profit-loss">
        <table class="data-table">
            <thead>
                <tr>
                    <th></th>
                    <th>Mar 2021</th>
                    <th>Mar 2022</th>
                    <th>Mar 2023</th>
                    <th>Mar 2024</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Sales +</td>
                    <td>100,472</td>
                    <td>121,641</td>
                    <td>146,767</td>
                    <td>153,670</td>
                </tr>
                <tr>
                    <td>Operating Profit</td>
                    <td>27,889</td>
                    <td>31,491</td>
                    <td>35,130</td>
                    <td>36,128</td>
                </tr>
                <tr>
                    <td>OPM %</td>
                    <td>28%</td>
                    <td>26%</td>
                    <td>24%</td>
                    <td>24%</td>
                </tr>
                <tr>
                    <td>Net Profit +</td>
                    <td>19,351</td>
                    <td>22,110</td>
                    <td>24,095</td>
                    <td>26,233</td>
                </tr>
                <tr>
                    <td>EPS in Rs</td>
                    <td>45.61</td>
                    <td>52.54</td>
                    <td>57.63</td>
                    <td>63.29</td>
                </tr>
            </tbody>
        </table>
    </section>
    <div class="annual-reports">
        <a href="https://www.bseindia.com/xml-data/corpfiling/AttachHis/sample_infy.pdf">Annual Report 2024</a>
    </div>
</body>
</html>
"""


def test_screener_scraper_search_mock():
    """Test search_company parsing with mocked HTTP response."""
    scraper = ScreenerScraper()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"id": 1489, "name": "Infosys Ltd", "url": "/company/INFY/consolidated/"},
        {"id": 1296, "name": "HCL Infosystems Ltd", "url": "/company/HCL-INSYS/consolidated/"},
    ]

    with patch("httpx.Client.get", return_value=mock_response):
        results = scraper.search_company("INFY")
        assert len(results) == 2
        assert results[0]["ticker"] == "INFY"
        assert results[0]["name"] == "Infosys Ltd"


def test_screener_scraper_parse_pl():
    """Test profit & loss table parsing from HTML."""
    scraper = ScreenerScraper()
    soup = BeautifulSoup(SAMPLE_SCREENER_HTML, "html.parser")
    metrics = scraper._parse_profit_loss(soup, "INFY")

    assert len(metrics) == 4
    latest = metrics[-1]
    assert latest["period"] == "FY2024"
    # 153670 Cr in INR (153670 * 1e7 = 1,536,700,000,000)
    assert latest["revenue"] == 153670 * 1e7
    assert latest["net_profit"] == 26233 * 1e7
    assert latest["currency"] == "INR"
    assert latest["eps"] == 63.29


def test_screener_scraper_extract_annual_reports():
    """Test finding Annual Report PDF links in HTML."""
    scraper = ScreenerScraper()
    soup = BeautifulSoup(SAMPLE_SCREENER_HTML, "html.parser")
    reports = scraper._extract_annual_reports(soup)

    assert len(reports) >= 1
    assert "sample_infy.pdf" in reports[0]["url"]
    assert "Annual Report 2024" in reports[0]["title"]


def test_screener_scraper_extended_fields():
    """Test parsing about, top ratios, pros/cons, sector, and quarterly results."""
    html_extended = """
    <html>
    <body>
        <div class="about"><p class="sub">Leading global IT services and consulting provider.</p></div>
        <ul id="top-ratios">
            <li><span class="name">Market Cap</span><span class="value">₹ 6,50,000 Cr.</span></li>
            <li><span class="name">Stock P/E</span><span class="value">26.5</span></li>
            <li><span class="name">ROCE</span><span class="value">38.2 %</span></li>
            <li><span class="name">ROE</span><span class="value">31.4 %</span></li>
        </ul>
        <div class="pros"><ul><li>Company has a good return on equity (ROE) track record: 3 Years ROE 31.4%</li></ul></div>
        <div class="cons"><ul><li>Stock is trading at 7.8 times its book value</li></ul></div>
        <div id="peers"><a href="/market/it/">IT - Software</a></div>
        <section id="quarters">
            <table>
                <thead>
                    <tr><th></th><th>Dec 2023</th><th>Mar 2024</th></tr>
                </thead>
                <tbody>
                    <tr><td>Sales +</td><td>38,821</td><td>37,923</td></tr>
                    <tr><td>Operating Profit</td><td>9,418</td><td>9,380</td></tr>
                    <tr><td>OPM %</td><td>24%</td><td>25%</td></tr>
                    <tr><td>Net Profit +</td><td>6,113</td><td>7,975</td></tr>
                    <tr><td>EPS in Rs</td><td>14.76</td><td>19.26</td></tr>
                </tbody>
            </table>
        </section>
    </body>
    </html>
    """
    scraper = ScreenerScraper()
    soup = BeautifulSoup(html_extended, "html.parser")

    ratios = scraper._parse_ratios(soup)
    assert ratios["Market Cap"] == "₹ 6,50,000 Cr."
    assert ratios["Stock P/E"] == "26.5"
    assert ratios["ROCE"] == "38.2 %"

    about = scraper._parse_about(soup)
    assert "Leading global IT services" in about

    pros, cons = scraper._parse_pros_cons(soup)
    assert len(pros) == 1
    assert "return on equity" in pros[0]
    assert len(cons) == 1

    sector = scraper._parse_sector(soup)
    assert sector == "IT - Software"

    quarters = scraper._parse_quarterly_results(soup)
    assert len(quarters) == 2
    assert quarters[-1]["period"] == "Q4 FY24"
    assert quarters[-1]["raw_period"] == "Mar 2024"
    assert quarters[-1]["revenue"] == 37923 * 1e7

