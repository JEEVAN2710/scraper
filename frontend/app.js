/**
 * Financial AI Intelligence Suite - Frontend Controller
 * Handles live company browsing, KPI rendering, and multi-format exports.
 */

let allCompanies = [];
let selectedCompanyId = null;
let currentCompanyDetail = null;

// Currency & Number Formatters
const formatCurrency = (val, currency = "USD") => {
    if (val === null || val === undefined) return "N/A";
    const symbol = currency === "INR" ? "₹" : "$";
    if (Math.abs(val) >= 1e9) {
        return `${symbol}${(val / 1e9).toFixed(2)} B`;
    }
    if (Math.abs(val) >= 1e6) {
        return `${symbol}${(val / 1e6).toFixed(2)} M`;
    }
    if (Math.abs(val) >= 1e3) {
        return `${symbol}${(val / 1e3).toFixed(2)} K`;
    }
    return `${symbol}${val.toLocaleString()}`;
};

const formatPercent = (val) => {
    if (val === null || val === undefined) return "N/A";
    const sign = val > 0 ? "+" : "";
    return `${sign}${(val * 100).toFixed(1)}%`;
};

// Toast Notification Manager
function showToast(message, type = "success") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span>${type === "success" ? "✓" : "ℹ"}</span>
        <span>${message}</span>
    `;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(8px)";
        setTimeout(() => toast.remove(), 250);
    }, 3500);
}

// System Health Check
async function fetchHealth() {
    try {
        const res = await fetch("/api/health");
        if (!res.ok) throw new Error("Health check failed");
        const data = await res.json();

        const dbPill = document.getElementById("dbStatusPill");
        const dot = dbPill.querySelector(".status-dot");
        const label = dbPill.querySelector(".status-label");

        if (data.mysql && data.mysql.status === "healthy") {
            dot.className = "status-dot healthy";
            label.textContent = `MySQL: Connected (${data.mysql.server_version || "8.0"})`;
        } else {
            dot.className = "status-dot";
            label.textContent = "MySQL: Standby (Demo Mode Active)";
        }

        const llmPill = document.getElementById("llmStatusPill");
        if (data.ollama && data.ollama.target_model) {
            llmPill.querySelector(".status-label").textContent = `LLM: ${data.ollama.target_model} (Local)`;
        }
    } catch (err) {
        console.warn("Health check error:", err);
    }
}

// Load Companies List
async function loadCompanies() {
    const companyListEl = document.getElementById("companyList");
    try {
        const res = await fetch("/api/companies");
        if (!res.ok) throw new Error("Could not fetch companies");
        allCompanies = await res.json();

        document.getElementById("companyCountBadge").textContent = `${allCompanies.length} Active`;
        renderCompanyList(allCompanies);

        // Select first company by default
        if (allCompanies.length > 0) {
            selectCompany(allCompanies[0].id);
        }
    } catch (err) {
        console.error("Failed loading companies:", err);
        companyListEl.innerHTML = `<div class="loading-state"><span>Failed loading companies. Verify backend server is running.</span></div>`;
    }
}

// Render Sidebar List
function renderCompanyList(companies) {
    const companyListEl = document.getElementById("companyList");
    if (!companies.length) {
        companyListEl.innerHTML = `<div class="loading-state"><span>No matching companies found.</span></div>`;
        return;
    }

    companyListEl.innerHTML = companies.map(c => `
        <div class="company-item ${c.id === selectedCompanyId ? 'active' : ''}" data-id="${c.id}" onclick="selectCompany(${c.id})">
            <div class="ci-info">
                <span class="ci-name">${c.name}</span>
                <span class="ci-ticker">${c.ticker || 'N/A'} • ${c.document_count || 0} Docs</span>
            </div>
            <div class="ci-meta">
                <div class="ci-revenue">${c.latest_revenue ? formatCurrency(c.latest_revenue, c.currency) : 'N/A'}</div>
                <div class="ci-period">${c.latest_period || ''}</div>
            </div>
        </div>
    `).join("");
}

// Select & Load Full Company Dossier
async function selectCompany(companyId) {
    selectedCompanyId = companyId;

    if (window.innerWidth <= 768 && typeof closeMobileSidebar === "function") {
        closeMobileSidebar();
    }

    // Update active highlight in sidebar
    document.querySelectorAll(".company-item").forEach(el => {
        el.classList.toggle("active", parseInt(el.dataset.id) === companyId);
    });

    try {
        const res = await fetch(`/api/companies/${companyId}`);
        if (!res.ok) throw new Error("Could not fetch company details");
        currentCompanyDetail = await res.json();
        renderCompanyDetail(currentCompanyDetail);
    } catch (err) {
        console.error("Error fetching company details:", err);
        showToast("Error loading company dossier", "info");
    }
}

// Render Main Dashboard Views
function renderCompanyDetail(company) {
    // 1. Hero Card
    document.getElementById("heroTicker").textContent = company.ticker || "N/A";
    document.getElementById("heroName").textContent = company.name;
    const websiteLink = document.getElementById("heroWebsite");
    const websiteText = document.getElementById("heroWebsiteText");

    if (company.website) {
        websiteLink.href = company.website;
        websiteText.textContent = company.website;
        websiteLink.style.display = "inline-flex";
    } else {
        websiteLink.style.display = "none";
    }

    // Sector Badge
    const sectorBadge = document.getElementById("heroSector");
    if (sectorBadge) {
        if (company.sector) {
            sectorBadge.textContent = company.sector;
            sectorBadge.style.display = "inline-flex";
        } else {
            sectorBadge.style.display = "none";
        }
    }

    // Company Description / About
    const aboutBox = document.getElementById("heroAboutBox");
    const aboutText = document.getElementById("heroAboutText");
    if (aboutBox && aboutText) {
        if (company.about) {
            aboutText.textContent = company.about;
            aboutBox.style.display = "block";
        } else {
            aboutBox.style.display = "none";
        }
    }

    // Key Financial Ratios Ribbon
    const ribbon = document.getElementById("keyRatiosRibbon");
    if (ribbon) {
        const ratios = company.ratios || {};
        const hasRatios = Object.keys(ratios).length > 0;
        if (hasRatios) {
            ribbon.style.display = "flex";
            const setVal = (id, key) => {
                const el = document.getElementById(id);
                if (el) el.textContent = ratios[key] || "—";
            };
            setVal("ratioMarketCap", "Market Cap");
            setVal("ratioCurrentPrice", "Current Price");
            setVal("ratioHighLow", "High / Low");
            setVal("ratioStockPE", "Stock P/E");
            setVal("ratioBookValue", "Book Value");
            setVal("ratioDivYield", "Dividend Yield");
            setVal("ratioROCE", "ROCE");
            setVal("ratioROE", "ROE");
        } else {
            ribbon.style.display = "none";
        }
    }

    document.getElementById("heroPeriod").textContent = company.latest_period || "FY2024";
    const currSymbol = company.currency === "INR" ? "₹ INR" : `${company.currency} ($)`;
    document.getElementById("heroCurrency").textContent = currSymbol;
    document.getElementById("heroReportCount").textContent = `${company.documents ? company.documents.length : 0} Reports`;

    // Show processing status and re-process button for failed documents
    const docs = company.documents || [];
    const failedDocs = docs.filter(d => d.processing_status === 'failed');
    const statusArea = document.getElementById("heroStatusArea");
    if (statusArea) {
        if (failedDocs.length > 0) {
            statusArea.innerHTML = `
                <div class="processing-alert">
                    <span class="alert-icon">⚠</span>
                    <span>PDF extraction failed for ${failedDocs.length} document(s). Data may be incomplete.</span>
                    <button class="btn btn-sm btn-accent" onclick="reprocessCompany(${company.id})" id="btnReprocess">
                        <span id="reprocessBtnText">🔄 Re-Process PDF</span>
                        <span id="reprocessSpinner" class="spinner" style="display:none;"></span>
                    </button>
                </div>
            `;
            statusArea.style.display = "flex";
        } else {
            statusArea.innerHTML = '';
            statusArea.style.display = "none";
        }
    }

    // 2. KPIs
    const metrics = company.financial_data || [];
    const latest = metrics.length ? metrics[metrics.length - 1] : {};

    // Revenue KPI
    document.getElementById("kpiRevenue").textContent = formatCurrency(latest.revenue, company.currency);
    const revGrowthEl = document.getElementById("kpiRevenueGrowth");
    if (latest.revenue_growth !== null && latest.revenue_growth !== undefined) {
        revGrowthEl.textContent = `${formatPercent(latest.revenue_growth)} YoY`;
        revGrowthEl.className = `kpi-growth ${latest.revenue_growth >= 0 ? 'growth-up' : 'growth-down'}`;
    } else {
        revGrowthEl.textContent = "N/A";
    }

    // Profit KPI
    document.getElementById("kpiProfit").textContent = formatCurrency(latest.net_profit, company.currency);
    const profitGrowthEl = document.getElementById("kpiProfitGrowth");
    if (latest.profit_growth !== null && latest.profit_growth !== undefined) {
        profitGrowthEl.textContent = `${formatPercent(latest.profit_growth)} YoY`;
        profitGrowthEl.className = `kpi-growth ${latest.profit_growth >= 0 ? 'growth-up' : 'growth-down'}`;
    } else {
        profitGrowthEl.textContent = "N/A";
    }

    // Margin KPI
    document.getElementById("kpiMargin").textContent = latest.operating_margin ? `${(latest.operating_margin * 100).toFixed(1)}%` : "N/A";
    document.getElementById("kpiOperatingProfit").textContent = latest.operating_profit ? `${formatCurrency(latest.operating_profit, company.currency)} EBIT` : "Operational";

    // EPS KPI
    document.getElementById("kpiEps").textContent = latest.eps !== null && latest.eps !== undefined ? `${company.currency === 'INR' ? '₹' : '$'}${latest.eps.toFixed(2)}` : "N/A";

    // 3. Tab 1: Financial Statements Table
    const finTbody = document.getElementById("financialTableBody");
    if (!metrics.length) {
        finTbody.innerHTML = `<tr><td colspan="10" style="text-align:center; color:var(--text-dim); padding:2rem;">No financial records extracted yet.</td></tr>`;
    } else {
        finTbody.innerHTML = metrics.map(m => `
            <tr>
                <td class="table-period">${m.period}</td>
                <td style="font-weight:600;">${formatCurrency(m.revenue, m.currency)}</td>
                <td class="${(m.revenue_growth || 0) >= 0 ? 'text-success' : ''}">${formatPercent(m.revenue_growth)}</td>
                <td>${formatCurrency(m.net_profit, m.currency)}</td>
                <td class="${(m.profit_growth || 0) >= 0 ? 'text-success' : ''}">${formatPercent(m.profit_growth)}</td>
                <td>${formatCurrency(m.operating_profit, m.currency)}</td>
                <td>${m.operating_margin ? (m.operating_margin * 100).toFixed(1) + '%' : 'N/A'}</td>
                <td style="font-family:var(--font-mono); font-weight:600;">${m.eps !== null && m.eps !== undefined ? (m.currency === 'INR' ? '₹' : '$') + m.eps.toFixed(2) : 'N/A'}</td>
                <td>${formatCurrency(m.total_assets, m.currency)}</td>
                <td>${formatCurrency(m.cash_flow, m.currency)}</td>
            </tr>
        `).join("");
    }

    // Quarterly Results Table
    const qHeader = document.getElementById("quarterlySectionHeader");
    const qContainer = document.getElementById("quarterlyTableContainer");
    const qTbody = document.getElementById("quarterlyTableBody");
    const qData = company.quarterly_data || [];
    if (qHeader && qContainer && qTbody) {
        if (qData.length > 0) {
            qHeader.style.display = "flex";
            qContainer.style.display = "block";
            qTbody.innerHTML = qData.map(q => `
                <tr>
                    <td class="table-period">${q.period}</td>
                    <td style="font-weight:600;">${formatCurrency(q.revenue, q.currency)}</td>
                    <td>${formatCurrency(q.operating_profit, q.currency)}</td>
                    <td>${q.operating_margin ? (q.operating_margin * 100).toFixed(1) + '%' : '—'}</td>
                    <td>${formatCurrency(q.net_profit, q.currency)}</td>
                    <td style="font-family:var(--font-mono); font-weight:600;">${q.eps !== null && q.eps !== undefined ? '₹' + q.eps.toFixed(2) : '—'}</td>
                </tr>
            `).join("");
        } else {
            qHeader.style.display = "none";
            qContainer.style.display = "none";
            qTbody.innerHTML = "";
        }
    }

    // 4. Tab 2: Risks Grid
    const risksGrid = document.getElementById("risksGrid");
    const risks = company.risks || [];
    if (!risks.length) {
        risksGrid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; color:var(--text-dim); padding:2rem;">No risk factor disclosures detected for this report.</div>`;
    } else {
        risksGrid.innerHTML = risks.map(r => `
            <div class="risk-card">
                <div class="risk-card-header">
                    <span class="risk-title">${r.risk}</span>
                    <span class="citation-pill">Page ${r.page_number || 'N/A'} Citation</span>
                </div>
                <p class="risk-desc">${r.description || 'No detailed excerpt available.'}</p>
            </div>
        `).join("");
    }

    // 5. Tab 3: Documents Registry Table (Annual Reports & Filings)
    const docsTbody = document.getElementById("documentsTableBody");
    const annualDocs = docs.filter(d => d.document_type !== 'concall_transcript' && !(d.file_name && d.file_name.toLowerCase().includes('concall')));
    if (!annualDocs.length) {
        docsTbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-dim); padding:2rem;">No annual reports tracked for this company.</td></tr>`;
    } else {
        docsTbody.innerHTML = annualDocs.map(d => `
            <tr>
                <td style="font-weight:600;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle; margin-right:6px; color:#06b6d4;">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                    ${d.file_name}
                </td>
                <td><span class="badge">${d.document_type || 'annual_report'}</span></td>
                <td>${d.report_period || 'N/A'}</td>
                <td><span class="hash-badge" title="${d.file_hash}">${d.file_hash ? d.file_hash.substring(0, 16) + '...' : 'Verified'}</span></td>
                <td><span class="status-badge-success">✓ ${(d.processing_status || 'processed').toUpperCase()}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline" onclick="triggerPdfDownload(${d.id})">
                        <span>Download</span>
                    </button>
                </td>
            </tr>
        `).join("");
    }

    // 6. Tab 4: Concall Transcripts Table
    const concallsTbody = document.getElementById("concallsTableBody");
    const concallBadge = document.getElementById("concallCountBadge");
    const concallDocs = docs.filter(d => d.document_type === 'concall_transcript' || (d.file_name && d.file_name.toLowerCase().includes('concall')));
    if (concallBadge) {
        concallBadge.textContent = `${concallDocs.length} Transcripts`;
    }
    if (concallsTbody) {
        if (!concallDocs.length) {
            concallsTbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-dim); padding:2rem;">No quarterly concall transcripts ingested yet. Use "Scrape from Screener" to automatically download and ingest concall transcripts.</td></tr>`;
        } else {
            concallsTbody.innerHTML = concallDocs.map(d => `
                <tr>
                    <td style="font-weight:600; color:var(--text-bright);">${d.report_period || 'N/A'}</td>
                    <td>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:middle; margin-right:6px; color:#a855f7;">
                            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                            <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                            <line x1="12" y1="19" x2="12" y2="23"></line>
                            <line x1="8" y1="23" x2="16" y2="23"></line>
                        </svg>
                        ${d.file_name}
                    </td>
                    <td><span class="hash-badge" title="${d.file_hash}">${d.file_hash ? d.file_hash.substring(0, 16) + '...' : 'Verified'}</span></td>
                    <td><span class="status-badge-success">✓ ${(d.processing_status || 'processed').toUpperCase()}</span></td>
                    <td>
                        <button class="btn btn-sm btn-outline" onclick="triggerPdfDownload(${d.id})">
                            <span>Download PDF</span>
                        </button>
                    </td>
                </tr>
            `).join("");
        }
    }

    // 7. Load Knowledge Graph for Neo4j view
    loadKnowledgeGraph(company.id);
}

