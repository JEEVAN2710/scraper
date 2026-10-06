# V2 Architecture Plan

> **Status**: Architectural Assessment & Migration Roadmap (In-Place V2 Upgrade)  
> **Repository Root**: `D:\scraper`  
> **Target Branch**: `v2-development`  
> **Hardware Target**: Windows 11 Pro, Intel Core i3 12th-Gen (6P/2E or 2P/8E cores), 16 GB RAM, Intel UHD/Iris Xe Graphics, Zero CUDA/Docker Dependencies  

---

## Executive Summary

The V1 application is a functioning local-first prototype that searches Screener.in, downloads official Indian corporate filings (Annual Reports and BSE concall transcripts), extracts text via `pypdf`, stores metrics and risks in MySQL 8.0, compiles an in-memory Knowledge Graph, answers financial questions via Graph RAG (Ollama), and serves an interactive glassmorphic dashboard.

V2 transitions this platform from a single-shot reactive workflow:
$$\text{Search Company} \longrightarrow \text{Scrape Company} \longrightarrow \text{Process Documents}$$
into a proactive, autonomous, multi-source financial intelligence platform:
$$\text{Register Company} \longrightarrow \text{Configure Sources} \longrightarrow \text{Define Automation} \longrightarrow \text{Scheduled Discovery} \longrightarrow \text{PyMuPDF / OCR} \longrightarrow \text{Structured AI Extraction} \longrightarrow \text{MySQL Ground Truth} \longrightarrow \text{Research Profile / RAG} \longrightarrow \text{Exports}$$

This document provides a comprehensive codebase assessment of the V1 baseline in `D:\scraper` and defines the architectural blueprint for upgrading the application in-place without breaking existing features or introducing unnecessary heavyweight dependencies (no Docker, no n8n, no Celery, no Redis, no LangChain).

---

## 1. Current V1 Architecture

The V1 system located in `D:\scraper` consists of nine functional packages:

```
D:\scraper\
├── app\
│   ├── config\settings.py          # Pydantic BaseSettings loading .env, default OLLAMA_MODEL="phi3:mini"
│   ├── database\
│   │   ├── connection.py           # DatabaseManager: MySQL pooling (mysql.connector.pooling)
│   │   ├── repositories.py         # 6 repositories (Company, Document, Financial, Risk, Chunk, Log)
│   │   └── migrations\
│   │       ├── schema.sql          # 6 normalized tables (companies, documents, financial_data, risk_factors, document_chunks, processing_logs)
│   │       └── runner.py           # SQL statement splitter and executor
│   ├── scraper\
│   │   └── screener_scraper.py     # HTTPX + BeautifulSoup4 scraping Screener search API, P&L table, ratios, PDF links
│   ├── extraction\
│   │   └── pdf_extractor.py        # PyPDF text extraction, SHA-256 hashing, 1000-char sliding chunker, regex risk heuristic
│   ├── llm\
│   │   ├── base.py                 # Abstract LLMProvider interface
│   │   ├── ollama_client.py        # OllamaProvider communicating with http://localhost:11434/api/generate
│   │   └── prompts.py              # Financial extraction and Graph RAG system prompts
│   ├── pipeline\
│   │   ├── ingestion_pipeline.py   # Synchronous monolithic orchestrator tying scraper, downloader, MySQL, and graph
│   │   ├── graphify.py             # KnowledgeGraph in-memory indexer (5 node types, 7 edge types, concall guidance regexes)
│   │   └── graph_rag.py            # GraphRAGEngine: subgraph traversal, semantic triples, Ollama prompt, offline fallback
│   ├── export\
│   │   └── excel_exporter.py       # openpyxl multi-sheet formatted workbook (.xlsx) and CSV generator
│   ├── api\
│   │   ├── models.py               # Pydantic v2 schemas (CompanyDetailResponse, IngestionResponse, AskResponse, etc.)
│   │   └── routes.py               # Single 826-line FastAPI router hosting 12 endpoints
│   └── main.py                     # FastAPI app factory, CORS, static frontend mount (/static)
├── frontend\                       # Vanilla JS, CSS3, HTML5 (index.html, app.js, style.css, graph.html)
├── data\                           # Storage directories (downloads, processed, exports)
├── logs\                           # Rotating audit logs (app.log)
├── tests\                          # 7 test suites (28 passing pytest unit & integration tests)
├── run.py                          # Unified CLI entrypoint (--serve, --health, --migrate, --graphify, --info)
├── requirements.txt                # Core Python dependencies
└── .env / .env.example             # Environment variables
```

### V1 Execution Flow
1. User enters a query into the frontend or calls `POST /api/scrape/ingest`.
2. `IngestionPipeline` executes a synchronous sequence:
   - Queries Screener.in API (`/api/company/search/?q=...`)
   - Scrapes HTML page for `#top-ratios`, `#profit-loss`, `.about`, `#peers`, `#quarters`
   - Stores/updates `companies` record in MySQL
   - Downloads Annual Report PDF (or falls back to BSE concall transcript)
   - Computes SHA-256 hash and checks `documents` table for existing match
   - Extracts text page-by-page using `pypdf.PdfReader`
   - Generates 1000-character chunks with 150-char overlap
   - Applies regex patterns to extract risk factors with page numbers
   - Ingests quarterly concall transcripts (up to 4 quarters)
   - Runs `Graphifier.graphify_from_db()` to compile and serialize `data/processed/knowledge_graph.json`
3. The user queries the chat endpoint (`POST /api/ask`), which traverses the in-memory graph neighborhood and prompts Ollama or returns deterministic graph synthesis.

---

## 2. V1 Components We Keep

The following V1 components are well-designed, robust, and will be retained in V2:

