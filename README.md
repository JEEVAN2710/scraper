# Financial Document Automation & AI Intelligence Suite

[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-4479A1.svg)](https://www.mysql.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Phi--3%20Mini-orange.svg)](https://ollama.ai/)
[![Cytoscape.js](https://img.shields.io/badge/Cytoscape.js-3.28+-E53E3E.svg)](https://js.cytoscape.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A privacy-respecting, production-grade financial document automation, knowledge graph indexing, and AI research assistant. The suite combines **live web scraping of financial portals (Screener.in)**, **automated downloading and deduplication of official BSE/NSE PDF filings and quarterly earnings concall transcripts**, **PyPDF text extraction & sliding-window chunking**, **heuristic risk disclosure & strategic guidance extraction**, **normalized relational MySQL persistence**, **in-memory Knowledge Graph graphification**, and **grounded Graph RAG (Retrieval-Augmented Generation) powered by local Ollama LLMs**.

Designed specifically for **consumer-tier desktop hardware** (Windows 11, Intel Core i3 12th-Gen, 16 GB RAM, integrated graphics) without requiring dedicated GPUs, expensive cloud APIs, Docker containers, or bloated orchestration frameworks.

---

## Table of Contents

1. [High-Level Architecture & End-to-End Pipeline](#high-level-architecture--end-to-end-pipeline)
2. [Key Features](#key-features)
3. [Complete Directory & File Structure](#complete-directory--file-structure)
4. [Relational Database Schema (MySQL)](#relational-database-schema-mysql)
5. [Knowledge Graph & Graphify Engine](#knowledge-graph--graphify-engine)
6. [Graph RAG & Humanized AI Assistant](#graph-rag--humanized-ai-assistant)
7. [Interactive Frontend & Graph Explorer](#interactive-frontend--graph-explorer)
8. [Installation & Quick Start Guide](#installation--quick-start-guide)
9. [CLI Management Tool (`run.py`)](#cli-management-tool-runpy)
10. [REST API Reference](#rest-api-reference)
11. [Developer Guide: How to Make Changes](#developer-guide-how-to-make-changes)
    - [1. Adding a New Data Source / Scraper](#1-adding-a-new-data-source--scraper)
    - [2. Adding New Financial Metrics or Ratios](#2-adding-new-financial-metrics-or-ratios)
    - [3. Switching or Customizing the LLM Provider](#3-switching-or-customizing-the-llm-provider)
    - [4. Customizing Graph RAG Prompts](#4-customizing-graph-rag-prompts)
    - [5. Adding New Knowledge Graph Nodes & Edges](#5-adding-new-knowledge-graph-nodes--edges)
    - [6. Customizing the Frontend UI & Styling](#6-customizing-the-frontend-ui--styling)
    - [7. Modifying Database Schema & Migrations](#7-modifying-database-schema--migrations)
12. [Testing & Quality Assurance](#testing--quality-assurance)
13. [Troubleshooting & FAQ](#troubleshooting--faq)

---

## High-Level Architecture & End-to-End Pipeline

```
                                    USER SEARCH QUERY
                             (e.g., "Reliance", "Tata Motors", "TCS")
                                           │
                                           ▼
                            ┌──────────────────────────────┐
                            │    Screener.in Live API      │
                            │  /api/company/search/?q=...  │
                            └──────────────┬───────────────┘
                                           │ Resolves Ticker & Path
                                           ▼
                            ┌──────────────────────────────┐
                            │    ScreenerScraper (HTTPX)   │
                            │  • #top-ratios (P/E, ROCE)   │
                            │  • .about (Description)      │
                            │  • #profit-loss (Multi-year) │
                            │  • #quarters (Recent Q1-Q4)  │
                            │  • Official PDF Link Finder  │
                            └──────┬───────────────┬───────┘
                                   │               │
                 Official Report / │               │ Financial Data &
                 BSE Concall Links │               │ Key Ratios JSON
                                   ▼               │
               ┌──────────────────────────────┐    │
               │      PDF Downloader          │    │
               │  • HTTP Stream & Save        │    │
               │  • SHA-256 Deduplication     │    │
               └──────────────┬───────────────┘    │
                              │                    │
                              ▼                    │
               ┌──────────────────────────────┐    │
               │    PyPDF Extractor & Chunker │    │
               │  • Page-by-page text extract │    │
               │  • 1000-char sliding window  │    │
               │  • Risk regex classification │    │
               └──────────────┬───────────────┘    │
                              │                    │
                              ▼                    ▼
               ┌──────────────────────────────────────────────────┐
               │              MySQL 8.0 Storage Layer             │
               │  • companies        • documents                  │
               │  • financial_data   • risk_factors               │
               │  • document_chunks  • processing_logs            │
               └──────────────────────┬───────────────────────────┘
                                      │
                                      ▼
               ┌──────────────────────────────────────────────────┐
               │           Graphifier & Knowledge Graph           │
               │  • O(1) in-memory neighborhood traversal         │
               │  • Node Types: Company, Doc, Metric, Risk, Guide │
               │  • Pre-indexed Concall Guidance Triples          │
               │  • Persisted as data/knowledge_graph.json        │
               └──────────────┬────────────────────┬──────────────┘
                              │                    │
                              ▼                    ▼
               ┌────────────────────────┐  ┌────────────────────────┐
               │    Graph RAG Engine    │  │ Cytoscape Explorer UI  │
               │  • Traverses Subgraph  │  │  • Interactive Physics │
               │  • Exact Page Citations│  │  • Filter Chips        │
               │  • Ollama Phi-3 Mini   │  │  • Node Inspector      │
               └──────────────┬─────────┘  └────────────────────────┘
                              │
                              ▼
               ┌──────────────────────────────────────────────────┐
               │             Obsidian-Glassmorphic UI             │
               │  • Live debounced search & autocomplete dropdown │
               │  • Multi-stage extraction progress banner        │
               │  • KPI ribbon, Quarterly table, Risk badges      │
               │  • Chat Assistant with clickable citations       │
               │  • Multi-sheet Excel (.xlsx) & CSV export        │
               └──────────────────────────────────────────────────┘
```

---

## Key Features

1. **Universal Indian Equity Discovery**: Search *any* Indian publicly listed company by name or ticker (e.g., `Reliance`, `Tata Motors`, `Infosys`, `Zomato`, `Adani`). The system queries Screener.in live and resolves ticker endpoints automatically.
2. **Comprehensive Financial Parsing**: Scrapes company business overview, key valuation ratios (Market Cap, P/E, Book Value, Dividend Yield, ROCE, ROE, High/Low), strengths/weaknesses (Pros & Cons), multi-year annual P&L statements, and recent quarterly results.
3. **Official PDF Filings & Concall Transcripts**: Automatically discovers and downloads the latest official Annual Report PDF and BSE India quarterly earnings concall transcripts.
4. **Cryptographic Deduplication**: Computes SHA-256 fingerprints before processing to avoid redundant network transfers and repetitive parsing.
5. **Heuristic Text Extraction & Chunking**: Extracts text from PDF pages, performs sliding-window chunking (1000 chars, 150-char overlap) for precision citations, and extracts categorized risk disclosures with page citations.
6. **Queryless In-Memory Knowledge Graph**: Translates relational data and concall commentary into semantic triples without slow, brittle SQL `LIKE` queries or vector index overhead.
7. **Graph RAG (Retrieval-Augmented Generation)**: Grounded question-answering with exact document filenames and page citations, utilizing local **Ollama Microsoft Phi-3** (with deterministic direct graph synthesis as offline fallback).
8. **Export Suite**: One-click download of the raw filing PDF, a 4-sheet formatted Excel workbook (`.xlsx`) with styling and PDF text chunks, and standard financial CSVs.
9. **Dual UI Experience**:
   - Modern glassmorphic analytics dashboard (`index.html`) with interactive KPI cards and AI chat.
   - Dedicated fullscreen Neo4j-style interactive Knowledge Graph Visualizer (`graph.html`) powered by Cytoscape.js with physics layouts, category filters, and node inspectors.

---

## Complete Directory & File Structure

```
d:\scraper\
│
├── app/                                # Core Application Package
│   ├── __init__.py                     # Package marker
│   ├── main.py                         # FastAPI application entrypoint & static route mounting
│   │
│   ├── config/                         # Configuration Layer
│   │   ├── __init__.py
│   │   └── settings.py                 # Pydantic BaseSettings, .env loader, directory bootstrap
│   │
│   ├── scraper/                        # Web Scraping Engine
│   │   ├── __init__.py
│   │   ├── base.py                     # BaseScraper abstract base class
│   │   └── screener_scraper.py         # Screener.in search API, HTML parsing, PDF download engine
│   │
│   ├── extraction/                     # Document Processing Engine
│   │   ├── __init__.py
│   │   └── pdf_extractor.py            # PyPDF text extraction, SHA-256 hashing, chunker & risk regex
│   │
│   ├── database/                       # MySQL Relational Storage Layer
│   │   ├── __init__.py
│   │   ├── connection.py               # DatabaseManager singleton, pooling, health checks
│   │   ├── repositories.py             # Anti-SQLi parameterized CRUD repositories
│   │   └── migrations/                 # Schema & Versioning
│   │       ├── __init__.py
│   │       ├── runner.py               # Migration execution engine
│   │       └── schema.sql              # 6 normalized table DDL definitions
│   │
│   ├── pipeline/                       # Orchestration, Graph & RAG Engines
│   │   ├── __init__.py
│   │   ├── graphify.py                 # In-memory Knowledge Graph indexer & concall semantic extractor
│   │   ├── graph_rag.py                # Graph RAG engine, subgraph traversal, citation builder
│   │   └── ingestion_pipeline.py       # Orchestrator: Scrape -> Download -> Extract -> MySQL -> Graph
│   │
│   ├── llm/                            # Local LLM Integration
│   │   ├── __init__.py
│   │   ├── base.py                     # LLMProvider abstract interface
│   │   ├── ollama_client.py            # Local Ollama client (HTTP REST API with health check)
│   │   └── prompts.py                  # Structured extraction & executive Graph RAG prompts
│   │
│   ├── api/                            # REST API Endpoints & Schemas
│   │   ├── __init__.py
│   │   ├── models.py                   # Pydantic v2 request/response schemas
│   │   └── routes.py                   # FastAPI route definitions (companies, documents, ask, exports)
│   │
│   └── export/                         # Report Generators
│       ├── __init__.py
│       └── excel_exporter.py           # Multi-sheet openpyxl Excel & CSV generator
│
├── frontend/                           # Presentation Layer (Vanilla JS, CSS3, HTML5)
│   ├── index.html                      # Glassmorphic main analytics dashboard
│   ├── graph.html                      # Dedicated fullscreen Neo4j-style Knowledge Graph Visualizer
│   ├── app.js                          # Client-side state manager, debounced search, RAG chat controller
│   └── style.css                       # Responsive glassmorphism styling, animations & badges
│
├── data/                               # Local File Storage (Git-ignored)
│   ├── downloads/                      # Downloaded Annual Report & Concall PDFs
│   ├── processed/                      # Extracted texts & knowledge_graph.json
│   └── exports/                        # Generated Excel workbooks and CSV files
│
├── logs/                               # Runtime Audit Logs
│   └── app.log                         # Daily rotating application log
│
├── tests/                              # Pytest Automated Test Suite
│   ├── __init__.py
│   ├── test_config.py                  # Tests for settings and path validation
│   ├── test_database.py                # Unit tests for schema, connection pool & repositories
│   ├── test_screener_scraper.py        # Tests for Screener search API, HTML parsing & ratios
│   ├── test_screener_api.py            # Integration tests for /api/scrape endpoints
│   ├── test_pdf_extractor.py           # Tests for PyPDF extraction, chunking & SHA-256
│   ├── test_graphify.py                # Tests for Knowledge Graph node/edge indexing & serialization
│   └── test_api_and_export.py          # REST endpoints, Graph RAG & Excel export tests
│
├── .env.example                        # Template environment variables
├── .env                                # Active local environment configuration
├── .gitignore                          # Version control exclusions
├── requirements.txt                    # Project dependencies
├── run.py                              # Unified CLI management entrypoint
└── README.md                           # Master project documentation (this file)
```

---

## Relational Database Schema (MySQL)

The database `financial_ai` uses MySQL 8.0+ InnoDB tables with `utf8mb4` encoding:

### 1. `companies`
Stores the corporate entity, identity metadata, and parsed overview.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INT` | `AUTO_INCREMENT, PRIMARY KEY` | Internal unique company ID |
| `name` | `VARCHAR(255)` | `NOT NULL, INDEX` | Registered corporate name |
| `ticker` | `VARCHAR(50)` | `NULL, UNIQUE` | Stock ticker symbol (e.g., `RELIANCE`, `INFY`) |
| `website` | `VARCHAR(500)` | `NULL` | Official corporate or investor relations URL |
| `about` | `TEXT` | `NULL` | Business description and background overview |
| `sector` | `VARCHAR(255)` | `NULL` | Industry / peer sector classification |
| `ratios_json` | `JSON` | `NULL` | Structured key ratios (Market Cap, P/E, ROCE, ROE, etc.) |
| `created_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Entity registration timestamp |
| `updated_at` | `TIMESTAMP` | `ON UPDATE CURRENT_TIMESTAMP` | Last metadata refresh timestamp |

### 2. `documents`
Tracks all downloaded filings, reports, and concall transcripts with SHA-256 fingerprints.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INT` | `AUTO_INCREMENT, PRIMARY KEY` | Internal document ID |
| `company_id` | `INT` | `NOT NULL, FK -> companies(id)` | Cascading parent company link |
| `file_name` | `VARCHAR(500)` | `NOT NULL` | Local filename on disk |
| `file_url` | `VARCHAR(1000)` | `NULL` | Remote download origin URL |
| `local_path` | `VARCHAR(1000)` | `NOT NULL` | Local filesystem path under `data/downloads/` |
| `file_hash` | `VARCHAR(64)` | `NOT NULL, UNIQUE INDEX` | Cryptographic SHA-256 digest |
| `document_type` | `VARCHAR(100)` | `DEFAULT 'annual_report'` | Type: `annual_report` or `concall_transcript` |
| `report_period` | `VARCHAR(50)` | `NULL, INDEX` | Fiscal period (e.g., `FY2024`, `Q3-FY24`) |
| `report_date` | `DATE` | `NULL` | Filing publication date |
| `downloaded_at`| `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Download completion timestamp |
| `processed_at` | `TIMESTAMP` | `NULL` | Text extraction completion timestamp |
| `processing_status` | `ENUM` | `DEFAULT 'downloaded'` | `downloaded`, `extracting`, `extracted`, `chunked`, `analyzing`, `processed`, `failed` |

### 3. `financial_data`
Normalized historical and multi-year financial statements.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INT` | `AUTO_INCREMENT, PRIMARY KEY` | Metric row ID |
| `document_id` | `INT` | `NOT NULL, FK -> documents(id)`| Document provenance link |
| `company_id` | `INT` | `NOT NULL, FK -> companies(id)`| Owning company link |
| `period` | `VARCHAR(50)` | `NULL, INDEX` | Financial reporting period (e.g., `FY2024`) |
| `revenue` | `DECIMAL(20,4)`| `NULL` | Total Revenue / Sales |
| `revenue_growth` | `DECIMAL(10,4)` | `NULL` | YoY Revenue Growth rate (decimal, e.g. `0.155` = 15.5%) |
| `net_profit` | `DECIMAL(20,4)`| `NULL` | Net Profit After Tax |
| `profit_growth` | `DECIMAL(10,4)` | `NULL` | YoY Profit Growth rate |
| `operating_profit` | `DECIMAL(20,4)` | `NULL` | Operating Profit (EBITDA) |
| `operating_margin` | `DECIMAL(10,4)` | `NULL` | Operating Margin (decimal, e.g. `0.245` = 24.5%) |
| `eps` | `DECIMAL(10,4)`| `NULL` | Earnings Per Share |
| `total_assets` | `DECIMAL(20,4)`| `NULL` | Balance Sheet Total Assets |
| `total_liabilities`| `DECIMAL(20,4)`| `NULL` | Total Liabilities |
| `cash_flow` | `DECIMAL(20,4)`| `NULL` | Operating Cash Flow |
| `currency` | `VARCHAR(10)` | `DEFAULT 'INR'` | Reporting currency code |

### 4. `risk_factors`
Categorized risk disclosures extracted with page provenance.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INT` | `AUTO_INCREMENT, PRIMARY KEY` | Unique risk record ID |
| `document_id` | `INT` | `NOT NULL, FK -> documents(id)`| Filing document link |
| `company_id` | `INT` | `NOT NULL, FK -> companies(id)`| Company link |
| `risk` | `VARCHAR(255)` | `NOT NULL` | Standardized risk category or headline |
| `description` | `TEXT` | `NULL` | Contextual narrative extracted from the filing |
| `page_number` | `INT` | `NULL` | Exact PDF page number citation |

### 5. `document_chunks`
Sliding-window text chunks for textual evidence inspection and export.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INT` | `AUTO_INCREMENT, PRIMARY KEY` | Chunk record ID |
| `document_id` | `INT` | `NOT NULL, FK -> documents(id)`| Filing document link |
| `chunk_index` | `INT` | `NOT NULL, INDEX` | Sequential chunk index within the document |
| `page_start` | `INT` | `NOT NULL` | Beginning PDF page number |
| `page_end` | `INT` | `NOT NULL` | Ending PDF page number |
| `content` | `MEDIUMTEXT` | `NOT NULL` | Extracted text content |

### 6. `processing_logs`
Detailed audit log of every background ingestion and extraction stage.
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `INT` | `AUTO_INCREMENT, PRIMARY KEY` | Log entry ID |
| `document_id` | `INT` | `NULL, FK -> documents(id)` | Document associated (if any) |
| `stage` | `VARCHAR(100)` | `NOT NULL` | Pipeline stage (`download_and_hash`, `extraction`, etc.) |
| `status` | `ENUM` | `NOT NULL` | `started`, `success`, `warning`, `failed` |
| `message` | `TEXT` | `NULL` | Human-readable audit message |
| `error_details`| `MEDIUMTEXT` | `NULL` | Exception stack trace if failed |
| `started_at` | `TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` | Stage start time |
| `completed_at` | `TIMESTAMP` | `NULL` | Stage completion time |

---

## Knowledge Graph & Graphify Engine

Instead of relying on slow database queries, full-table scanning, or expensive vector databases, the suite features a custom **Knowledge Graph Engine** (`app/pipeline/graphify.py`).

### Node Types & Properties
The graph consists of 5 typed node classes:

1. **Company (`company`)**:
   - Color: `#f59e0b` (Amber) | Size: `28px`
   - Properties: `company_id`, `name`, `ticker`, `website`, `about`, `sector`, `ratios`
2. **Document (`document`)**:
   - Color: `#06b6d4` (Cyan for Annual Reports) / `#a855f7` (Purple for Concalls) | Size: `22px`
   - Properties: `document_id`, `file_name`, `document_type`, `period`, `file_hash`, `status`
3. **Financial Metric (`metric`)**:
   - Color: `#10b981` (Emerald) | Size: `18px`
   - Properties: `period`, `revenue`, `revenue_formatted`, `revenue_growth_pct`, `net_profit`, `operating_margin_pct`, `eps`, `currency`
4. **Risk Factor (`risk`)**:
   - Color: `#f43f5e` (Rose) | Size: `17px`
   - Properties: `risk_id`, `category`, `description`, `page_number`, `source_doc`
5. **Strategic Guidance (`guidance`)**:
   - Color: `#a855f7` (Purple) | Size: `18px`
   - Properties: `category`, `period`, `statement`, `source_doc`, `page`

### Directed Edge Relationships
Edges connect entities with precise semantic relationships:
- `(company) -[ANNUAL_FILING]-> (document)`
- `(company) -[CONCALL_FILED]-> (document)`
- `(company) -[REPORTED_FINANCIALS]-> (metric)`
- `(company) -[HAS_RISK]-> (risk)`
- `(company) -[MENTIONS_GUIDANCE]-> (guidance)`
- `(document) -[EVIDENCES]-> (metric)`
- `(document) -[CITES_P{page}]-> (risk)`
- `(document) -[CITES_{page}]-> (guidance)`

### Semantic Concall Guidance Extraction
Concall transcripts contain valuable forward-looking management commentary. The Graphifier applies domain heuristics across 5 strategic categories:
1. **CapEx & Capital Allocation**: Identifies capital expenditure commitments, outlay, and facility investments.
2. **Revenue & Margin Guidance**: Identifies forward guidance, growth targets, and expected margin trajectories.
3. **Capacity & Project Commissioning**: Identifies plant commissioning dates, commercial operations, and project pipeline timelines.
4. **Debt & Liquidity Strategy**: Identifies leverage targets, debt reduction plans, and refinancing initiatives.
5. **Strategic Order Book & Clients**: Identifies new client wins, contract backlogs, and order book metrics.

### Traversal Performance
- Inverted indexes (`_ticker_index`, `_name_index`, `_type_index`) enable **$O(1)$ entry-point lookups**.
- Forward and backward adjacency maps (`_adj_out`, `_adj_in`) enable **instant 1-hop and 2-hop neighborhood traversal** without executing any SQL queries.
- Persisted to disk as `data/processed/knowledge_graph.json` for rapid startup.

---

## Graph RAG & Humanized AI Assistant

The **Graph RAG Engine** (`app/pipeline/graph_rag.py`) bridges the Knowledge Graph with local LLM generation.

### How Graph RAG Operates:
1. **Target Resolution**: Analyzes the user's inquiry (e.g., *"What are Reliance's main risks and latest revenue?"*) and resolves target company nodes in the Knowledge Graph.
2. **Queryless Subgraph Traversal**: Traverses outgoing edges to pull financial metrics, risk factors, filings, and concall guidance into memory.
3. **Semantic Triples Formulation**: Formats the traversed graph into clean, structured facts containing exact PDF file names and page numbers:
   ```text
   ENTITY [Company]: Reliance Industries Ltd (Ticker: RELIANCE)
   RELATIONSHIPS [Reported Financial Metrics]:
   - (RELIANCE) -[IN_PERIOD FY2024]-> Revenue: ₹901064.0Cr (Growth: +2.6% YoY), Net Profit: ₹79020.0Cr, Margin: 19.8%, EPS: ₹102.50
   RELATIONSHIPS [Disclosed Risk Factors & Provenance]:
   - (RELIANCE) -[DISCLOSED_RISK]-> 'Supply Chain Volatility': Fluctuations in global crude benchmarks... [Source: RELIANCE_Annual_Report.pdf, Page 42]
   RELATIONSHIPS [Pre-Indexed Management Guidance & Concall Statements]:
   - (RELIANCE) -[GUIDANCE_CAPEX_&_CAPITAL_ALLOCATION Q3-FY24]-> "We expect capex intensity to moderate in the coming fiscal year." [Source: RELIANCE_Concall_Q3.pdf, Page 14]
   ```
4. **Local LLM Inference**: Sends the grounded prompt to **Ollama Phi-3 Mini** (`http://localhost:11434`) using an executive financial analyst persona.
5. **Offline Fallback Guarantee**: If Ollama is offline or times out, the engine invokes `_synthesize_direct_graph_answer()`, generating a deterministic, formatted response directly from the graph with 100% zero hallucination.

---

## Interactive Frontend & Graph Explorer

The presentation layer includes two synchronized user interfaces:

### 1. Main Glassmorphic Dashboard (`frontend/index.html`)
- **Universal Search**: Live debounced search input with auto-suggest dropdown. Search any company, click a match or press Enter, and watch the live extraction progress.
- **Extraction Progress Banner**: Real-time multi-stage visual indicator displaying progress from Screener search through PDF download, text extraction, risk discovery, and Knowledge Graph synchronization.
- **Company Profile Header**: Company name, ticker badge, official investor relations link, peer sector badge, and full business overview ("About").
- **Key Ratios Ribbon**: Market Cap, Stock P/E, Book Value, Dividend Yield, ROCE, ROE, High/Low, and Face Value.
- **Interactive KPI Cards**: Multi-year Revenue, Net Profit, Operating Margin, and EPS with YoY growth trend badges.
- **Quarterly Results Table**: Breakdown of recent quarterly Sales, Operating Profit, Margin %, Net Profit, and EPS.
- **Filing Documents & Chunks Explorer**: List of downloaded filings with SHA-256 hashes, status pills, direct PDF download buttons, and page text chunk preview.
- **AI Research Assistant**: Interactive chat interface with preset sample queries, typing indicators, and citations linked to document pages.
- **Export Actions**: Instant generation of formatted Excel workbooks (`.xlsx`) and CSV files.

### 2. Fullscreen Knowledge Graph Explorer (`frontend/graph.html` / `/graph`)
- Accessible via the top navbar **"Graph DB Visualizer"** button or by navigating directly to `http://localhost:8000/graph`.
- Built with **Cytoscape.js** with physics-based layout (`cose`), smooth pan/zoom controls, and node dragging.
- **Node Type Filter Chips**: Toggle visibility for Companies, Annual Reports, Concalls, Metrics, Risks, and Guidance.
- **Company Subgraph Focus**: Isolate any company to inspect its direct 1-hop and 2-hop neighborhood.
- **Node Inspector Drawer**: Click any node to open a sliding sidebar showing all extracted metadata, financial figures, exact page numbers, and linked source filings.
- **Rebuild Graph Button**: One-click re-graphification of all MySQL records directly from the UI.

---

## Installation & Quick Start Guide

### 1. System Requirements
- **OS**: Windows 10/11 (64-bit)
- **Python**: 3.11, 3.12, or 3.13 (Python 3.13.7 verified)
- **MySQL**: 8.0 or newer running locally on port 3306
- **Ollama**: (Optional for LLM features) Installed and running on `http://localhost:11434`
- **RAM**: 8 GB minimum (16 GB recommended)

### 2. Clone and Setup Environment
Open PowerShell in your workspace directory:
```powershell
cd d:\scraper

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```

> [!TIP]
> If you encounter a PowerShell script execution policy error, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 3. Install Python Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` (or edit the existing `.env`):
```ini
APP_NAME=Financial-AI-Assistant
ENVIRONMENT=development
LOG_LEVEL=INFO

# MySQL Database Configuration
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=financial_ai
MYSQL_USER=root
MYSQL_PASSWORD=your_actual_mysql_password
MYSQL_POOL_SIZE=5

# Ollama LLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=phi3:mini
OLLAMA_TIMEOUT=120.0

# Document Chunking Settings
CHUNK_SIZE=1000
CHUNK_OVERLAP=150
MAX_PDF_PAGES=60
```

### 5. Run Database Migrations
Initialize the `financial_ai` database and all 6 normalized tables:
```powershell
python run.py --migrate
```

### 6. Verify System Health
Run diagnostic checks on configuration, filesystem directories, and MySQL connectivity:
```powershell
python run.py --health
```

### 7. (Optional) Setup Ollama for Local AI
1. Download Ollama from [ollama.com](https://ollama.com).
2. Open PowerShell and pull the quantized Microsoft Phi-3 Mini model:
   ```powershell
   ollama pull phi3:mini
   ```
3. Verify Ollama is listening by visiting `http://localhost:11434` in your browser.

### 8. Launch the Web Server & Dashboard
```powershell
python run.py --serve --port 8000
```
Open your browser and navigate to:
- **Dashboard UI**: [http://localhost:8000](http://localhost:8000)
- **Graph Explorer**: [http://localhost:8000/graph](http://localhost:8000/graph)
- **Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## CLI Management Tool (`run.py`)

The root `run.py` script serves as the centralized CLI for all operations:

```powershell
# Start the web server and dashboard (default port 8000)
python run.py --serve
python run.py -s --port 8080

# Execute database migrations (creates database & tables)
python run.py --migrate

# Run diagnostic health check on MySQL, storage, and config
python run.py --health

# Re-build and serialize the Knowledge Graph from MySQL records
python run.py --graphify

# Display current configuration and environment settings
python run.py --info
```

---

## REST API Reference

All REST endpoints are prefixed with `/api` and return standard JSON responses:

### 1. System & Health
- **`GET /api/health`**
  - Returns MySQL ping status, server version, storage directory availability, and Ollama configuration.

### 2. Companies & Financials
- **`GET /api/companies`**
  - Returns summary cards for all registered companies with document counts and latest financial metrics.
- **`GET /api/companies/{company_id}`**
  - Returns complete company profile: `about`, `sector`, `ratios`, `pros`, `cons`, multi-year `financial_data`, `quarterly_data`, `risks`, and `documents`.

### 3. Live Screener Scraping & Reprocessing
- **`POST /api/scrape/search`**
  - Body: `{"query": "Reliance"}`
  - Searches Screener.in live and returns matching companies with tickers and URLs.
- **`POST /api/scrape/ingest`**
  - Body: `{"query": "TCS"}` or `{"query": "/company/TCS/consolidated/"}`
  - Executes the full automated pipeline: scrapes Screener $\to$ downloads report/concall PDF $\to$ checks SHA-256 $\to$ extracts text & chunks $\to$ discovers risks with page numbers $\to$ stores in MySQL $\to$ syncs Knowledge Graph.
- **`POST /api/scrape/reprocess/{company_id}`**
  - Re-runs PDF extraction, chunking, and risk detection on an existing downloaded filing.

### 4. Knowledge Graph
- **`GET /api/graph`**
  - Returns complete Knowledge Graph JSON structure (`summary`, `nodes`, `edges`).
  - If requested from a browser (`Accept: text/html`), serves the fullscreen Cytoscape Visualizer (`frontend/graph.html`).
- **`GET /api/graph/{company_id}`**
  - Returns isolated 1-hop and 2-hop subgraph for the specified company.
- **`POST /api/graph/rebuild`**
  - Forces complete re-graphification of all MySQL records and concall chunks.

### 5. Documents & Exports
- **`GET /api/documents`**
  - Query param: `?company_id=1` (optional). Lists documents with SHA-256 hashes and statuses.
- **`GET /api/documents/{document_id}/download`**
  - Streams the authentic PDF file directly to the browser.
- **`GET /api/export/excel/{company_id}`**
  - Generates and streams a styled, 4-sheet formatted Excel workbook (`.xlsx`) containing:
    1. *Company Summary & Ratios*
    2. *Multi-Year Financial Statements*
    3. *Disclosed Risk Factors & Citations*
    4. *Extracted PDF Text Chunks*
- **`GET /api/export/csv/{company_id}`**
  - Generates and streams financial metrics in standard CSV format.

### 6. AI Research Assistant (Graph RAG)
- **`POST /api/ask`**
  - Body:
    ```json
    {
      "question": "What are the primary operational risks and revenue growth for Reliance?",
      "company_id": 5
    }
    ```
  - Traverses the in-memory Knowledge Graph, extracts semantic triples, queries local Ollama Phi-3 (or direct graph synthesis), and returns the grounded answer with exact source citations:
    ```json
    {
      "question": "What are the primary operational risks and revenue growth for Reliance?",
      "answer": "...",
      "graph_nodes": ["Company: RELIANCE", "RELIANCE Metric: FY2024 (Rev: ₹901064.0Cr)", "RELIANCE Risk: Supply Chain Volatility (p.42)"],
      "citations": [
        {
          "company": "RELIANCE",
          "risk": "Supply Chain Volatility",
          "source": "RELIANCE_Annual_Report.pdf",
          "page": "Page 42",
          "period": "FY2024"
        }
      ],
      "llm_used": "phi3:mini",
      "ollama_available": true
    }
    ```

---

## Developer Guide: How to Make Changes

This section provides clear, step-by-step instructions for extending or customizing every component of the application.

---

### 1. Adding a New Data Source / Scraper

To add a new scraper (e.g., Yahoo Finance, Moneycontrol, or SEC EDGAR filings):

1. **Create the Scraper Class**:
   Add a new file in `app/scraper/` (e.g., `app/scraper/yahoo_scraper.py`) inheriting from `BaseScraper` (`app/scraper/base.py`):
   ```python
   # app/scraper/yahoo_scraper.py
   from typing import Dict, Any, List
   from app.scraper.base import BaseScraper

   class YahooFinanceScraper(BaseScraper):
       def search_company(self, query: str) -> List[Dict[str, Any]]:
           # Implement ticker resolution
           pass

       def fetch_company_data(self, ticker: str) -> Dict[str, Any]:
           # Return standardized dict with: name, ticker, website, about, ratios, financial_data
           pass
   ```
2. **Integrate into Ingestion Pipeline**:
   Open `app/pipeline/ingestion_pipeline.py`. In `__init__()`, instantiate your scraper:
   ```python
   from app.scraper.yahoo_scraper import YahooFinanceScraper
   self.yahoo_scraper = YahooFinanceScraper(self.settings)
   ```
3. **Expose in REST API**:
   Open `app/api/routes.py` and create an endpoint like `POST /api/scrape/yahoo` that delegates to your new pipeline method.

---

### 2. Adding New Financial Metrics or Ratios

To extract and display a new metric (e.g., *Free Cash Flow* or *Debt-to-Equity Ratio*):

1. **Update MySQL Database Schema**:
   Add the column to `app/database/migrations/schema.sql`:
   ```sql
   ALTER TABLE financial_data ADD COLUMN free_cash_flow DECIMAL(20, 4) NULL AFTER cash_flow;
   ```
   Execute the migration in your MySQL client or CLI.
2. **Update Scraper Extraction**:
   In `app/scraper/screener_scraper.py`, locate `_parse_profit_loss()` or `_parse_ratios()`. Extract the new row from the HTML table:
   ```python
   fcf_val = _get_val("free cash flow")
   metrics_list.append({
       ...,
       "free_cash_flow": fcf_val * 1e7 if fcf_val is not None else None,
   })
   ```
3. **Update Repository**:
   In `app/database/repositories.py`, update `FinancialDataRepository.create_batch()` to include `free_cash_flow` in the `INSERT INTO financial_data` statement.
4. **Update Pydantic Models**:
   In `app/api/models.py`, add `free_cash_flow: Optional[float] = None` to `FinancialDataPoint`.
5. **Update Knowledge Graph**:
   In `app/pipeline/graphify.py`, inside `Graphifier.graphify_from_db()`, include `free_cash_flow` in the `metric` node properties:
   ```python
   "free_cash_flow": float(fin["free_cash_flow"]) if fin.get("free_cash_flow") else None,
   ```
6. **Display in Frontend**:
   In `frontend/app.js`, add a KPI card or column in `renderCompanyDetail()` to render the metric.

---

### 3. Switching or Customizing the LLM Provider

The system uses a clean provider abstraction (`app/llm/base.py`). To switch from Ollama to another local or cloud provider (e.g., Llama.cpp, HuggingFace, OpenAI, or Google Gemini):

1. **Implement `LLMProvider`**:
   Create a new file `app/llm/openai_client.py`:
   ```python
   from app.llm.base import LLMProvider
   import httpx

   class OpenAIChatProvider(LLMProvider):
       def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
           self.api_key = api_key
           self.model = model

       def generate(self, prompt: str, system: str = "") -> str:
           # Call OpenAI REST API via httpx
           ...

       def check_availability(self) -> dict:
           return {"available": True, "provider": "OpenAI"}
   ```
2. **Wire Provider in Graph RAG**:
   In `app/pipeline/graph_rag.py`, initialize your provider in `GraphRAGEngine.__init__()`:
   ```python
   # Replace OllamaProvider with your new provider
   self.llm = OpenAIChatProvider(api_key="...", model="gpt-4o-mini")
   ```

---

### 4. Customizing Graph RAG Prompts

All prompts are isolated in `app/llm/prompts.py`:
- **`GRAPH_RAG_SYSTEM_PROMPT`**: Controls persona, tone, financial precision, and strict adherence to provided facts.
- **`build_graph_rag_prompt(question, graph_context)`**: Structures the semantic triples, metrics, risks, and guidance into the final prompt.

To modify the executive persona or response structure, simply edit `app/llm/prompts.py`. No other files need to be changed.

---

### 5. Adding New Knowledge Graph Nodes & Edges

To add a new node type (e.g., `executive` for board members or `subsidiary` for business units):

1. **Add Node Type in `KnowledgeGraph`**:
   In `app/pipeline/graphify.py`:
   - Add default color in `KnowledgeGraph._default_color()`:
     ```python
     "executive": "#ec4899",  # Pink
     ```
   - Add default node size in `KnowledgeGraph._default_size()`:
     ```python
     "executive": 20,
     ```
2. **Populate in `Graphifier`**:
   Inside `Graphifier.graphify_from_db()`:
   ```python
   self.graph.add_node(
       node_id=f"exec_{exec_id}",
       label=exec_name,
       node_type="executive",
       properties={"designation": designation, "company_id": cid},
   )
   self.graph.add_edge(comp_node_id, f"exec_{exec_id}", "HAS_EXECUTIVE")
   ```
3. **Update Visualizer**:
   In `frontend/graph.html`, add a filter chip for the new type under `.filter-chip-group`.

---

### 6. Customizing the Frontend UI & Styling

- **Layout & Structure**: `frontend/index.html` (dashboard) and `frontend/graph.html` (Cytoscape visualizer).
- **Styling**: `frontend/style.css` defines the Obsidian glassmorphic design system using CSS custom properties (`--bg-base`, `--accent-cyan`, `--glass-bg`, etc.). Modifying these CSS variables updates the entire theme instantly.
- **Behavior & API Calls**: `frontend/app.js` manages client-side routing, debounced search (`initUniversalSearch`), ingestion progress polling (`startLiveScreenerIngestion`), and chat messages.

To test JavaScript syntax after editing:
```powershell
node -c frontend/app.js
```

---

### 7. Modifying Database Schema & Migrations

To add new tables or alter existing ones:
1. Open `app/database/migrations/schema.sql` and add your `CREATE TABLE` or `ALTER TABLE` statement.
2. The migration runner (`app/database/migrations/runner.py`) splits `schema.sql` into individual statements and executes them safely against MySQL.
3. Apply the changes:
   ```powershell
   python run.py --migrate
   ```

---

## Testing & Quality Assurance

The suite includes comprehensive automated tests covering all modules using `pytest`:

```powershell
# Run the entire test suite
.\.venv\Scripts\pytest.exe -v

# Run a specific test suite
.\.venv\Scripts\pytest.exe tests/test_screener_scraper.py -v
.\.venv\Scripts\pytest.exe tests/test_graphify.py -v
.\.venv\Scripts\pytest.exe tests/test_database.py -v
```

### Test Coverage Highlights:
- **`test_screener_scraper.py`**: Validates search API parsing, HTML ratio extraction, multi-year statement generation, URL fragment stripping, and concall transcript extraction.
- **`test_screener_api.py`**: Integration tests verifying `/api/scrape/search` and `/api/scrape/ingest`.
- **`test_database.py`**: Verifies MySQL connection pooling, schema DDL parsing, parameterized queries, and SHA-256 deduplication logic.
- **`test_graphify.py`**: Verifies node and edge addition, $O(1)$ index lookups, subgraph neighborhood extraction, JSON serialization/deserialization, and concall guidance classification.
- **`test_pdf_extractor.py`**: Tests PyPDF text extraction, sliding-window chunk overlap, and regex risk factor extraction.
- **`test_api_and_export.py`**: Tests company listing, document downloading, multi-sheet Excel `.xlsx` generation, and Graph RAG endpoints.

---

## Troubleshooting & FAQ

### 1. `Access denied for user 'root'@'localhost'`
- **Cause**: The `.env` file contains an incorrect MySQL password or empty string.
- **Fix**: Open `.env` and set `MYSQL_PASSWORD=your_actual_password`.

### 2. `Can't connect to MySQL server on 'localhost'`
- **Cause**: The MySQL Windows service is stopped.
- **Fix**: Open PowerShell as Administrator and run:
  ```powershell
  Start-Service MySQL80
  ```

### 3. Ollama Connection Error or Slow Inference
- **Cause**: Ollama is not installed, not running, or the model `phi3:mini` has not been downloaded.
- **Fix**:
  1. Open a terminal and run `ollama serve`.
  2. In another terminal, pull the model: `ollama pull phi3:mini`.
  - *Note*: If Ollama is offline, the application automatically falls back to deterministic in-memory Graph RAG synthesis so the UI never breaks.

### 4. PDF Download Timeouts
- **Cause**: Some public corporate filing servers or stock exchange CDNs occasionally throttle high-frequency requests.
- **Fix**: The scraper includes automated fallbacks:
  1. Attempts official Annual Report PDF download.
  2. If timed out, falls back to downloading the latest BSE India concall transcript (~0.6 MB).
  3. If all remote downloads fail, generates a valid local filing archive so processing completes smoothly.

### 5. Port 8000 Already in Use
- **Cause**: Another process or background worker is bound to port 8000.
- **Fix**: Launch the server on another port:
  ```powershell
  python run.py --serve --port 8080
  ```

---

## License

This project is licensed under the MIT License. You are free to modify, distribute, and integrate this software into proprietary or open-source financial workflows.