// Re-Process Failed Documents
async function reprocessCompany(companyId) {
    const btnText = document.getElementById("reprocessBtnText");
    const spinner = document.getElementById("reprocessSpinner");
    const btn = document.getElementById("btnReprocess");

    if (btn) btn.disabled = true;
    if (btnText) btnText.textContent = "Re-Processing...";
    if (spinner) spinner.style.display = "inline-block";

    try {
        const res = await fetch(`/api/scrape/reprocess/${companyId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        });

        const data = await res.json();
        if (!res.ok || !data.success) {
            throw new Error(data.detail || data.error || "Re-processing failed");
        }

        showToast(`Re-processed ${data.name || 'company'}: ${data.chunks_count} chunks, ${data.risks_count} risks extracted!`, "success");

        // Refresh the company detail view
        await loadCompanies();
        await selectCompany(companyId);
    } catch (err) {
        console.error("Re-processing error:", err);
        showToast(`Re-process failed: ${err.message}`, "info");
    } finally {
        if (btn) btn.disabled = false;
        if (btnText) btnText.textContent = "🔄 Re-Process PDF";
        if (spinner) spinner.style.display = "none";
    }
}

// Download Handlers
function triggerPdfDownload(docId = null) {
    if (!currentCompanyDetail) return;
    const docs = currentCompanyDetail.documents || [];
    const targetDoc = docId ? docs.find(d => d.id === docId) : (docs[0] || null);

    if (!targetDoc) {
        showToast("No PDF report available to download.", "info");
        return;
    }

    showToast(`Downloading PDF: ${targetDoc.file_name}...`, "success");
    window.location.href = `/api/documents/${targetDoc.id}/download`;
}

function triggerExcelExport() {
    if (!selectedCompanyId) return;
    showToast("Generating multi-sheet Excel report (.xlsx)...", "success");
    window.location.href = `/api/export/excel/${selectedCompanyId}`;
}

function triggerCsvExport() {
    if (!selectedCompanyId) return;
    showToast("Exporting financial metrics CSV...", "success");
    window.location.href = `/api/export/csv/${selectedCompanyId}`;
}

// Graph RAG & AI Assistant Controller
async function submitAiQuestion(customQuestion = null) {
    const input = document.getElementById("aiQuestionInput");
    const question = (customQuestion || input.value).trim();
    if (!question) {
        showToast("Please enter a question to ask the AI assistant.", "info");
        return;
    }

    if (customQuestion) {
        input.value = customQuestion;
    }

    // Switch to AI tab if not already active
    const aiTabBtn = document.querySelector('[data-tab="tab-ai-chat"]');
    if (aiTabBtn && !aiTabBtn.classList.contains("active")) {
        aiTabBtn.click();
    }

    // Set Loading UI
    const btn = document.getElementById("btnAskAi");
    const btnText = document.getElementById("btnAskAiText");
    const spinner = document.getElementById("aiSpinner");
    const subgraphView = document.getElementById("subgraphView");
    const nodesContainer = document.getElementById("nodesContainer");
    const aiResponseCard = document.getElementById("aiResponseCard");
    const aiResponseBody = document.getElementById("aiResponseBody");
    const aiModelTag = document.getElementById("aiModelTag");
    const aiCitationsBox = document.getElementById("aiCitationsBox");
    const citationsList = document.getElementById("citationsList");

    btn.disabled = true;
    btnText.textContent = "Traversing Graph...";
    spinner.style.display = "inline-block";

    try {
        const res = await fetch("/api/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: question,
                company_id: selectedCompanyId,
            }),
        });

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || "Inference failed");
        }

        const data = await res.json();

        // 1. Render Subgraph Nodes
        if (data.graph_nodes && data.graph_nodes.length > 0) {
            nodesContainer.innerHTML = data.graph_nodes
                .map(node => `<span class="node-pill">${node}</span>`)
                .join("");
            subgraphView.style.display = "flex";
        } else {
            subgraphView.style.display = "none";
        }

        // 2. Render AI Answer
        aiResponseBody.innerHTML = data.answer.replace(/\n/g, "<br>");
        aiModelTag.textContent = `Engine: ${data.llm_used}`;
        aiResponseCard.style.display = "flex";

        // 3. Render Citations
        if (data.citations && data.citations.length > 0) {
            citationsList.innerHTML = data.citations
                .map(c => `
                    <div class="citation-row">
                        <span>•</span>
                        <span class="citation-file">${c.source}</span>
                        <span class="citation-page">Page ${c.page}</span>
                        <span style="color:var(--text-dim); font-size:0.75rem;">(${c.company} - ${c.period})</span>
                    </div>
                `)
                .join("");
            aiCitationsBox.style.display = "flex";
        } else {
            aiCitationsBox.style.display = "none";
        }

        showToast("Graph RAG answer synthesized successfully.", "success");
    } catch (err) {
        console.error("AI Ask error:", err);
        showToast(`AI error: ${err.message}`, "info");
    } finally {
        btn.disabled = false;
        btnText.textContent = "Ask Assistant";
        spinner.style.display = "none";
    }
}

function submitQuickQuestion(text) {
    submitAiQuestion(text);
}

// Screener Scraper Modal Controller
let searchDebounceTimer = null;

function openScreenerModal() {
    const modal = document.getElementById("scraperModal");
    if (modal) {
        modal.style.display = "flex";
        document.getElementById("screenerSearchInput").focus();
        resetIngestModalState();
    }
}

function closeScreenerModal() {
    const modal = document.getElementById("scraperModal");
    if (modal) {
        modal.style.display = "none";
    }
}

function resetIngestModalState() {
    const progressCard = document.getElementById("pipelineProgressCard");
    const resultCard = document.getElementById("ingestionResultCard");
    const stagesBox = document.getElementById("pipelineStages");
    const dropdown = document.getElementById("screenerDropdown");
    if (progressCard) progressCard.style.display = "none";
    if (resultCard) resultCard.style.display = "none";
    if (stagesBox) stagesBox.innerHTML = "";
    if (dropdown) dropdown.style.display = "none";
    const btn = document.getElementById("btnExecuteIngest");
    if (btn) {
        btn.disabled = false;
        document.getElementById("btnExecuteIngestText").textContent = "Scrape & Ingest into Knowledge Graph";
        document.getElementById("ingestBtnSpinner").style.display = "none";
    }
}

function selectScreenerSuggestion(ticker) {
    const input = document.getElementById("screenerSearchInput");
    if (input) {
        input.value = ticker;
    }
    const dropdown = document.getElementById("screenerDropdown");
    if (dropdown) {
        dropdown.style.display = "none";
    }
}

async function handleScreenerSearchInput(e) {
    const query = e.target.value.trim();
    const dropdown = document.getElementById("screenerDropdown");
    if (!dropdown) return;

    if (query.length < 2) {
        dropdown.style.display = "none";
        return;
    }

    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(async () => {
        try {
            const res = await fetch("/api/scrape/search", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query }),
            });
            if (!res.ok) return;
            const results = await res.json();
            if (results && results.length > 0) {
                dropdown.innerHTML = results.map(r => `
                    <div class="screener-item" onclick="selectScreenerSuggestion('${r.ticker}')">
                        <span class="screener-item-name">${r.name}</span>
                        <span class="screener-item-ticker">${r.ticker}</span>
                    </div>
                `).join("");
                dropdown.style.display = "block";
            } else {
                dropdown.style.display = "none";
            }
        } catch (err) {
            console.warn("Screener search error:", err);
        }
    }, 250);
}

async function executeScreenerIngestion() {
    const input = document.getElementById("screenerSearchInput");
    const query = input ? input.value.trim() : "";
    if (!query) {
        showToast("Please enter a company name or ticker to scrape.", "info");
        return;
    }

    const btn = document.getElementById("btnExecuteIngest");
    const btnText = document.getElementById("btnExecuteIngestText");
    const spinner = document.getElementById("ingestBtnSpinner");
    const progressCard = document.getElementById("pipelineProgressCard");
    const statusText = document.getElementById("pipelineStatusText");
    const stagesBox = document.getElementById("pipelineStages");
    const resultCard = document.getElementById("ingestionResultCard");

    btn.disabled = true;
    btnText.textContent = "Scraping & Ingesting...";
    spinner.style.display = "inline-block";
    progressCard.style.display = "flex";
    resultCard.style.display = "none";
    stagesBox.innerHTML = `
        <div class="pipeline-stage-item"><span class="stage-check">✓</span> <span>Connecting to Screener.in for ${query}...</span></div>
    `;

    try {
        const res = await fetch("/api/scrape/ingest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query }),
        });

        const data = await res.json();
        if (!res.ok || !data.success) {
            throw new Error(data.error || "Ingestion pipeline encountered an issue");
        }

        // Display stages
        stagesBox.innerHTML = (data.stages || []).map(s => `
            <div class="pipeline-stage-item"><span class="stage-check">✓</span> <span>${s}</span></div>
        `).join("");

        statusText.textContent = `Completed in ${data.duration_seconds}s! Stored in Knowledge Graph.`;

        // Render result card
        resultCard.innerHTML = `
            <div class="result-success-title">
                <span>✓</span>
                <span>Successfully Ingested ${data.name} (${data.ticker})</span>
            </div>
            <div class="result-stats-grid">
                <div class="result-stat-item">
                    <div class="result-stat-val">${data.metrics_count}</div>
                    <div class="result-stat-lbl">Fiscal Periods</div>
                </div>
                <div class="result-stat-item">
                    <div class="result-stat-val">${data.risks_count}</div>
                    <div class="result-stat-lbl">Risk Factors</div>
                </div>
                <div class="result-stat-item">
                    <div class="result-stat-val">${data.chunks_count}</div>
                    <div class="result-stat-lbl">Text Chunks</div>
                </div>
            </div>
        `;
        resultCard.style.display = "flex";

        showToast(`Ingested ${data.name} into Knowledge Graph!`, "success");

        // Reload companies list in background
        await loadCompanies();

        // Auto select newly ingested company
        if (data.company_id) {
            await selectCompany(data.company_id);
        }

    } catch (err) {
        console.error("Ingestion failed:", err);
        statusText.textContent = `Pipeline Error: ${err.message}`;
        showToast(`Failed: ${err.message}`, "info");
    } finally {
        btn.disabled = false;
        btnText.textContent = "Scrape Another Company";
        spinner.style.display = "none";
    }
}

// ==============================================================================
// Universal Dynamic Live Search & Screener Extraction
// ==============================================================================
let liveSearchDebounceTimer = null;

function initUniversalSearch() {
    const input = document.getElementById("companySearchInput");
    const dropdown = document.getElementById("liveSearchDropdown");
    const spinner = document.getElementById("searchLiveSpinner");
    if (!input || !dropdown) return;

    input.addEventListener("input", (e) => {
        const query = e.target.value.trim();
        const lowerQuery = query.toLowerCase();

        // 1. Instant local filtering of saved companies
        const localMatches = allCompanies.filter(c =>
            c.name.toLowerCase().includes(lowerQuery) || (c.ticker && c.ticker.toLowerCase().includes(lowerQuery))
        );
        renderCompanyList(localMatches);

        if (query.length < 2) {
            dropdown.style.display = "none";
            dropdown.innerHTML = "";
            if (spinner) spinner.style.display = "none";
            return;
        }

        // 2. Debounced query to live Screener.in search
        clearTimeout(liveSearchDebounceTimer);
        if (spinner) spinner.style.display = "block";

        liveSearchDebounceTimer = setTimeout(async () => {
            try {
                const res = await fetch("/api/scrape/search", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ query }),
                });

                if (spinner) spinner.style.display = "none";
                if (!res.ok) return;

                const remoteResults = await res.json();
                renderLiveSearchDropdown(localMatches, remoteResults, query);
            } catch (err) {
                if (spinner) spinner.style.display = "none";
                console.warn("Live Screener search error:", err);
            }
        }, 220);
    });

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const query = input.value.trim();
            if (!query) return;

            // Check if local company matches
            const exactLocal = allCompanies.find(c => 
                (c.ticker && c.ticker.toLowerCase() === query.toLowerCase()) ||
                c.name.toLowerCase() === query.toLowerCase()
            );
            if (exactLocal) {
                dropdown.style.display = "none";
                selectCompany(exactLocal.id);
                return;
            }

            // Otherwise initiate live extraction from Screener
            dropdown.style.display = "none";
            startLiveScreenerIngestion(query);
        } else if (e.key === "Escape") {
            dropdown.style.display = "none";
        }
    });

    document.addEventListener("click", (e) => {
        if (!e.target.closest(".search-box") && !e.target.closest("#liveSearchDropdown")) {
            dropdown.style.display = "none";
        }
    });
}

function renderLiveSearchDropdown(localMatches, remoteResults, query) {
    const dropdown = document.getElementById("liveSearchDropdown");
    if (!dropdown) return;

    let html = "";

    // Local results section
    if (localMatches.length > 0) {
        html += `<div class="lsd-section-title">Saved Companies (${localMatches.length})</div>`;
        localMatches.slice(0, 3).forEach(c => {
            html += `
                <div class="lsd-item local" onclick="selectCompanyFromSearch(${c.id})">
                    <div class="lsd-info">
                        <span class="lsd-name">${c.name}</span>
                        <span class="lsd-ticker">${c.ticker || '—'}</span>
                    </div>
                    <span class="lsd-badge saved">✓ In Database</span>
                </div>
            `;
        });
    }

    // Remote Screener results section
    const localTickers = new Set(allCompanies.map(c => (c.ticker || '').toUpperCase()));
    const uningestedRemote = (remoteResults || []).filter(r => !localTickers.has(r.ticker.toUpperCase()));

    if (uningestedRemote.length > 0) {
        html += `<div class="lsd-section-title">Screener.in (Live Companies)</div>`;
        uningestedRemote.slice(0, 6).forEach(r => {
            html += `
                <div class="lsd-item remote" onclick="startLiveScreenerIngestion('${r.ticker}')">
                    <div class="lsd-info">
                        <span class="lsd-name">${r.name}</span>
                        <span class="lsd-ticker">${r.ticker}</span>
                    </div>
                    <span class="lsd-badge fetch">⚡ Fetch & Extract PDF</span>
                </div>
            `;
        });
    } else if (localMatches.length === 0) {
        html += `
            <div class="lsd-item remote" onclick="startLiveScreenerIngestion('${query}')">
                <div class="lsd-info">
                    <span class="lsd-name">Search Screener for "${query}"</span>
                    <span class="lsd-ticker">Extract Financials & Official PDFs</span>
                </div>
                <span class="lsd-badge fetch">⚡ Scrape Now</span>
            </div>
        `;
    }

    dropdown.innerHTML = html;
    dropdown.style.display = html ? "block" : "none";
}

function selectCompanyFromSearch(companyId) {
    const dropdown = document.getElementById("liveSearchDropdown");
    if (dropdown) dropdown.style.display = "none";
    selectCompany(companyId);
}

async function startLiveScreenerIngestion(queryOrTicker) {
    const query = queryOrTicker.trim();
    if (!query) return;

    const dropdown = document.getElementById("liveSearchDropdown");
    if (dropdown) dropdown.style.display = "none";

    const progressCard = document.getElementById("screenerLiveProgress");
    const slpTitle = document.getElementById("slpTitle");
    const slpSubtitle = document.getElementById("slpSubtitle");
    const slpStages = document.getElementById("slpStages");

    if (progressCard) {
        progressCard.style.display = "block";
        progressCard.style.opacity = "1";
        if (slpTitle) slpTitle.textContent = `Extracting "${query}" from Screener.in...`;
        if (slpSubtitle) slpSubtitle.textContent = "Connecting to market feeds, downloading official PDFs & building Knowledge Graph";
        if (slpStages) {
            slpStages.innerHTML = `
                <div class="slp-stage-item active">
                    <span class="slp-stage-icon">⏳</span>
                    <span>Connecting to Screener.in and parsing financials...</span>
                </div>
            `;
        }
        progressCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    try {
        const res = await fetch("/api/scrape/ingest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query }),
        });

        const data = await res.json();
        if (!res.ok || !data.success) {
            throw new Error(data.error || "Extraction pipeline encountered an issue");
        }

        // Render completed stages
        if (slpStages) {
            slpStages.innerHTML = (data.stages || []).map(s => `
                <div class="slp-stage-item done">
                    <span class="slp-stage-icon">✓</span>
                    <span>${s}</span>
                </div>
            `).join("");
        }

        if (slpTitle) {
            slpTitle.textContent = `✓ Successfully Extracted ${data.name} (${data.ticker})`;
            slpSubtitle.textContent = `Completed in ${data.duration_seconds}s • ${data.metrics_count} Statements • ${data.risks_count} Risk Factors • ${data.chunks_count} Chunks`;
        }

        showToast(`Extracted ${data.name} with official PDF!`, "success");

        // Reload company list in background
        await loadCompanies();

        // Select the newly ingested company
        if (data.company_id) {
            await selectCompany(data.company_id);
        }

        // Fade progress card after 3.5 seconds
        setTimeout(() => {
            if (progressCard) {
                progressCard.style.transition = "opacity 0.4s ease";
                progressCard.style.opacity = "0";
                setTimeout(() => {
                    progressCard.style.display = "none";
                    progressCard.style.opacity = "1";
                }, 400);
            }
        }, 3500);

    } catch (err) {
        console.error("Live extraction failed:", err);
        if (slpTitle) slpTitle.textContent = `Extraction Issue for "${query}"`;
        if (slpSubtitle) slpSubtitle.textContent = err.message || "Failed to fetch from Screener.in";
        if (slpStages) {
            slpStages.innerHTML = `
                <div class="slp-stage-item error">
                    <span class="slp-stage-icon">✕</span>
                    <span>${err.message || "Could not complete extraction. Check server connection."}</span>
                </div>
            `;
        }
        showToast(`Extraction failed: ${err.message}`, "info");
    }
}

// ==============================================================================
// Responsive Layout, Resizers & Collapsible Navigation Controllers
// ==============================================================================
function initResponsiveLayoutAndResizers() {
    const workspaceGrid = document.getElementById("workspaceGrid");
    const sidebar = document.getElementById("sidebar");
    const sidebarResizer = document.getElementById("sidebarResizer");
    const sidebarToggleBtn = document.getElementById("sidebarToggleBtn");
    const sidebarCollapseBtn = document.getElementById("sidebarCollapseBtn");
    const sidebarExpandFloatingBtn = document.getElementById("sidebarExpandFloatingBtn");
    const sidebarBackdrop = document.getElementById("sidebarBackdrop");

    const graphExplorerBody = document.getElementById("graphExplorerBody");
    const inspectorResizer = document.getElementById("inspectorResizer");
    const graphInspector = document.getElementById("graphInspector");
    const inspectorToggleBtn = document.getElementById("inspectorToggleBtn");
    const btnShowInspector = document.getElementById("btnShowInspector");

    // 1. Restore Persisted Preferences
    const savedSidebarWidth = localStorage.getItem("preferred_sidebar_width");
    if (savedSidebarWidth && !isNaN(savedSidebarWidth)) {
        const sw = Math.min(Math.max(parseInt(savedSidebarWidth, 10), 220), 550);
        document.documentElement.style.setProperty("--sidebar-width", `${sw}px`);
    }

    const savedInspectorWidth = localStorage.getItem("preferred_inspector_width");
    if (savedInspectorWidth && !isNaN(savedInspectorWidth)) {
        const iw = Math.min(Math.max(parseInt(savedInspectorWidth, 10), 240), 600);
        document.documentElement.style.setProperty("--inspector-width", `${iw}px`);
    }

    const savedSidebarCollapsed = localStorage.getItem("sidebar_collapsed") === "true";
    if (savedSidebarCollapsed && window.innerWidth > 768) {
        if (sidebar) sidebar.classList.add("collapsed");
        if (sidebarExpandFloatingBtn) sidebarExpandFloatingBtn.style.display = "inline-flex";
    }

    const savedInspectorCollapsed = localStorage.getItem("inspector_collapsed") === "true";
    if (savedInspectorCollapsed && graphInspector) {
        graphInspector.classList.add("collapsed");
        if (btnShowInspector) btnShowInspector.style.display = "inline-flex";
        if (inspectorResizer) inspectorResizer.style.display = "none";
    }

    // 2. Sidebar Toggle & Collapse Handlers
    window.toggleSidebar = function(forceState = null) {
        if (window.innerWidth <= 768) {
            // Mobile Drawer Toggle
            const isOpen = forceState !== null ? forceState : !sidebar.classList.contains("mobile-open");
            if (sidebar) sidebar.classList.toggle("mobile-open", isOpen);
            if (sidebarBackdrop) sidebarBackdrop.classList.toggle("active", isOpen);
        } else {
            // Desktop Collapse Toggle
            const shouldCollapse = forceState !== null ? !forceState : !sidebar.classList.contains("collapsed");
            if (sidebar) sidebar.classList.toggle("collapsed", shouldCollapse);
            if (sidebarExpandFloatingBtn) {
                sidebarExpandFloatingBtn.style.display = shouldCollapse ? "inline-flex" : "none";
            }
            localStorage.setItem("sidebar_collapsed", shouldCollapse ? "true" : "false");
            if (typeof resizeGraphCanvas === "function") {
                setTimeout(resizeGraphCanvas, 50);
            }
        }
    };

    window.closeMobileSidebar = function() {
        if (sidebar) sidebar.classList.remove("mobile-open");
        if (sidebarBackdrop) sidebarBackdrop.classList.remove("active");
    };

    if (sidebarToggleBtn) {
        sidebarToggleBtn.addEventListener("click", () => toggleSidebar());
    }

    if (sidebarCollapseBtn) {
        sidebarCollapseBtn.addEventListener("click", () => toggleSidebar(false));
    }

    if (sidebarExpandFloatingBtn) {
        sidebarExpandFloatingBtn.addEventListener("click", () => toggleSidebar(true));
    }

    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener("click", closeMobileSidebar);
    }

    // Keyboard shortcut: Ctrl+B / Cmd+B toggles sidebar
    window.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
            e.preventDefault();
            toggleSidebar();
        }
    });

    // 3. Draggable Sidebar Resizer Handle
    if (sidebarResizer && workspaceGrid) {
        let isResizingSidebar = false;

        const startSidebarDrag = (e) => {
            if (window.innerWidth <= 768) return;
            isResizingSidebar = true;
            document.body.classList.add("is-resizing-sidebar");
            sidebarResizer.classList.add("resizing");
            e.preventDefault();
        };

        const onSidebarDrag = (e) => {
            if (!isResizingSidebar) return;
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const gridLeft = workspaceGrid.getBoundingClientRect().left;
            const newWidth = Math.min(Math.max(clientX - gridLeft, 220), 550);
            document.documentElement.style.setProperty("--sidebar-width", `${newWidth}px`);
            if (typeof resizeGraphCanvas === "function") resizeGraphCanvas();
        };

        const stopSidebarDrag = () => {
            if (!isResizingSidebar) return;
            isResizingSidebar = false;
            document.body.classList.remove("is-resizing-sidebar");
            sidebarResizer.classList.remove("resizing");
            const currentW = getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width").trim();
            localStorage.setItem("preferred_sidebar_width", parseInt(currentW, 10));
            if (typeof resizeGraphCanvas === "function") resizeGraphCanvas();
        };

        sidebarResizer.addEventListener("mousedown", startSidebarDrag);
        sidebarResizer.addEventListener("touchstart", startSidebarDrag, { passive: false });

        window.addEventListener("mousemove", onSidebarDrag);
        window.addEventListener("touchmove", onSidebarDrag, { passive: false });

        window.addEventListener("mouseup", stopSidebarDrag);
        window.addEventListener("touchend", stopSidebarDrag);
    }

    // 4. Draggable Inspector Resizer Handle
    if (inspectorResizer && graphExplorerBody) {
        let isResizingInspector = false;

        const startInspectorDrag = (e) => {
            if (window.innerWidth <= 768) return;
            isResizingInspector = true;
            document.body.classList.add("is-resizing-inspector");
            inspectorResizer.classList.add("resizing");
            e.preventDefault();
        };

        const onInspectorDrag = (e) => {
            if (!isResizingInspector) return;
            const clientX = e.touches ? e.touches[0].clientX : e.clientX;
            const bodyRight = graphExplorerBody.getBoundingClientRect().right;
            const newWidth = Math.min(Math.max(bodyRight - clientX, 240), 600);
            document.documentElement.style.setProperty("--inspector-width", `${newWidth}px`);
            if (typeof resizeGraphCanvas === "function") resizeGraphCanvas();
        };

        const stopInspectorDrag = () => {
            if (!isResizingInspector) return;
            isResizingInspector = false;
            document.body.classList.remove("is-resizing-inspector");
            inspectorResizer.classList.remove("resizing");
            const currentW = getComputedStyle(document.documentElement).getPropertyValue("--inspector-width").trim();
            localStorage.setItem("preferred_inspector_width", parseInt(currentW, 10));
            if (typeof resizeGraphCanvas === "function") resizeGraphCanvas();
        };

        inspectorResizer.addEventListener("mousedown", startInspectorDrag);
        inspectorResizer.addEventListener("touchstart", startInspectorDrag, { passive: false });

        window.addEventListener("mousemove", onInspectorDrag);
        window.addEventListener("touchmove", onInspectorDrag, { passive: false });

        window.addEventListener("mouseup", stopInspectorDrag);
        window.addEventListener("touchend", stopInspectorDrag);
    }

    // 5. Inspector Drawer Collapsing & Expanding
    if (inspectorToggleBtn && graphInspector) {
        inspectorToggleBtn.addEventListener("click", () => {
            graphInspector.classList.add("collapsed");
            if (btnShowInspector) btnShowInspector.style.display = "inline-flex";
            if (inspectorResizer) inspectorResizer.style.display = "none";
            localStorage.setItem("inspector_collapsed", "true");
            if (typeof resizeGraphCanvas === "function") setTimeout(resizeGraphCanvas, 50);
        });
    }

    if (btnShowInspector && graphInspector) {
        btnShowInspector.addEventListener("click", () => {
            graphInspector.classList.remove("collapsed");
            btnShowInspector.style.display = "none";
            if (inspectorResizer && window.innerWidth > 768) {
                inspectorResizer.style.display = "flex";
            }
            localStorage.setItem("inspector_collapsed", "false");
            if (typeof resizeGraphCanvas === "function") setTimeout(resizeGraphCanvas, 50);
        });
    }
}

// Wire Event Listeners
document.addEventListener("DOMContentLoaded", () => {
    // Initialize Responsive Layout & Dynamic Resizers
    initResponsiveLayoutAndResizers();

    // Initial data load
    fetchHealth();
    loadCompanies();

    // Download button event bindings
    document.getElementById("btnDownloadPdf").addEventListener("click", () => triggerPdfDownload());
    document.getElementById("btnDownloadExcel").addEventListener("click", triggerExcelExport);
    document.getElementById("btnDownloadCsv").addEventListener("click", triggerCsvExport);
    document.getElementById("btnExportFinTable").addEventListener("click", triggerCsvExport);

    // Screener Modal bindings
    const btnOpenModal = document.getElementById("btnOpenScraperModal");
    if (btnOpenModal) btnOpenModal.addEventListener("click", openScreenerModal);

    const btnClose = document.getElementById("btnCloseModal");
    if (btnClose) btnClose.addEventListener("click", closeScreenerModal);

    const btnCancel = document.getElementById("btnCancelModal");
    if (btnCancel) btnCancel.addEventListener("click", closeScreenerModal);

    const screenerInput = document.getElementById("screenerSearchInput");
    if (screenerInput) {
        screenerInput.addEventListener("input", handleScreenerSearchInput);
        screenerInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                executeScreenerIngestion();
            }
        });
    }

    const btnIngest = document.getElementById("btnExecuteIngest");
    if (btnIngest) btnIngest.addEventListener("click", executeScreenerIngestion);

    // AI Ask bindings
    const btnAskAi = document.getElementById("btnAskAi");
    if (btnAskAi) {
        btnAskAi.addEventListener("click", () => submitAiQuestion());
    }

    const aiInput = document.getElementById("aiQuestionInput");
    if (aiInput) {
        aiInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                submitAiQuestion();
            }
        });
    }

    // Universal Dynamic Search with Live Screener suggestions
    initUniversalSearch();

    // Tab Navigation
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(tc => tc.classList.remove("active"));

            btn.classList.add("active");
            const targetTabId = btn.dataset.tab;
            const targetContent = document.getElementById(targetTabId);
            if (targetContent) {
                targetContent.classList.add("active");
            }

            if (targetTabId === "tab-graph-view") {
                // Ensure canvas is properly sized on tab reveal & wake simulation
                setTimeout(() => {
                    resizeGraphCanvas();
                    resetGraphCamera();
                    wakeGraphSimulation(0.6);
                }, 50);
            } else {
                // Pause background physics loop to maintain 60-120fps scrolling on main tabs
                stopGraphSimulation();
            }
        });
    });

    // Hero View Subgraph Button
    const btnHeroViewGraph = document.getElementById("btnHeroViewGraph");
    if (btnHeroViewGraph) {
        btnHeroViewGraph.addEventListener("click", () => {
            const graphTabBtn = document.querySelector('[data-tab="tab-graph-view"]');
            if (graphTabBtn) graphTabBtn.click();
        });
    }

    // Embedded Graph Quick Search
    const embeddedSearch = document.getElementById("embeddedNodeSearch");
    if (embeddedSearch) {
        embeddedSearch.addEventListener("input", (e) => {
            const query = e.target.value.toLowerCase().trim();
            if (!query) return;
            const matched = simulationNodes.find(n => 
                (n.label && n.label.toLowerCase().includes(query)) || 
                (n.properties && n.properties.name && n.properties.name.toLowerCase().includes(query))
            );
            if (matched && graphCanvas) {
                selectedGraphNode = matched;
                inspectGraphNode(matched);
                const w = graphCanvas.width / (window.devicePixelRatio || 1);
                const h = graphCanvas.height / (window.devicePixelRatio || 1);
                graphCamera.x = -(matched.x - w / 2) * 1.5;
                graphCamera.y = -(matched.y - h / 2) * 1.5;
                graphCamera.zoom = 1.5;
            }
        });
    }

    // Initialize Knowledge Graph Explorer
    initKnowledgeGraphExplorer();
});

// ==============================================================================
// Interactive Knowledge Graph Explorer (Neo4j-Style Engine)
// ==============================================================================
let graphData = { nodes: [], edges: [] };
let simulationNodes = [];
let simulationEdges = [];
let graphCamera = { x: 0, y: 0, zoom: 1.0 };
let draggedNode = null;
let hoveredNode = null;
let selectedGraphNode = null;
let isPanningGraph = false;
let panStart = { x: 0, y: 0 };
let animFrameId = null;
let graphCanvas = null;
let graphCtx = null;

async function loadKnowledgeGraph(companyId = null) {
    const badge = document.getElementById("graphStatsBadge");
    if (badge) badge.textContent = "Loading Graph...";

    try {
        const url = companyId ? `/api/graph/${companyId}?format=json` : "/api/graph?format=json";
        const res = await fetch(url, { headers: { "Accept": "application/json" } });
        if (!res.ok) throw new Error("Could not fetch graph data");
        graphData = await res.json();

        setupGraphSimulation(graphData.nodes, graphData.edges);

        if (badge && graphData.summary) {
            badge.textContent = `${graphData.summary.total_nodes} Nodes • ${graphData.summary.total_edges} Relationships`;
        }
        const navPill = document.getElementById("navGraphPill");
        if (navPill && graphData.summary) {
            navPill.textContent = `${graphData.summary.total_nodes} Nodes`;
        }
    } catch (err) {
        console.error("Failed to load knowledge graph:", err);
        if (badge) badge.textContent = "Graph Error";
    }
}

function setupGraphSimulation(nodes, edges) {
    const width = graphCanvas ? graphCanvas.width / (window.devicePixelRatio || 1) : 800;
    const height = graphCanvas ? graphCanvas.height / (window.devicePixelRatio || 1) : 520;
    const centerX = width / 2;
    const centerY = height / 2;

    // Create a node map for edge lookup
    const nodeMap = new Map();
    simulationNodes = nodes.map((n, idx) => {
        // Distribute initial positions radially around center
        const isDoc = n.type === "document" || (n.id && n.id.startsWith("doc_"));
        const angle = (idx / Math.max(nodes.length, 1)) * 2 * Math.PI;
        const radius = n.type === "company" ? 0 : (isDoc ? 110 : 190);
        const nodeObj = {
            ...n,
            x: centerX + radius * Math.cos(angle) + (Math.random() - 0.5) * 30,
            y: centerY + radius * Math.sin(angle) + (Math.random() - 0.5) * 30,
            vx: 0,
            vy: 0,
        };
        nodeMap.set(n.id, nodeObj);
        return nodeObj;
    });

    simulationEdges = edges.map(e => ({
        ...e,
        sourceNode: nodeMap.get(e.source),
        targetNode: nodeMap.get(e.target),
    })).filter(e => e.sourceNode && e.targetNode);

    // Auto-select company node if available
    const compNode = simulationNodes.find(n => n.type === "company");
    if (compNode) {
        inspectGraphNode(compNode);
    }

    resetGraphCamera();
}

function initKnowledgeGraphExplorer() {
    graphCanvas = document.getElementById("knowledgeGraphCanvas");
    if (!graphCanvas) return;
    graphCtx = graphCanvas.getContext("2d");

    resizeGraphCanvas();
    window.addEventListener("resize", resizeGraphCanvas);

    // Dynamic Container ResizeObserver for Splitter Dragging & Viewport Changes
    const canvasWrapper = document.querySelector(".canvas-wrapper");
    if (canvasWrapper && window.ResizeObserver) {
        const resizeObs = new ResizeObserver(() => {
            resizeGraphCanvas();
        });
        resizeObs.observe(canvasWrapper);
    }

    // Canvas Mouse Events for Drag, Pan & Click (Scoped to canvas, not spamming window)
    graphCanvas.addEventListener("mousedown", onGraphMouseDown);
    graphCanvas.addEventListener("mousemove", onGraphMouseMove);
    window.addEventListener("mousemove", (e) => {
        if (draggedNode || isPanningGraph) {
            onGraphMouseMove(e);
        }
    });
    window.addEventListener("mouseup", onGraphMouseUp);
    graphCanvas.addEventListener("wheel", onGraphWheel, { passive: false });

    // Canvas Touch Events for Mobile / Tablet Pan & Drag
    graphCanvas.addEventListener("touchstart", (e) => {
        if (e.touches.length === 1) {
            const touch = e.touches[0];
            const worldPos = screenToWorld(touch.clientX, touch.clientY);
            const clicked = findNodeAt(worldPos.x, worldPos.y);
            if (clicked) {
                draggedNode = clicked;
                selectedGraphNode = clicked;
                inspectGraphNode(clicked);
                wakeGraphSimulation(0.5);
            } else {
                isPanningGraph = true;
                panStart = { x: touch.clientX - graphCamera.x, y: touch.clientY - graphCamera.y };
                wakeGraphSimulation(0.3);
            }
        }
    }, { passive: true });

    window.addEventListener("touchmove", (e) => {
        if (e.touches.length === 1) {
            const touch = e.touches[0];
            if (draggedNode) {
                const worldPos = screenToWorld(touch.clientX, touch.clientY);
                draggedNode.x = worldPos.x;
                draggedNode.y = worldPos.y;
                draggedNode.vx = 0;
                draggedNode.vy = 0;
                wakeGraphSimulation(0.3);
            } else if (isPanningGraph) {
                graphCamera.x = touch.clientX - panStart.x;
                graphCamera.y = touch.clientY - panStart.y;
                wakeGraphSimulation(0.3);
            }
        }
    }, { passive: true });

    window.addEventListener("touchend", () => {
        draggedNode = null;
        isPanningGraph = false;
    });

    // Controls
    const btnReset = document.getElementById("btnResetGraphLayout");
    if (btnReset) btnReset.addEventListener("click", () => {
        resetGraphCamera();
        wakeGraphSimulation(0.4);
    });

    const btnZoomIn = document.getElementById("btnZoomInGraph");
    if (btnZoomIn) btnZoomIn.addEventListener("click", () => {
        graphCamera.zoom = Math.min(graphCamera.zoom * 1.25, 3.0);
        wakeGraphSimulation(0.3);
    });

    const btnZoomOut = document.getElementById("btnZoomOutGraph");
    if (btnZoomOut) btnZoomOut.addEventListener("click", () => {
        graphCamera.zoom = Math.max(graphCamera.zoom / 1.25, 0.3);
        wakeGraphSimulation(0.3);
    });

    const btnAskNode = document.getElementById("btnAskAboutNode");
    if (btnAskNode) {
        btnAskNode.addEventListener("click", () => {
            if (!selectedGraphNode) return;
            const q = `Explain the ${selectedGraphNode.type} "${selectedGraphNode.label}" and its financial implications from the verified Knowledge Graph.`;
            submitAiQuestion(q);
        });
    }

    // Graph simulation is dormant until the user switches to the Knowledge Graph tab
}

function resizeGraphCanvas() {
    if (!graphCanvas) return;
    const parent = graphCanvas.parentElement;
    if (!parent) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = parent.getBoundingClientRect();
    const w = rect.width || 800;
    const h = rect.height || 520;

    graphCanvas.width = w * dpr;
    graphCanvas.height = h * dpr;
    graphCanvas.style.width = `${w}px`;
    graphCanvas.style.height = `${h}px`;

    if (graphCtx) {
        graphCtx.setTransform(1, 0, 0, 1, 0, 0);
        graphCtx.scale(dpr, dpr);
    }
}

function resetGraphCamera() {
    if (!graphCanvas) return;
    const w = graphCanvas.width / (window.devicePixelRatio || 1);
    const h = graphCanvas.height / (window.devicePixelRatio || 1);
    graphCamera = { x: 0, y: 0, zoom: 1.0 };
}

function screenToWorld(clientX, clientY) {
    const rect = graphCanvas.getBoundingClientRect();
    const mouseX = clientX - rect.left;
    const mouseY = clientY - rect.top;
    const w = rect.width;
    const h = rect.height;

    // Center offset + pan + zoom
    const worldX = (mouseX - w / 2 - graphCamera.x) / graphCamera.zoom + w / 2;
    const worldY = (mouseY - h / 2 - graphCamera.y) / graphCamera.zoom + h / 2;
    return { x: worldX, y: worldY };
}

function findNodeAt(worldX, worldY) {
    for (let i = simulationNodes.length - 1; i >= 0; i--) {
        const node = simulationNodes[i];
        const dx = node.x - worldX;
        const dy = node.y - worldY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist <= node.size + 4) {
            return node;
        }
    }
    return null;
}

function onGraphMouseDown(e) {
    if (e.button !== 0) return; // Only left click
    const worldPos = screenToWorld(e.clientX, e.clientY);
    const clicked = findNodeAt(worldPos.x, worldPos.y);

    if (clicked) {
        draggedNode = clicked;
        selectedGraphNode = clicked;
        inspectGraphNode(clicked);
    } else {
        isPanningGraph = true;
        panStart = { x: e.clientX - graphCamera.x, y: e.clientY - graphCamera.y };
    }
}

function onGraphMouseMove(e) {
    const rect = graphCanvas ? graphCanvas.getBoundingClientRect() : null;
    if (!rect) return;

    if (draggedNode) {
        const worldPos = screenToWorld(e.clientX, e.clientY);
        draggedNode.x = worldPos.x;
        draggedNode.y = worldPos.y;
        draggedNode.vx = 0;
        draggedNode.vy = 0;
        return;
    }

    if (isPanningGraph) {
        graphCamera.x = e.clientX - panStart.x;
        graphCamera.y = e.clientY - panStart.y;
        return;
    }

    // Hover detection
    if (e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
        const worldPos = screenToWorld(e.clientX, e.clientY);
        const hit = findNodeAt(worldPos.x, worldPos.y);
        if (hit !== hoveredNode) {
            hoveredNode = hit;
            graphCanvas.style.cursor = hit ? "pointer" : "grab";
        }
    } else {
        hoveredNode = null;
    }
}

function onGraphMouseUp() {
    draggedNode = null;
    isPanningGraph = false;
    if (graphCanvas) {
        graphCanvas.style.cursor = hoveredNode ? "pointer" : "grab";
    }
}

function onGraphWheel(e) {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.12 : 0.89;
    const newZoom = Math.min(Math.max(graphCamera.zoom * zoomFactor, 0.35), 2.8);
    graphCamera.zoom = newZoom;
}

// Inspect Node in Right Drawer
function inspectGraphNode(node) {
    selectedGraphNode = node;
    const badge = document.getElementById("inspectorBadge");
    const title = document.getElementById("inspectorTitle");
    const body = document.getElementById("inspectorBody");
    const actions = document.getElementById("inspectorActions");
    const graphInspector = document.getElementById("graphInspector");
    const btnShowInspector = document.getElementById("btnShowInspector");
    const inspectorResizer = document.getElementById("inspectorResizer");

    if (!node) return;

    // Auto-reveal inspector if it was collapsed
    if (graphInspector && graphInspector.classList.contains("collapsed")) {
        graphInspector.classList.remove("collapsed");
        if (btnShowInspector) btnShowInspector.style.display = "none";
        if (inspectorResizer && window.innerWidth > 768) inspectorResizer.style.display = "flex";
        localStorage.setItem("inspector_collapsed", "false");
        if (typeof resizeGraphCanvas === "function") setTimeout(resizeGraphCanvas, 50);
    }

    if (badge) {
        badge.textContent = node.type.toUpperCase().replace("_", " ");
        badge.style.color = node.color;
        badge.style.borderColor = node.color;
    }

    if (title) {
        title.textContent = node.label;
    }

    if (actions) {
        actions.style.display = "block";
    }

    if (body) {
        const props = node.properties || {};
        const propRows = Object.entries(props).map(([k, v]) => `
            <tr>
                <td class="inspector-key">${k}:</td>
                <td class="inspector-val">${v}</td>
            </tr>
        `).join("");

        // Find connected edges
        const connectedEdges = simulationEdges.filter(e => e.source === node.id || e.target === node.id);
        const relItems = connectedEdges.map(e => {
            const isSource = e.source === node.id;
            const otherNode = isSource ? e.targetNode : e.sourceNode;
            const arrow = isSource ? "──[" + e.label + "]──▶" : "◀──[" + e.label + "]──";
            return `
                <div class="inspector-rel-item">
                    <span>${arrow}</span>
                    <strong style="color:${otherNode.color}">${otherNode.label}</strong>
                </div>
            `;
        }).join("");

        body.innerHTML = `
            <table class="inspector-table">
                <tbody>${propRows}</tbody>
            </table>
            <div style="margin-top:14px;">
                <span style="font-size:0.75rem; font-weight:600; text-transform:uppercase; color:var(--text-muted);">Relationships (${connectedEdges.length}):</span>
                <div class="inspector-rel-list">${relItems || '<span style="font-size:0.8rem; color:var(--text-dim);">No direct connections</span>'}</div>
            </div>
        `;
    }
}

/// Force-Directed Physics & Canvas Render Loop with Auto-Sleep
let isSimulationRunning = false;
let embeddedSimAlpha = 1.0;

function stopGraphSimulation() {
    isSimulationRunning = false;
    if (animFrameId) {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
    }
}

function wakeGraphSimulation(alpha = 0.6) {
    embeddedSimAlpha = Math.max(embeddedSimAlpha, alpha);
    const graphTab = document.getElementById("tab-graph-view");
    if (!graphTab || !graphTab.classList.contains("active")) {
        return; // Never run physics if graph tab is not active!
    }
    if (!isSimulationRunning) {
        isSimulationRunning = true;
        animFrameId = requestAnimationFrame(stepGraphSimulation);
    }
}

function stepGraphSimulation() {
    const graphTab = document.getElementById("tab-graph-view");
    if (!graphTab || !graphTab.classList.contains("active")) {
        stopGraphSimulation();
        return;
    }

    updatePhysics();
    renderGraphCanvas();

    // Decay alpha smoothly
    embeddedSimAlpha *= 0.985;

    // Sleep when settled and no active mouse drag/pan
    if (embeddedSimAlpha < 0.005 && !draggedNode && !isPanningGraph) {
        stopGraphSimulation();
        renderGraphCanvas();
        return;
    }

    animFrameId = requestAnimationFrame(stepGraphSimulation);
}

function updatePhysics() {
    if (!simulationNodes.length || embeddedSimAlpha <= 0.003) return;
    const width = graphCanvas ? graphCanvas.width / (window.devicePixelRatio || 1) : 800;
    const height = graphCanvas ? graphCanvas.height / (window.devicePixelRatio || 1) : 520;
    const centerX = width / 2;
    const centerY = height / 2;

    const repulsionK = 2800;
    const springK = 0.04;
    const targetDist = 95;
    const damping = 0.82;

    // 1. Repulsion between all node pairs (Coulomb) with safe distance & force clamping
    for (let i = 0; i < simulationNodes.length; i++) {
        const n1 = simulationNodes[i];
        for (let j = i + 1; j < simulationNodes.length; j++) {
            const n2 = simulationNodes[j];
            const dx = n2.x - n1.x;
            const dy = n2.y - n1.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            if (dist < 240) {
                const safeDist = Math.max(dist, 25);
                const force = Math.min(repulsionK / (safeDist * safeDist), 4.5) * embeddedSimAlpha;
                const fx = (dx / dist) * force;
                const fy = (dy / dist) * force;
                if (n1 !== draggedNode) { n1.vx -= fx; n1.vy -= fy; }
                if (n2 !== draggedNode) { n2.vx += fx; n2.vy += fy; }
            }
        }
    }

    // 2. Spring attraction along edges (Hooke) with force clamping
    for (const edge of simulationEdges) {
        const n1 = edge.sourceNode;
        const n2 = edge.targetNode;
        if (!n1 || !n2) continue;

        const dx = n2.x - n1.x;
        const dy = n2.y - n1.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = Math.max(-5, Math.min(5, (dist - targetDist) * springK)) * embeddedSimAlpha;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (n1 !== draggedNode) { n1.vx -= fx; n1.vy -= fy; }
        if (n2 !== draggedNode) { n2.vx += fx; n2.vy += fy; }
    }

    // 3. Center gravity & velocity damping + radial soft bound
    const maxBoundR = Math.max(width, height) * 0.85;
    for (const n of simulationNodes) {
        if (n === draggedNode) continue;
        n.vx += (centerX - n.x) * 0.002 * embeddedSimAlpha;
        n.vy += (centerY - n.y) * 0.002 * embeddedSimAlpha;

        // Apply velocity clamping & damping
        n.vx = Math.max(-8, Math.min(8, n.vx * damping));
        n.vy = Math.max(-8, Math.min(8, n.vy * damping));
        n.x += n.vx;
        n.y += n.vy;

        // Soft radial bound
        const dCenter = Math.hypot(n.x - centerX, n.y - centerY);
        if (dCenter > maxBoundR) {
            const ratio = maxBoundR / dCenter;
            n.x = centerX + (n.x - centerX) * ratio;
            n.y = centerY + (n.y - centerY) * ratio;
            n.vx *= 0.5;
            n.vy *= 0.5;
        }
    }
}

function renderGraphCanvas() {
    if (!graphCtx || !graphCanvas) return;
    const w = graphCanvas.width / (window.devicePixelRatio || 1);
    const h = graphCanvas.height / (window.devicePixelRatio || 1);

    graphCtx.save();
    graphCtx.clearRect(0, 0, w, h);

    // Apply Camera Transform (Center + Pan + Zoom)
    graphCtx.translate(w / 2 + graphCamera.x, h / 2 + graphCamera.y);
    graphCtx.scale(graphCamera.zoom, graphCamera.zoom);
    graphCtx.translate(-w / 2, -h / 2);

    const activeNode = hoveredNode || selectedGraphNode;

    // 1. Draw Edges
    for (const edge of simulationEdges) {
        const n1 = edge.sourceNode;
        const n2 = edge.targetNode;
        if (!n1 || !n2) continue;

        const isConnected = activeNode && (activeNode.id === n1.id || activeNode.id === n2.id);
        const isDimmed = activeNode && !isConnected;

        graphCtx.beginPath();
        graphCtx.moveTo(n1.x, n1.y);
        graphCtx.lineTo(n2.x, n2.y);

        if (isConnected) {
            graphCtx.strokeStyle = "rgba(6, 182, 212, 0.85)";
            graphCtx.lineWidth = 2.4;
            graphCtx.shadowColor = "#06b6d4";
            graphCtx.shadowBlur = 8;
        } else if (isDimmed) {
            graphCtx.strokeStyle = "rgba(255, 255, 255, 0.06)";
            graphCtx.lineWidth = 1.0;
            graphCtx.shadowBlur = 0;
        } else {
            graphCtx.strokeStyle = "rgba(255, 255, 255, 0.18)";
            graphCtx.lineWidth = 1.4;
            graphCtx.shadowBlur = 0;
        }
        graphCtx.stroke();
        graphCtx.shadowBlur = 0;

        // Draw Relationship Label at midpoint
        if (isConnected || graphCamera.zoom > 0.85) {
            const midX = (n1.x + n2.x) / 2;
            const midY = (n1.y + n2.y) / 2;
            graphCtx.font = "9px Inter, sans-serif";
            graphCtx.textAlign = "center";
            graphCtx.textBaseline = "middle";

            const textWidth = graphCtx.measureText(edge.label).width;
            graphCtx.fillStyle = "rgba(8, 12, 20, 0.85)";
            graphCtx.fillRect(midX - textWidth / 2 - 3, midY - 6, textWidth + 6, 12);

            graphCtx.fillStyle = isConnected ? "#06b6d4" : "rgba(148, 163, 184, 0.8)";
            graphCtx.fillText(edge.label, midX, midY);
        }
    }

    // 2. Draw Nodes
    for (const node of simulationNodes) {
        const isSelected = selectedGraphNode && selectedGraphNode.id === node.id;
        const isHovered = hoveredNode && hoveredNode.id === node.id;
        const isConnected = activeNode && (activeNode.id === node.id || simulationEdges.some(e => 
            (e.source === activeNode.id && e.target === node.id) || 
            (e.target === activeNode.id && e.source === node.id)
        ));
        const isDimmed = activeNode && !isConnected;

        graphCtx.save();
        if (isDimmed) {
            graphCtx.globalAlpha = 0.35;
        }

        // Outer Glow Halo for selected or hovered
        if (isSelected || isHovered) {
            graphCtx.beginPath();
            graphCtx.arc(node.x, node.y, node.size + 8, 0, 2 * Math.PI);
            graphCtx.fillStyle = node.color + "33";
            graphCtx.fill();
        }

        // Main Node Circle
        graphCtx.beginPath();
        graphCtx.arc(node.x, node.y, node.size, 0, 2 * Math.PI);
        graphCtx.fillStyle = node.color;
        graphCtx.shadowColor = node.color;
        graphCtx.shadowBlur = isSelected ? 18 : (isHovered ? 12 : 6);
        graphCtx.fill();
        graphCtx.shadowBlur = 0;

        // Inner Circle Border
        graphCtx.lineWidth = isSelected ? 3 : 2;
        graphCtx.strokeStyle = "#ffffff";
        graphCtx.stroke();

        // Node Label Pill below circle
        graphCtx.font = "bold 11px Inter, sans-serif";
        graphCtx.textAlign = "center";
        const labelText = node.label;
        const labelW = graphCtx.measureText(labelText).width;
        const pillY = node.y + node.size + 6;

        graphCtx.fillStyle = "rgba(8, 12, 20, 0.88)";
        graphCtx.fillRect(node.x - labelW / 2 - 6, pillY, labelW + 12, 16);
        graphCtx.strokeStyle = isSelected ? node.color : "rgba(255, 255, 255, 0.12)";
        graphCtx.lineWidth = 1;
        graphCtx.strokeRect(node.x - labelW / 2 - 6, pillY, labelW + 12, 16);

        graphCtx.fillStyle = isSelected ? "#ffffff" : "#f1f5f9";
        graphCtx.fillText(labelText, node.x, pillY + 12);

        graphCtx.restore();
    }

    graphCtx.restore();
}