| Component | File Path | Why We Keep It |
| :--- | :--- | :--- |
| **MySQL Connection Pool** | `app/database/connection.py` | Built on `mysql.connector.pooling.MySQLConnectionPool`. Implements safe cursor context managers (`get_cursor`), ping health checks, auto-reconnection, and clean resource cleanup without heavy ORM overhead. |
| **Parameterized Repositories** | `app/database/repositories.py` | All SQL queries are strictly parameterized using `%s` placeholders, preventing SQL injection. Existing CRUD logic for companies, documents, financial data, risk factors, and chunks is solid. |
| **Cryptographic SHA-256 Deduplication** | `app/extraction/pdf_extractor.py` (`compute_sha256`) | Streams files in 64 KB blocks to compute cryptographic hashes. Enforces unique constraint in MySQL `documents.file_hash`, preventing duplicate downloads and redundant processing. |
| **Provider-Agnostic LLM Interface** | `app/llm/base.py` | Clean abstract base class `LLMProvider` requiring `generate()`, `check_availability()`, and `get_model_name()`. Allows switching model backends without touching data pipelines. |
| **Multi-Sheet Excel & CSV Exporter** | `app/export/excel_exporter.py` | High-quality `openpyxl` implementation generating formatted workbooks with brand headers, auto-adjusted column widths, number formatting (`₹` / `$`), and raw PDF text chunk tabs. |
| **Fullscreen Knowledge Graph Visualizer** | `frontend/graph.html` | A dedicated 1,530-line interactive Cytoscape.js visualizer with physics simulation (`cose`), category filter chips, search focus, node inspection drawer, and color-coded node classes. |
| **Glassmorphic UI Design System** | `frontend/style.css`, `frontend/index.html` | Custom Obsidian dark glassmorphic styling, responsive sidebar drawer, KPI ribbon, quarterly breakdown table, live progress banner, and citation cards. |
| **Automated Test Foundation** | `tests/` | 28 automated tests covering settings, database connection, repositories, scraper parsing, REST endpoints, and graph serialization. |

---

## 3. Components We Refactor

These components contain solid logic but require structural refactoring to support V2 requirements:

| Component | Current State | Required Refactoring | Why Needed |
| :--- | :--- | :--- | :--- |
| **`app/config/settings.py` & `.env.example`** | Defaults to `phi3:mini`; lacks automation intervals, OCR settings, and download constraints. | Update default model to `qwen3:4b`. Add `OCR_ENABLED`, `OCR_LANGUAGE`, `OCR_FALLBACK_MIN_WORDS`, `MAX_DOWNLOAD_SIZE_MB`, `MAX_PDF_PAGES`, `AUTOMATION_WORKER_INTERVAL_SEC`, and `SCHEDULER_ENABLED`. | V2 requires configurable local LLM defaults (Qwen3 4B) and operational settings for the autonomous scheduler, OCR fallback, and safety limits. |
| **`app/llm/ollama_client.py`** | Calls `/api/generate` with plain text options and hardcoded temperature/predict limits; lacks JSON schema mode. | Add structured JSON output support (leveraging Ollama's `format="json"`), explicit context window parameters (`num_ctx=8192`), configurable timeout, and robust retry logic. | Structured financial extraction requires strict JSON formatting validated against Pydantic schemas. |
| **`app/pipeline/graphify.py`** | Treats graph as an alternative data store; can get out of sync with MySQL if not manually rebuilt. | Refactor `Graphifier` so that MySQL is strictly the single source of truth. The graph becomes a derived, transient in-memory index that is deterministically rebuildable from MySQL tables at any time. | Upholds the core architectural principle: MySQL = Source of Truth; Knowledge Graph = Secondary Index; LLM = Reasoning Layer. |
| **`app/pipeline/graph_rag.py`** | Traverses graph but falls back to mock company data if MySQL isn't populated; mixes prompt formulation with synthesis logic. | Decouple context assembly from inference. Use MySQL entity IDs for primary lookup, traverse the graph for 1-hop/2-hop relationship triples, and include verifiable document SHA-256 fingerprints in citations. | Prevents demo-mode leakage and ensures all AI answers cite authentic, verifiable source filings. |
| **`app/api/routes.py`** | Monolithic 826-line file containing all route definitions, fallback demo datasets, and business logic. | Split into modular route packages: `routes/health.py`, `routes/companies.py`, `routes/sources.py`, `routes/documents.py`, `routes/automations.py`, `routes/research.py`, `routes/exports.py`. | Maintainability, clean separation of concerns, and readiness for automated background jobs and source management. |

---

## 4. Components We Extend

These existing components will be extended with new capabilities:

| Component | Current Capability | V2 Extension | Why Needed |
| :--- | :--- | :--- | :--- |
| **Database Schema (`schema.sql`)** | 6 tables: `companies`, `documents`, `financial_data`, `risk_factors`, `document_chunks`, `processing_logs`. | Extend existing tables and add 4 new tables: `company_sources`, `automations`, `automation_runs`, `extraction_runs`. Rename or alias `financial_data` to `financial_metrics`. | First-class automation requires tracking data sources per company, scheduled triggers, execution run states, and LLM extraction audit trails. |
| **`CompanyRepository`** | Handles `name`, `ticker`, `website`, `about`, `sector`, `ratios_json`. | Add methods for managing associated sources (`add_source`, `list_sources`), tracking automation status, and updating watchlist flags. | A company in V2 can have multiple sources (Screener, IR website, BSE, NSE, filings RSS). |
| **`DocumentRepository`** | Tracks basic statuses (`downloaded`, `extracting`, `processed`, `failed`). | Extend with V2 lifecycle states: `DISCOVERED`, `DOWNLOADING`, `DOWNLOADED`, `DUPLICATE`, `EXTRACTING`, `OCR`, `CHUNKING`, `AI_EXTRACTING`, `VALIDATING`, `STORED`, `FAILED`. Add `file_size_bytes`, `source_id`, `page_count`. | Enables fine-grained observability of exactly which stage a document is in. |
| **`ProcessingLogRepository`** | Logs stage, status, message, error details linked only to `document_id`. | Link logs to both `automation_run_id` and `document_id`. Add duration tracking and log level filtering. | Supports troubleshooting automation workflow failures from the UI. |
| **`app/scraper/`** | Only contains `screener_scraper.py`. | Introduce `BaseScraper` interface and source registry. Keep `screener_scraper.py` as the default source implementation; add stubs for `generic_ir_scraper.py` and `exchange_scraper.py`. | Eliminates single-vendor dependency on Screener.in and enables scraping official investor relations websites. |

---

## 5. Components We Eventually Replace

The following implementations will be deprecated and replaced during V2:

| Component to Replace | Replacement Component | Reason for Replacement |
| :--- | :--- | :--- |
| **`pypdf.PdfReader` in `pdf_extractor.py`** | **PyMuPDF (`fitz`)** via `app/documents/extractor.py` | PyMuPDF is 10x-20x faster on CPU, handles corrupted or complex font encodings far better, extracts precise bounding boxes and layout structures, and provides direct page rasterization to image buffers for OCR. |
| **Low-word page skipping (unhandled scanned PDFs)** | **`pytesseract` + Pillow OCR Fallback** via `app/documents/ocr.py` | In V1, pages with `< 20` words are simply flagged as `is_scanned = True` and their text is lost. V2 will automatically render low-density pages to an image and run Tesseract OCR to recover text from scanned filings. |
| **Regex-only risk heuristic (`extract_risk_factors`)** | **LLM Structured Extraction + Pydantic Validation** via `app/extraction/` | Regex pattern matching (`cybersecurity|compliance`) only captures superficial keyword matches. V2 will feed chunks into the local LLM (`qwen3:4b`) to extract contextual risks with severity and likelihood, while keeping regexes as a fast fallback. |
| **Synchronous `IngestionPipeline.run_screener_ingestion()`** | **Asynchronous `AutomationRunner` & `JobManager`** via `app/automation/` | V1 blocks the FastAPI worker thread for 30–60 seconds while downloading and processing PDFs. V2 dispatches background automation jobs with observable progress states, preventing UI freezes. |

---

## 6. Proposed V2 Architecture

```
                                  USER INTERFACE / BROWSER EXTENSION
                                (Dashboard / Automations / Research)
                                                 │
                                                 ▼
                                     FASTAPI APPLICATION LAYER
                          ┌──────────────────────────────────────────────┐
                          │ /api/companies        /api/sources           │
                          │ /api/automations      /api/runs              │
                          │ /api/documents        /api/research          │
                          │ /api/graph            /api/exports           │
                          └──────────────────────┬───────────────────────┘
                                                 │
                                                 ▼
                                     AUTOMATION & JOB LAYER
                          ┌──────────────────────────────────────────────┐
                          │ AutomationScheduler (Lightweight Python Loop)│
                          │ AutomationRunner    (Job State Coordinator)  │
                          │ JobManager          (State & Retry Policy)   │
                          └──────────────┬───────────────────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
       DATA SOURCE ENGINE                              DOCUMENT PIPELINE
┌───────────────────────────────┐               ┌───────────────────────────────┐
│ BaseScraper Interface         │               │ DocumentDownloader (HTTPX)    │
│ • ScreenerScraper (Default)   │               │ SHA-256 Deduplication Check  │
│ • GenericIRScraper (Company)  │               │ PyMuPDF (fitz) Text Extractor │
│ • ExchangeScraper (BSE/NSE)   │               │ OCR Fallback (Tesseract/PIL)  │
│ • BrowserExtensionHook        │               │ DocumentChunker (Provenance)  │
└───────────────────────────────┘               └───────────────┬───────────────┘
                                                                │
                                                                ▼
                                                       STRUCTURED AI EXTRACTION
                                                ┌───────────────────────────────┐
                                                │ LLMProvider (Base Interface)  │
                                                │ └── OllamaProvider (qwen3:4b) │
                                                │ Pydantic Validation Layer     │
                                                │ Financial Accounting Sanity   │
                                                └───────────────┬───────────────┘
                                                                │
                                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    PRIMARY SOURCE OF TRUTH                                   │
│                                           MySQL 8.0                                          │
│  • companies         • company_sources    • automations         • automation_runs            │
│  • documents         • document_chunks    • extraction_runs     • financial_metrics          │
│  • risk_factors      • processing_logs                                                       │
└───────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                │
                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   SECONDARY INDEXING LAYER                                   │
│                                  In-Memory Knowledge Graph                                   │
│  • O(1) Neighborhood Traversal • Derived directly from MySQL • Rebuildable on demand         │
└───────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                │
                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  AI RESEARCH & EXPORT LAYER                                  │
│  • Graph RAG Assistant • Exact Page & SHA-256 Citations • Multi-Sheet Excel & CSV Exporters  │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Proposed Directory Changes

To maintain strict continuity with V1, all upgrades occur **in-place** inside `D:\scraper`. No secondary folder is created.

```
D:\scraper\
├── app/
│   ├── main.py                     # [MODIFY] Mount modular API routers and lifespan event
│   │
│   ├── config/
│   │   ├── __init__.py             # [KEEP]
│   │   ├── settings.py             # [MODIFY] Add automation, OCR, and Qwen3 4B settings
│   │   └── logging.py              # [NEW] Centralized rotating log configuration
│   │
│   ├── database/
│   │   ├── __init__.py             # [KEEP]
│   │   ├── connection.py           # [KEEP] DatabaseManager with connection pooling
│   │   ├── repositories.py         # [MODIFY] Add Source, Automation, Run repositories
│   │   └── migrations/
│   │       ├── runner.py           # [KEEP] Migration runner
│   │       ├── schema.sql          # [KEEP] V1 baseline schema
│   │       └── schema_v2.sql       # [NEW] V2 non-destructive table additions & modifications
│   │
│   ├── scraping/                   # [REFACTOR from app/scraper/]
│   │   ├── __init__.py             # [NEW]
│   │   ├── base.py                 # [NEW] Abstract BaseScraper interface
│   │   ├── registry.py             # [NEW] Scraper registry and factory
│   │   └── sources/
│   │       ├── __init__.py         # [NEW]
│   │       ├── screener.py         # [RENAME/REFACTOR from screener_scraper.py]
│   │       └── company_ir.py       # [NEW] Generic company investor relations scraper
│   │
│   ├── documents/                  # [EXTEND from empty folder]
│   │   ├── __init__.py             # [KEEP]
│   │   ├── downloader.py           # [NEW] Streaming download with size limits & timeout
│   │   ├── hashing.py              # [NEW] SHA-256 hashing extracted from pdf_extractor.py
│   │   ├── extractor.py            # [NEW] PyMuPDF (fitz) text extraction & page structuring
│   │   ├── ocr.py                  # [NEW] pytesseract + Pillow OCR fallback for low-density pages
│   │   └── chunker.py              # [NEW] Sliding window chunker preserving page provenance
│   │
│   ├── extraction/                 # [REFACTOR from V1 pdf_extractor.py]
│   │   ├── __init__.py             # [KEEP]
│   │   ├── schemas.py              # [NEW] Pydantic models for structured financial extraction
│   │   ├── extractor.py            # [NEW] LLM-based structured extraction pipeline
│   │   └── validator.py            # [NEW] Accounting sanity checks & identity validation
│   │
│   ├── llm/
│   │   ├── __init__.py             # [KEEP]
│   │   ├── base.py                 # [KEEP] Abstract LLMProvider interface
│   │   ├── ollama_client.py        # [MODIFY] Add JSON mode, Qwen3 4B configuration, retry logic
│   │   └── prompts.py              # [MODIFY] Add structured extraction prompts
│   │
│   ├── automation/                 # [NEW PACKAGE]
│   │   ├── __init__.py             # [NEW]
│   │   ├── scheduler.py            # [NEW] Lightweight background scheduler (Python threading)
│   │   ├── runner.py               # [NEW] Automation execution engine
│   │   └── pipeline.py             # [NEW] Multi-stage document processing coordinator
│   │
│   ├── jobs/                       # [NEW PACKAGE]
│   │   ├── __init__.py             # [NEW]
│   │   ├── manager.py              # [NEW] Job lifecycle & state management
│   │   └── retry.py                # [NEW] Retry policies with exponential backoff
│   │
│   ├── research/                   # [REFACTOR from app/pipeline/]
│   │   ├── __init__.py             # [NEW]
│   │   ├── graph.py                # [REFACTOR from pipeline/graphify.py] Derived in-memory index
│   │   ├── rag.py                  # [REFACTOR from pipeline/graph_rag.py] Grounded reasoning engine
│   │   └── citations.py            # [NEW] Verifiable page & hash citation builder
│   │
│   ├── export/
│   │   ├── __init__.py             # [KEEP]
│   │   ├── excel_exporter.py       # [KEEP] Multi-sheet openpyxl workbook generator
│   │   └── csv_exporter.py         # [NEW] Standardized CSV metrics generator
│   │
│   └── api/
│       ├── __init__.py             # [KEEP]
│       ├── models.py               # [MODIFY] Add Automation, Source, and Run schemas
│       └── routes/                 # [REFACTOR from single routes.py]
│           ├── __init__.py         # [NEW]
│           ├── health.py           # [NEW] System health and component status
│           ├── companies.py        # [NEW] Company CRUD and profile retrieval
│           ├── sources.py          # [NEW] Data source configuration
│           ├── automations.py      # [NEW] Automation creation, scheduling, run-now
│           ├── documents.py        # [NEW] Document listing, chunks, download
│           ├── research.py         # [NEW] Graph RAG inquiries and graph visualization
│           └── exports.py          # [NEW] Excel and CSV downloads
│
├── frontend/                       # [KEEP] Existing UI continues functioning
│   ├── index.html                  # [MODIFY incrementally in Phase 7]
│   ├── graph.html                  # [KEEP] Fullscreen Cytoscape Visualizer
│   ├── app.js                      # [MODIFY incrementally in Phase 7]
│   └── style.css                   # [KEEP]
│
├── data/                           # [KEEP] Storage directories
├── logs/                           # [KEEP] Log files
├── tests/                          # [EXTEND] Add tests for PyMuPDF, OCR, Automation, and Schemas
├── run.py                          # [MODIFY] Add --worker flag for background automation
├── requirements.txt                # [MODIFY] Add pymupdf, pytesseract, pillow
├── .env.example                    # [MODIFY] Add V2 configuration keys
└── README.md                       # [MODIFY] Document V2 features and architecture
```

---

## 8. Proposed Database Changes

The relational database remains **MySQL 8.0** (`financial_ai`). All schema modifications are non-destructive and backward-compatible with V1 records.

### Complete 10-Table Relational Schema

```
                                  ┌───────────────────────────┐
                                  │         companies         │
                                  ├───────────────────────────┤
                                  │ id (PK)                   │
                                  │ name, ticker, website     │
                                  │ about, sector, ratios_json│
                                  └─────────────┬─────────────┘
                                                │ 1:N
                  ┌─────────────────────────────┼─────────────────────────────┐
                  ▼                             ▼                             ▼
    ┌───────────────────────────┐ ┌───────────────────────────┐ ┌───────────────────────────┐
    │      company_sources      │ │        automations        │ │         documents         │
    ├───────────────────────────┤ ├───────────────────────────┤ ├───────────────────────────┤
    │ id (PK)                   │ │ id (PK)                   │ │ id (PK)                   │
    │ company_id (FK)           │ │ company_id (FK)           │ │ company_id (FK)           │
    │ source_type, source_url   │ │ source_id (FK)            │ │ source_id (FK)            │
    │ is_active, config_json    │ │ schedule_cron, is_active  │ │ file_name, file_hash (UK) │
    └───────────────────────────┘ └─────────────┬─────────────┘ │ processing_status, ...    │
                                                │ 1:N           └─────────────┬─────────────┘
                                                ▼                             │ 1:N
                                  ┌───────────────────────────┐               │
                                  │      automation_runs      │               │
                                  ├───────────────────────────┤               │
                                  │ id (PK)                   │               │
                                  │ automation_id (FK)        │               │
                                  │ status, trigger_type      │               │
                                  │ docs_discovered, ...      │               │
                                  └─────────────┬─────────────┘               │
                                                │                             │
                  ┌─────────────────────────────┴─────────────────────────────┤
                  ▼                                                           ▼
    ┌───────────────────────────┐                               ┌───────────────────────────┐
    │      processing_logs      │                               │      document_chunks      │
    ├───────────────────────────┤                               ├───────────────────────────┤
    │ id (PK)                   │                               │ id (PK)                   │
    │ automation_run_id (FK)    │                               │ document_id (FK)          │
    │ document_id (FK)          │                               │ chunk_index, page_start   │
    │ stage, status, message    │                               │ page_end, content         │
    └───────────────────────────┘                               └─────────────┬─────────────┘
                                                                              │ 1:N
                                                                              ▼
                                                                ┌───────────────────────────┐
                                                                │      extraction_runs      │
                                                                ├───────────────────────────┤
                                                                │ id (PK)                   │
                                                                │ document_id (FK)          │
                                                                │ model_name, prompt_tokens │
                                                                │ raw_response, is_valid    │
                                                                └─────────────┬─────────────┘
                                                                              │ 1:N
                                                ┌─────────────────────────────┴─────────────┐
                                                ▼                                           ▼
                                  ┌───────────────────────────┐               ┌───────────────────────────┐
                                  │     financial_metrics     │               │       risk_factors        │
                                  │  (evolved from fin_data)  │               ├───────────────────────────┤
                                  ├───────────────────────────┤               │ id (PK)                   │
                                  │ id (PK)                   │               │ document_id (FK)          │
                                  │ extraction_run_id (FK)    │               │ extraction_run_id (FK)    │
                                  │ period, revenue, margin...│               │ risk, description, page   │
                                  └───────────────────────────┘               └───────────────────────────┘
```

### Table Definitions & Modifications

#### 1. `companies` (Modified in-place)
- **Retained**: `id`, `name`, `ticker`, `website`, `about`, `sector`, `ratios_json`, `created_at`, `updated_at`.
- **Added**:
  - `is_active` (`BOOLEAN DEFAULT TRUE`): Controls whether the company is actively tracked.
  - `tracking_tier` (`ENUM('standard', 'priority') DEFAULT 'standard'`): Prioritizes scheduled jobs.

#### 2. `company_sources` (NEW)
Tracks all discovery sources configured for a company.
- `id` (`INT AUTO_INCREMENT PRIMARY KEY`)
- `company_id` (`INT NOT NULL, FK -> companies(id) ON DELETE CASCADE`)
- `source_type` (`ENUM('screener', 'company_website', 'investor_relations', 'bse', 'nse', 'custom_url') NOT NULL`)
- `source_url` (`VARCHAR(1000) NOT NULL`)
- `is_active` (`BOOLEAN DEFAULT TRUE`)
- `config_json` (`JSON NULL`): Custom scraping headers, selectors, or URL patterns.
- `last_polled_at` (`TIMESTAMP NULL`)
- `created_at` (`TIMESTAMP DEFAULT CURRENT_TIMESTAMP`)

#### 3. `automations` (NEW)
Defines scheduled or manual workflow triggers per company or source.
- `id` (`INT AUTO_INCREMENT PRIMARY KEY`)
- `company_id` (`INT NOT NULL, FK -> companies(id) ON DELETE CASCADE`)
- `source_id` (`INT NULL, FK -> company_sources(id) ON DELETE SET NULL`)
- `name` (`VARCHAR(255) NOT NULL`): e.g., "Weekly Annual Report & Concall Sync"
- `schedule_type` (`ENUM('manual', 'interval', 'cron') DEFAULT 'manual'`)
- `schedule_expression` (`VARCHAR(100) NULL`): e.g., "0 9 * * 1" (Weekly Monday 9 AM) or "86400" (seconds)
- `is_active` (`BOOLEAN DEFAULT TRUE`)
- `max_retries` (`INT DEFAULT 3`)
- `created_at`, `updated_at` (`TIMESTAMP`)

#### 4. `automation_runs` (NEW)
Audit log of every automation execution.
- `id` (`INT AUTO_INCREMENT PRIMARY KEY`)
- `automation_id` (`INT NOT NULL, FK -> automations(id) ON DELETE CASCADE`)
- `trigger_type` (`ENUM('manual', 'scheduled', 'retry', 'extension') NOT NULL`)
- `status` (`ENUM('pending', 'running', 'completed', 'failed', 'cancelled') DEFAULT 'pending'`)
- `documents_discovered` (`INT DEFAULT 0`)
- `documents_downloaded` (`INT DEFAULT 0`)
- `documents_processed` (`INT DEFAULT 0`)
- `error_message` (`TEXT NULL`)
- `started_at`, `completed_at` (`TIMESTAMP NULL`)

#### 5. `documents` (Modified in-place)
- **Retained**: `id`, `company_id`, `file_name`, `file_url`, `local_path`, `file_hash` (`UNIQUE`), `document_type`, `report_period`, `report_date`, `downloaded_at`, `processed_at`, `created_at`.
- **Modified**:
  - `processing_status` expanded to: `'discovered', 'downloading', 'downloaded', 'duplicate', 'extracting', 'ocr', 'chunking', 'ai_extracting', 'validating', 'stored', 'failed'`
- **Added**:
  - `source_id` (`INT NULL, FK -> company_sources(id) ON DELETE SET NULL`)
  - `file_size_bytes` (`BIGINT NULL`)
  - `page_count` (`INT NULL`)
  - `text_density_score` (`FLOAT NULL`): Used to determine whether OCR was triggered.

#### 6. `document_chunks` (Modified in-place)
- **Retained**: `id`, `document_id`, `chunk_index`, `page_start`, `page_end`, `content`, `created_at`.
- **Added**:
  - `word_count` (`INT NULL`)
  - `is_ocr` (`BOOLEAN DEFAULT FALSE`): Indicates whether chunk text was recovered via Tesseract.

#### 7. `extraction_runs` (NEW)
Audits every structured LLM extraction pass.
- `id` (`INT AUTO_INCREMENT PRIMARY KEY`)
- `document_id` (`INT NOT NULL, FK -> documents(id) ON DELETE CASCADE`)
- `model_name` (`VARCHAR(100) NOT NULL`): e.g., "qwen3:4b"
- `prompt_tokens` (`INT NULL`), `completion_tokens` (`INT NULL`)
- `raw_response` (`MEDIUMTEXT NOT NULL`): Full JSON response from the LLM.
- `is_valid` (`BOOLEAN DEFAULT FALSE`): Whether Pydantic validation passed.
- `validation_errors` (`TEXT NULL`)
- `duration_seconds` (`FLOAT NULL`)
- `created_at` (`TIMESTAMP DEFAULT CURRENT_TIMESTAMP`)

#### 8. `financial_metrics` (Evolved from `financial_data`)
- **Retained**: All financial statement columns (`revenue`, `revenue_growth`, `net_profit`, `operating_profit`, `operating_margin`, `eps`, `total_assets`, `total_liabilities`, `cash_flow`, `currency`).
- **Added**:
  - `extraction_run_id` (`INT NULL, FK -> extraction_runs(id) ON DELETE SET NULL`)
  - `confidence_score` (`FLOAT DEFAULT 1.0`)
  - `source_page` (`INT NULL`): Page number where the metric was found.

#### 9. `risk_factors` (Modified in-place)
- **Retained**: `id`, `document_id`, `company_id`, `risk`, `description`, `page_number`, `created_at`.
- **Added**:
  - `extraction_run_id` (`INT NULL, FK -> extraction_runs(id) ON DELETE SET NULL`)
  - `severity` (`ENUM('low', 'medium', 'high', 'critical') DEFAULT 'medium'`)
  - `confidence_score` (`FLOAT DEFAULT 1.0`)

#### 10. `processing_logs` (Modified in-place)
- **Retained**: `id`, `document_id`, `stage`, `status`, `message`, `error_details`, `started_at`, `completed_at`.
- **Added**:
  - `automation_run_id` (`INT NULL, FK -> automation_runs(id) ON DELETE CASCADE`)
  - `duration_ms` (`INT NULL`)

---

## 9. Automation Architecture

### Why No Celery / Redis / Airflow?
The platform is built for a personal Intel Core i3 machine with 16 GB RAM running Windows 11. Celery requires an external message broker (RabbitMQ/Redis), Redis on Windows requires WSL or third-party ports, and Airflow has massive memory overhead (>2 GB baseline).

### Lightweight Python Scheduler & Worker
V2 implements a zero-dependency, local-friendly worker architecture:
1. **`AutomationScheduler` (`app/automation/scheduler.py`)**:
   - Runs as a daemon thread inside the FastAPI process (or via `python run.py --worker`).
   - Polls the `automations` table every 30 seconds for jobs where `is_active = TRUE` and `next_run_at <= NOW()`.
   - Uses simple locking via MySQL `UPDATE automations SET status = 'running' WHERE id = %s AND status = 'idle'` to prevent race conditions.
2. **`AutomationRunner` (`app/automation/runner.py`)**:
   - Executes the multi-stage pipeline:
     1. Discover new document URLs from configured `company_sources`.
     2. Check existing `documents.file_url` and SHA-256 hashes.
     3. Stream new files through `DocumentDownloader` with `MAX_DOWNLOAD_SIZE_MB` enforcement.
     4. Process text via PyMuPDF and OCR fallback.
     5. Execute structured LLM extraction via Qwen3 4B.
     6. Validate with Pydantic and persist to MySQL.
     7. Re-index MySQL records into the in-memory Knowledge Graph.
3. **`JobManager` (`app/jobs/manager.py`)**:
   - Provides explicit state transitions:
     $$\text{DISCOVERED} \to \text{DOWNLOADING} \to \text{DOWNLOADED} \to \text{EXTRACTING} \to \text{CHUNKING} \to \text{AI\_EXTRACTING} \to \text{STORED}$$
   - Implements exponential backoff retry for transient network timeouts.
   - Writes granular stage logs into `processing_logs`.

---

## 9.5 Phase 3 — Source Discovery and Document Acquisition

### Discovery Architecture
The document acquisition pipeline decouples source discovery from storage and extraction:
1. **Source Providers**:
   - `BaseSourceProvider`: Unified abstract base class defining `discover(source_url, company_identifier, max_documents) -> List[DiscoveredDocument]`.
   - `ScreenerProvider`: Connects to Screener.in company profile pages and parses official annual report links and quarterly concall transcripts.
   - `GenericWebProvider`: Scrapes arbitrary corporate websites, investor relations portals, and custom filing pages using BeautifulSoup.
   - `SourceDiscoveryRegistry`: Factory resolving `company_sources.source_type` (`screener`, `company_website`, `investor_relations`, `custom_url`, `bse`, `nse`) into registered provider instances.
2. **URL Safety & Normalization**:
   - Enforces strictly `http` and `https` schemes; rejects `file://`, `data:`, `ftp:`, and private localhost network loops.
   - Resolves relative links (`../files/report.pdf`) against the source page origin via `urllib.parse.urljoin`.
   - Strips URL fragments (`#page=1`) and marketing tracking parameters (`utm_*`, `fbclid`, `gclid`).
   - HTML entity decoding (`&amp;` -> `&`) and safe filename sanitization for Windows and POSIX file systems.
3. **PDF Detection**:
   - Triple-check detection:
     - URL suffix check (`.pdf`)
     - HTTP `Content-Type` response header (`application/pdf`, `application/x-pdf`, `binary/octet-stream`)
     - Stream header magic bytes validation (`%PDF-` in the first 1024 bytes).
4. **Streaming Download Flow & Size Enforcement**:
   - Streaming HTTP chunked downloads via `httpx.stream("GET", ...)` (default 64 KB chunk buffer).
   - Enforces configurable maximum file size limit (`DOWNLOAD_MAX_SIZE_MB`, default 100 MB).
   - Writes to staging directory (`data/downloads/.staging`) and calculates SHA-256 fingerprint on the fly without holding the full file in system RAM.
5. **Two-Tier Deduplication**:
   - **Tier 1 (URL-Level)**: If candidate URL is already registered in `documents` for the company, skip download immediately.
   - **Tier 2 (Content SHA-256)**: If downloaded file's SHA-256 matches an existing row in `documents.file_hash`, delete the staging file, log `DUPLICATE_DETECTED`, and reuse existing record.
6. **Document Lifecycle States**:
   $$\text{DISCOVERED} \to \text{DOWNLOADING} \to \text{DOWNLOADED} \quad (\text{or } \text{DUPLICATE} \ / \ \text{FAILED})$$
7. **Automation Run Integration**:
   - Executes via `POST /api/automations/{automation_id}/run`.
   - Populates `automation_runs` with `documents_discovered`, `documents_downloaded`, `documents_processed`, and `error_message`.
   - Writes audit logs into `processing_logs` (`DISCOVERY_STARTED`, `DISCOVERY_COMPLETED`, `DOWNLOAD_STARTED`, `DOWNLOAD_COMPLETED`, `DUPLICATE_DETECTED`, `DOWNLOAD_FAILED`) without logging sensitive tokens or credentials.

---

## 10. Document Processing Architecture

### Upgrade from PyPDF to PyMuPDF + Tesseract OCR

```
                      Raw PDF File (data/downloads/*.pdf)
                                      │
                                      ▼
                        Compute SHA-256 Digest
                         Check Duplicate in DB
                                      │
                         [Unique Document Verified]
                                      │
                                      ▼
                        PyMuPDF (fitz.open(path))
                                      │
                                      ▼
                       Extract Text from Each Page
                                      │
                                      ▼
                   Evaluate Text Quality (Word Density)
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
         Word Count >= 30                          Word Count < 30
          (Digital PDF)                             (Scanned Page)
                 │                                         │
                 │                                         ▼
                 │                              Render Page to Image
                 │                                (fitz.Pixmap -> PIL)
                 │                                         │
                 │                                         ▼
                 │                              pytesseract.image_to_string()
                 │                              (OCR Fallback Text)
                 │                                         │
                 └────────────────────┬────────────────────┘
                                      │
                                      ▼
                         Clean & Normalize Text
                                      │
                                      ▼
                          Sliding Window Chunker
                    (CHUNK_SIZE=1200, CHUNK_OVERLAP=200)
                                      │
                                      ▼
                        Persist Chunks to MySQL
                 (document_id, chunk_index, page_start, page_end)
```

### Key Technical Advantages on Hardware:
- **PyMuPDF (`fitz`)**: Written in C, executes text extraction in milliseconds per page without creating heavy Python object hierarchies. Consumes `< 50 MB` RAM even on a 300-page Annual Report.
- **Selective OCR**: Only executes Tesseract on pages where word count is below threshold (`OCR_FALLBACK_MIN_WORDS = 20`), avoiding unnecessary CPU spikes on native digital PDFs.

---

## 11. LLM Provider Architecture

### Decoupled Abstraction

```python
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text completion."""
        pass

    @abstractmethod
    def generate_structured(self, prompt: str, schema: Type[BaseModel], system: Optional[str] = None) -> BaseModel:
        """Generate structured completion validated against Pydantic schema."""
        pass

    @abstractmethod
    def check_availability(self) -> Dict[str, Any]:
        """Verify provider availability."""
        pass
```

### Initial Implementation: `OllamaProvider` (Qwen3 4B)
- **Model**: `qwen3:4b` (Q4_K_M quantization).
- **RAM footprint**: ~2.8 GB VRAM / System RAM.
- **Inference Speed**: ~25–35 tokens/sec on Intel Core i3 12th-Gen CPU (4 threads).
- **Configuration**: Strictly read from `settings.OLLAMA_MODEL`. Never hardcoded in business logic.
- **Structured Output**: Invokes Ollama with `format="json"` and parses the response into Pydantic models.

### Future Providers
Adding `OpenAIProvider`, `AnthropicProvider`, or `GeminiProvider` simply requires implementing `LLMProvider`. No document scrapers, chunkers, or database repositories will ever need modification.

---

## 12. Research / RAG Architecture

### Grounded Context Assembly
1. **Primary Ground Truth**: Facts are queried from MySQL `financial_metrics`, `risk_factors`, and `document_chunks`.
2. **Secondary Index Traversal**: The in-memory `KnowledgeGraph` identifies multi-hop relationships (e.g., *Company $\to$ Concall $\to$ Strategic CapEx Guidance*).
3. **Provenance & Zero-Hallucination**:
   - Every metric statement includes `[Source: {file_name}, Page {page_number}, SHA-256: {hash[:12]}]`.
   - The system prompt strictly limits the LLM to facts explicitly stated in the context.
4. **Deterministic Fallback**: If Ollama is offline or CPU utilization is saturated, `GraphRAGEngine` synthesizes a formatted, structured summary directly from MySQL/Graph triples with zero LLM inference.

---

## 13. Browser Extension Future Architecture

The V2 backend will include an extension-ready ingestion endpoint:

```
Chrome / Firefox Extension (Future)
  │ Reads company name, ticker, active URL from Screener/BSE/Moneycontrol/IR page
  ▼
POST /api/sources/external
  {
    "company_name": "Tata Motors Ltd",
    "ticker": "TATAMOTORS",
    "source_type": "screener",
    "source_url": "https://www.screener.in/company/TATAMOTORS/consolidated/",
    "auto_create_automation": true
  }
  │
  ▼
FastAPI Backend
  1. Calls CompanyRepository.get_or_create(...)
  2. Registers CompanySource record
  3. Creates an Automation workflow
  4. Dispatches an immediate background AutomationRun
  5. Returns { "status": "queued", "company_id": 12, "run_id": 45 }
```

---

## 14. API Evolution

### Existing V1 Endpoints (Retained)
- `GET /api/health`: System health and MySQL/storage status.
- `GET /api/companies`: List company summary cards.
- `GET /api/companies/{company_id}`: Full company dossier.
- `GET /api/documents`: List filings and status.
- `GET /api/documents/{document_id}/download`: Stream original PDF.
- `GET /api/export/excel/{company_id}`: Stream 4-sheet formatted Excel workbook.
- `GET /api/export/csv/{company_id}`: Stream financial CSV.
- `GET /api/graph` & `GET /api/graph/{company_id}`: Knowledge Graph JSON & visualizer page.
- `POST /api/graph/rebuild`: Force graph re-compilation from MySQL.
- `POST /api/ask`: Graph RAG question answering.
- `POST /api/scrape/search`: Screener ticker resolution.

### New V2 Endpoints (To Add)
- `POST /api/companies`: Manually register a new company.
- `GET /api/companies/{id}/sources`: List configured data sources.
- `POST /api/companies/{id}/sources`: Add a new data source (IR URL, BSE, etc.).
- `GET /api/automations`: List all automation workflows.
- `POST /api/automations`: Create new scheduled or manual automation.
- `POST /api/automations/{id}/run`: Trigger immediate manual execution ("Run Now").
- `GET /api/runs`: List historical automation runs with statuses.
- `GET /api/runs/{id}`: Detailed run progress, stages, and error logs.
- `POST /api/runs/{id}/retry`: Retry a failed automation run.
- `POST /api/sources/external`: Browser extension ingestion endpoint.

---

## 15. Frontend Evolution

### Strategy
The existing glassmorphic dashboard (`frontend/index.html`, `frontend/app.js`) and Knowledge Graph Visualizer (`frontend/graph.html`) will remain **100% functional** throughout Phase 1–6.

### Incremental UI Additions (Phase 7):
1. **Automations Tab / Panel**:
   - Table of active workflows with toggle switches, schedule badges, and "Run Now" buttons.
2. **Job History & Live Progress Drawer**:
   - Shows observable stages (`DISCOVERED` $\to$ `DOWNLOADING` $\to$ `EXTRACTING` $\to$ `STORED`).
   - Displays error callouts directly from `processing_logs`.
3. **Multi-Source Configuration Modal**:
   - Allows users to add official investor relations URLs, BSE tickers, or custom PDF links per company.

---

## 16. Migration Strategy

The migration must be executed **in-place** with zero downtime or data loss:

1. **Non-Destructive Database Migration**:
   - Create `app/database/migrations/schema_v2.sql` containing `CREATE TABLE IF NOT EXISTS` for the 4 new tables (`company_sources`, `automations`, `automation_runs`, `extraction_runs`) and non-destructive `ALTER TABLE` statements for existing tables.
   - Run via updated `run.py --migrate`.
2. **Repository Backward Compatibility**:
   - All existing repository methods retain their exact signatures. New methods (`create_source`, `create_automation`, etc.) are added alongside existing ones.
3. **Test Suite Integrity**:
   - Existing 28 tests in `tests/` must continue to pass at every stage.
   - New unit tests will be added incrementally per phase.

---

## 17. Development Phases

| Phase | Focus Area | Deliverables |
| :--- | :--- | :--- |
| **Phase 1** (Current) | **Architectural Assessment & Migration Plan** | Detailed codebase review, `docs/V2_ARCHITECTURE_PLAN.md`, validation of baseline. |
| **Phase 2** | **Relational Schema & Repository Layer** | `schema_v2.sql`, 4 new tables, migration runner update, repositories for sources, automations, and runs. |
| **Phase 3** | **Multi-Source Scraping & Document Pipeline** | `BaseScraper`, PyMuPDF extractor, Tesseract OCR fallback, sliding-window chunker, SHA-256 deduplication. |
| **Phase 4** | **Structured AI Extraction & Validation** | Qwen3 4B Ollama integration, Pydantic extraction schemas, accounting validation rules. |
| **Phase 5** | **Lightweight Automation Engine & Jobs** | Background scheduler thread, `AutomationRunner`, `JobManager`, retry logic, stage logging. |
| **Phase 6** | **Research Assistant & Knowledge Graph** | Derived in-memory graph index, Graph RAG with verifiable page citations, offline synthesis. |
| **Phase 7** | **API Modularization & Frontend Evolution** | Modular FastAPI routers, Automations UI panel, job run viewer, browser extension backend hook. |

---

## 18. Risks and Technical Decisions

### 1. CPU-Only Local LLM Inference
- **Risk**: Running models $> 7\text{B}$ parameters on an Intel Core i3 causes high latency (30–90 seconds per prompt) and risks system out-of-memory.
- **Decision**: Standardize on **Qwen3 4B** (Q4_K_M quantization). It fits comfortably in ~2.8 GB RAM, executes in 2–4 seconds per chunk, and exhibits exceptional structured JSON extraction capabilities.

### 2. OCR Latency on Large Filings
- **Risk**: Running OCR on every page of a 200-page Annual Report on CPU would take 10+ minutes.
- **Decision**: Implement a **two-tier gatekeeper**: PyMuPDF extracts native text first. If word count per page $\ge 20$, OCR is bypassed entirely. OCR is triggered only for scanned, image-only pages.

### 3. Database Connection Contention
- **Risk**: Background automation jobs running concurrently with API requests could exhaust the MySQL connection pool (`MYSQL_POOL_SIZE = 5`).
- **Decision**: Keep the background automation scheduler strictly single-threaded with serialized job queues. A single worker thread checks out one connection, processes the job, and immediately returns it to the pool.

### 4. Preservation of V1 Working Features
- **Risk**: Large refactors often break existing endpoints, Excel exports, or frontend charts.
- **Decision**: Strictly additive development. No existing endpoint or repository method will be removed until its V2 successor is fully tested and verified against the existing 28-test suite.
