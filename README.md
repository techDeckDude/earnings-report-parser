# Earnings Report Parser

A pipeline that extracts structured financial data from SEC 10-Q PDF filings, validates it with Pydantic, uploads a normalized contract JSON to S3, and persists data to SQLite (local) or PostgreSQL (cloud). Built and tested against Palantir Technologies Q1 2025–Q2 2026.

## Table of Contents

- [Usage](#usage)
- [How It Works](#how-it-works)
  - [1. Extraction](#1-extraction-extractors)
  - [2. Validation](#2-validation-modelspy)
  - [3. Database](#3-database-dbpy)
  - [4. Orchestration](#4-orchestration-mainpy)
  - [5. Contract Loader](#5-contract-loader-loaderpy)
  - [5. Web Dashboard](#5-web-dashboard-apppy--templates)
  - [6. News Ingestion](#6-news-ingestion-ingest_newspy)
  - [7. News Scheduler](#7-news-scheduler-schedulerpy)
- [Project Structure](#project-structure)
- [Experimental Features](#experimental-features)
- [Deployment](#deployment)
- [Workflow: How to Ingest a New Quarterly Report](#workflow-how-to-ingest-a-new-quarterly-report)
- [Design Patterns & Infrastructure](#design-patterns--infrastructure)
- [Known Limitations](#known-limitations)
- [Changelog](#changelog)

## Usage

```bash
pip install pdfplumber pydantic flask boto3 psycopg2-binary
# Place the PDF in data/inputs/{TICKER}/ first, then:
python main.py data/inputs/PLTR/your-10-Q.pdf
```

This produces:
- Console output with a formatted financial summary
- A normalized contract JSON written locally alongside the PDF
- The contract uploaded to S3 (when `S3_BUCKET` env var is set)
- Data persisted to SQLite locally, or PostgreSQL when `DB_HOST` is set

**To replay a contract from S3 into the database:**
```bash
python loader.py s3://financial-statements/PLTR/10-Q/FY2026Q2.json
# or from a local file:
python loader.py path/to/contract.json
```

## How It Works

The pipeline runs in two stages connected by a normalized contract JSON:

```
PDF → extractor.py → models.py → contract JSON → S3
                          ↓                    (audit trail / replay)
                    validation error
                    (stops the run)

contract JSON → loader.py → db.py → SQLite or Postgres
```

`main.py` runs both stages in sequence. `loader.py` can run the second stage independently from an existing S3 contract, without re-touching the original PDF.

### 1. Extraction (`extractors/`)

The extractor package uses a **Strategy pattern** to decouple the extraction interface from company-specific PDF formats:

- **`extractors/base.py`** — defines `BaseExtractor`, an abstract base class with two methods: `can_handle(cover_text) -> bool` and `extract(pdf_path) -> EarningsReport`.
- **`extractors/palantir.py`** — `PalantirExtractor` implements `BaseExtractor` with all Palantir-specific page numbers, regex patterns, and label variations.
- **`extractors/__init__.py`** — maintains a registry of extractor instances. `get_extractor(pdf_path)` reads the PDF cover page and returns the first registered extractor whose `can_handle()` returns `True`.

Adding support for a new company means creating a new file (e.g. `extractors/acme.py`), implementing `BaseExtractor`, and adding it to `_REGISTRY` — nothing else changes.

`PalantirExtractor` reads raw text from specific pages:

| Page (0-indexed) | Content |
|---|---|
| 2 | Balance Sheet |
| 3 | Income Statement |
| dynamic | Cash Flow Statement |

Each statement has its own extraction function using regex patterns to find known line-item labels. Dollar signs, commas, and parenthetical negatives (e.g. `(1,509,665)`) are normalized by `_parse_num`. The cash flow page is located dynamically by scanning the first 20 pages for a content anchor, since this page number varies across quarterly filings.

### 2. Validation (`models.py`)

The raw extracted numbers are passed into Pydantic models, which serve two purposes:

- **Type enforcement** — all values must be valid floats; missing or unparseable fields raise an error immediately
- **Cross-field validation** — two `@model_validator` checks catch silent extraction errors:
  - `IncomeStatement`: asserts `gross_profit == revenue - cost_of_revenue` (within a $5k rounding tolerance)
  - `BalanceSheet`: asserts `total_assets == total_liabilities + total_equity` (within a $500k tolerance)

If either check fails the run stops before anything is written to the database.

### 3. Database (`db.py`)

SQLite with six tables:

```
companies
  id, ticker, name, category

earnings_reports
  id, company_id → companies, period, period_end_date, filing_type, units

financial_metrics
  id, report_id → earnings_reports, statement, metric_name, value

news_runs
  id, run_at, period, total_headlines, score_distribution, weighted_sentiment, net_sentiment_label

news_articles
  id, run_id → news_runs, headline, source, url, url_verified,
  stocks_mentioned (JSON), sentiment_score, sentiment_label, summary,
  published_date (article publish date, used for week grouping)

target_stocks
  ticker (PK), name, category, cik (SEC CIK, cached), ingested (0/1), added_at
```

`financial_metrics` is a key-value store — every field from every Pydantic model is flattened into a `(statement, metric_name, value)` row. This makes it easy to add new metrics without schema changes.

All writes use `INSERT ... ON CONFLICT ... DO UPDATE`, so re-running against the same filing updates values in place rather than creating duplicates.

### 4. Orchestration (`main.py`)

Calls each step in sequence, prints a human-readable summary to stdout, writes the contract JSON locally, and uploads it to S3 if `S3_BUCKET` is set. The DB write uses Postgres when `DB_HOST` is set, SQLite otherwise — no code change required when switching environments.

### 5. Contract Loader (`loader.py`)

Reads a contract JSON from S3 (`s3://bucket/key`) or a local path, re-validates it with Pydantic, and upserts into the database. Useful for replaying ingestion without re-extracting the PDF — for example, after a schema migration or a database rebuild.

The S3 key format is `{ticker}/{filing_type}/FY{year}Q{quarter}.json` (e.g. `PLTR/10-Q/FY2026Q2.json`), making filings browsable by company and report type.

### 5. Web Dashboard (`app.py` + `templates/`)

A Flask web server that reads from the SQLite database and renders two interactive pages at `http://localhost:5001`.

**Routes:**
- **`GET /`** — earnings page (`earnings.html`): ticker search filter (press `/` to focus, `Enter` to jump to first match, `Esc` to clear) above a horizontally-scrollable ticker selector; scrollable metric pill row; scrollable metric line chart (fixed y-axis, per-quarter minimum spacing); and a full quarterly metrics table
- **`GET /api/revenue`** — revenue records for all companies as JSON
- **`GET /api/tickers`** — list of all known ticker symbols and company names
- **`GET /api/metrics/<ticker>`** — all financial metrics for a ticker, pivoted to `{statement: {metric_name: [value_per_period]}}` ordered by `period_end_date`
- **`GET /api/news`** — all news articles grouped into Mon–Sun calendar weeks, newest first; each week includes `week_start`, `week_end`, `period`, `headlines`, and dynamically-computed `summary_stats`
- **`GET /news`** — AI market news feed page; spacing and mobile layout aligned with the earnings page; reads from `/api/news`

New companies and periods appear automatically as more filings are parsed — no UI changes needed.

The app runs in two modes from a single codebase:

| Mode | How to run | API |
|---|---|---|
| **Live** | `python app.py` → `localhost:5001` | Flask routes hit SQLite in real time |
| **Static** | `python generate.py` → serve `static/` | Pre-built `.json` files (Cloudflare Pages) |

```bash
# Live mode (local dev)
python app.py

# Build static output
python generate.py

# Verify live and static are in sync
python verify.py

# Serve static locally to preview before deploying
python -m http.server 8080 --directory static
```

### 6. News Ingestion (`ingest_news.py`)

Fetches AI stock market headlines from the last ingested article date to today, then stores them in the database. Requires an `ANTHROPIC_API_KEY` with credits.

```bash
# Set your API key (add to .env or export directly)
export ANTHROPIC_API_KEY=sk-ant-...

# Fetch and store headlines (auto-detects date range from DB)
python ingest_news.py

# Dry run: print JSON without storing
python ingest_news.py --dry-run
```

The script reads `MAX(published_date)` from `news_articles` to determine the start of the next fetch window (last date + 1 day). On first run with an empty database, it defaults to the past 7 days. The date range is injected into the skill prompt so each article's `published_date` is constrained to the window. Articles are stored with their individual `published_date`.

The news page groups articles into Mon–Sun calendar weeks based on `published_date` (not ingestion time), so a single run covering multiple weeks will appear as separate carousel pages. The carousel shows the most recent week by default; use the PREV/NEXT buttons (or swipe on mobile) to navigate.

### 7. News Scheduler (`scheduler.py`)

Runs `ingest_news.py` automatically on a configurable interval. The interval is set via the `INGEST_INTERVAL_HOURS` env var (default `24`; supports fractional hours).

```bash
# Run in the foreground (logs to stdout)
python3 scheduler.py

# Custom interval (every 12 hours)
INGEST_INTERVAL_HOURS=12 python3 scheduler.py

# Every 10 seconds (for testing)
INGEST_INTERVAL_HOURS=0.0028 python3 scheduler.py
INGEST_INTERVAL_HOURS=0.0027 nohup python3 scheduler.py > logs/scheduler.log 2>&1 &

# Run in the background and log to file
mkdir -p logs
nohup python3 scheduler.py > logs/scheduler.log 2>&1 &

# Watch the log live
tail -f logs/scheduler.log

# Stop the scheduler
pkill -f earnings-news-scheduler
```

On startup, the scheduler runs ingestion immediately, then sleeps for the configured interval before the next run. Each run logs its start time, result, and the timestamp of the next scheduled run.

## Project Structure

```
earnings-report-parser/
├── main.py              # CLI entry point: extract → validate → save → summarize
├── edgar.py             # EDGAR API client: CIK lookup and 10-Q filing discovery for any ticker
├── extractors/
│   ├── __init__.py      # Registry and get_extractor() strategy selector
│   ├── base.py          # BaseExtractor abstract interface
│   ├── palantir.py      # Palantir 10-Q implementation (PDF via pdfplumber + regex)
│   ├── marvell.py       # Marvell Technology 10-Q implementation (iXBRL ZIP via tag lookup)
│   └── xbrl.py          # Tier 1 EDGAR XBRL extractor: maps US-GAAP concepts to EarningsReport for any XBRL filer
├── models.py            # Pydantic data models and validators
├── db.py                # SQLite schema and persistence
├── app.py               # Flask web server and API; injects STATIC_BUILD flag via context processor
├── generate.py          # Build static/ from live Flask (sets STATIC_BUILD=true, uses test client)
├── verify.py            # Diff live API responses against static JSON files; exits 1 on mismatch
├── add_stock.py         # CLI: add a ticker to target_stocks, resolve its CIK, and scan its EDGAR filing history in one command
├── scan_filings.py      # CLI: scan EDGAR 10-Q history for all target stocks — shows count, date range, years before ingestion; --save writes to DB
├── ingest_xbrl.py       # CLI: ingest 10-Q filings for any ticker via EDGAR XBRL API (no file download)
├── bulk_ingest.py       # CLI: ingest all target stocks with EDGAR XBRL data in one pass; logs per-ticker results and final summary
├── ingest_news.py       # CLI: fetch AI stock news via Claude (Anthropic SDK + web search), store in DB
├── scheduler.py         # Run ingest_news.py on a configurable interval (INGEST_INTERVAL_HOURS env var)
├── deploy.sh            # Deploy script: merge develop → main (code + build commits), tag, push to origin
├── templates/
│   ├── earnings.html    # Earnings page: ticker selector, metric chart, quarterly metrics table
│   └── news.html        # AI news feed: weekly carousel, sentiment chart, swipe nav
├── data/
│   ├── inputs/
│   │   ├── PLTR/        # Place 10-Q PDFs here before running main.py
│   │   └── MRVL/        # Place 10-Q iXBRL ZIPs here before running main.py
│   └── outputs/
│       ├── PLTR/        # Extracted contract JSONs (FY{year}Q{quarter}.json)
│       └── MRVL/        # Extracted contract JSONs (FY{year}Q{quarter}.json)
├── docs/
│   ├── ingestion-pipeline.md          # Full walkthrough of the earnings ingestion pipeline (EDGAR → extract → validate → DB → static build)
│   ├── aws-deployment.md              # Plan for deploying to S3 + EC2 + RDS
│   └── architecture-diagram-8-22-26.png  # Visual architecture diagram
├── loader.py            # Load a contract JSON from S3 or local path into the DB
├── experimental/
│   ├── __init__.py      # Flask Blueprint definition (url_prefix="/experimental")
│   └── routes.py        # Route handlers for experimental features
├── .claude/
│   └── agents/
│       └── news-aggregator.md  # Claude Code skill: fetch and sentiment-score AI stock headlines
├── CLAUDE.md            # AI agent rules for this project
├── CHANGELOG.md         # Chronological record of changes
└── README.md
```

## Experimental Features

The `experimental/` package is a Flask Blueprint mounted at `/experimental`. It is the designated place for prototype pages, mock-data UIs, and ideas under active exploration — features that are not yet part of the production surface.

**Currently experimental:**

| Route | Template | Description |
|---|---|---|
| `GET /news` | `templates/news.html` | AI market news feed with weekly carousel, 5-level sentiment scoring, and a sentiment line chart; reads live data via `GET /api/news` |

**Enabling / disabling:**

The Blueprint is on by default. Set `EXPERIMENTAL=0` to disable all experimental routes (e.g. in a production deploy or static build):

```bash
EXPERIMENTAL=0 python app.py
```

**Promoting a feature to production** means: move its template to `templates/`, add its route to `app.py`, wire it to the real backend, and remove the `{% if experimental %}` nav guards. The full checklist is in `CLAUDE.md`.

---

## Deployment

### Cloudflare Pages (current)

Run the deploy script from the `develop` branch:

```bash
./deploy.sh
```

This will:
1. Show you a preview of uncommitted changes and ask for confirmation
2. Merge `develop` → `main` (code changes commit)
3. Run `python generate.py` to rebuild the static site on `develop`
4. Commit the static files with a timestamped tag (e.g. `build-20260925-143022`)
5. Merge the build commit → `main`
6. Push `main` and the build tag to origin — Cloudflare picks up the push and deploys

The two-commit structure keeps code changes and generated output separate in the git history.

### AWS (planned)

See [docs/aws-deployment.md](docs/aws-deployment.md) for a full plan to deploy this project to AWS using S3 (PDF storage), EC2 (Flask + ingestion), and RDS PostgreSQL (replacing SQLite).

## Workflow: How to Ingest a New Quarterly Report

This section describes the full process — including the iterative debugging that is typically required — for getting a new 10-Q PDF to parse correctly and appear in the dashboard.

### Step 1: Run `main.py` against the new PDF

```bash
python main.py path/to/new-10-Q.pdf
```

The most common outcome on a brand-new filing is an extraction error printed to stderr:

```
ERROR during extraction: Pattern not found: 'Some label pattern here'
```

This means a regex in `extractor.py` couldn't find the expected label text on the page it was looking at. This is normal — SEC filings use slightly different label wording across companies and across years.

### Step 2: Debug by printing the actual page text

Open a Python shell or scratch script and print the raw text from the relevant page:

```python
import pdfplumber

with pdfplumber.open("path/to/new-10-Q.pdf") as pdf:
    print(pdf.pages[3].extract_text())  # page 3 = income statement
    print(pdf.pages[2].extract_text())  # page 2 = balance sheet
    # cash flow: scan pages 5-10 manually if needed
```

Look for the line that should match the failing pattern. The actual text will usually be slightly different — a missing `$`, a word order change, a negative in parentheses instead of with a minus sign, or a line item that's split across two rows instead of one.

### Step 3: Fix the regex in `extractor.py`

Common failure modes encountered so far and how they were fixed:

| Problem | Example | Fix |
|---|---|---|
| Parenthetical negative | `(3,173)` instead of `3,173` | Change `([\d,]+)` to `(\([\d,]+\)\|[\d,]+)` |
| Optional `$` sign | `Total assets 10,199,183` vs `Total assets $ 10,199,183` | Change `\$\s*` to `\$?\s*` |
| Split line items | `Accounts payable` and `Accrued liabilities` on separate rows | Add a fallback in `_find_accounts_payable` that sums both |
| Different label wording | `Net earnings per share` vs `Earnings per share` | Use `(?:Net )?` to make the prefix optional |
| Wrong page | Cash flow on page 7 (index 6) vs page 8 (index 7) | Use `_find_cf_page()` which scans dynamically |

After fixing a pattern, re-run `main.py`. Repeat until the run completes with "Validation passed" and "Saved as report_id=N".

### Step 4: Verify in the dashboard

Reload `http://localhost:5001` — the new filing should appear as a new row in the revenue table automatically. No dashboard changes needed; the UI pulls all data fresh from the DB on each load.

### Step 5: Commit

Per the project rules in `CLAUDE.md`, update this README to reflect any extractor changes (e.g. add the new failure mode to the table above), then commit.

---

### What "compatible" means in practice

The extractor will work on a new filing without any changes if:
- The income statement is on page 4 (index 3) and the balance sheet is on page 3 (index 2)
- All line item labels use the same wording as a previously tested filing
- Dollar amounts appear in the same column position (first number after the label)

It will likely need a small fix if the filing is from a different company, a different fiscal year where label wording changed, or the page count of the document shifts the financial statement locations.

---

## Known Limitations

- **`PalantirExtractor` page numbers are hardcoded** (balance sheet index 2, income statement index 3) — reliable across all tested PLTR filings but specific to their layout
- **Column order is assumed** — the income statement has four columns (current quarter, prior quarter, YTD, prior YTD); the regex always captures the first, which is the current quarter
- **`PalantirExtractor` is PDF/regex-only** — adding another PDF-based company requires its own subclass
- **MRVL cash flow is YTD, not quarterly** — Marvell files the cash flow statement as a year-to-date figure in their 10-Q; individual quarter CF is not directly available without subtracting prior periods

Tested and working against: PLTR Q1 2025–Q2 2026; MRVL Q1 2024–Q1 2027.

---

## Design Patterns & Infrastructure

### Design Patterns

| Pattern | Where Applied | Purpose |
|---|---|---|
| **Strategy** | `extractors/` — `BaseExtractor` ABC + per-company subclasses (`PalantirExtractor`, `MarvellExtractor`), `get_extractor()` registry | Decouple parsing logic from the orchestrator; new company = new file, nothing else changes |
| **Experimental Blueprint** | `experimental/` Flask Blueprint mounted at `/experimental` | Isolate prototype features (mock data, unvalidated UI) from the production surface; controlled by `EXPERIMENTAL` env var; see `CLAUDE.md` for the promotion checklist |
| **S3 Contract / Landing Zone** | `main.py` → `data/outputs/{ticker}/FY{year}Q{quarter}.json` → S3 → `loader.py` → DB | Decouple extraction from loading; contracts are the durable intermediate record; DB can be rebuilt from S3 without re-parsing PDFs |
| **Repository** | `db.py` — `upsert_report()`, `init_db()` | Isolate all DB read/write logic; callers (`main.py`, `loader.py`, `app.py`) never write SQL directly |
| **Dual-backend detection** | `db.py` — `isinstance(conn, sqlite3.Connection)` | Single codebase supports SQLite (local dev) and PostgreSQL (cloud) with no code changes; switching is env-var-driven |

### Infrastructure

| Layer | Technology | Notes |
|---|---|---|
| PDF parsing | `pdfplumber` | Used by `PalantirExtractor`; text extraction from specific pages |
| iXBRL parsing | `zipfile` + `re` | Used by `MarvellExtractor`; extracts US-GAAP tagged values directly from iXBRL HTML; no page-position assumptions |
| Data validation | `Pydantic v2` | Schema enforcement + cross-field math checks (gross profit, balance sheet equation) |
| Local database | `SQLite` | Default; auto-initialized at `earnings.db`; no env vars needed |
| Cloud database | `PostgreSQL` (via `psycopg2`) | Enabled when `DB_HOST` env var is set |
| Contract storage | `AWS S3` (via `boto3`) | Enabled when `S3_BUCKET` env var is set; key format `{ticker}/{filing_type}/FY{year}Q{quarter}.json` |
| Web server | `Flask` | Serves dashboard at `localhost:5001`; routes: `/`, `/api/revenue`, `/api/tickers`, `/api/metrics/<ticker>` |
| Fonts | `IBM Plex Mono` + `IBM Plex Sans` (Google Fonts) | Terminal aesthetic: mono for all UI chrome (nav, labels, values), sans-serif for body text |
| Schema versioning | `schema_version: "1.0"` on `EarningsReport` | Lets `loader.py` detect and reject stale contract formats |

### Environment Variables

| Variable | Effect |
|---|---|
| `S3_BUCKET` | If set, `main.py` uploads the contract JSON to this S3 bucket after extraction |
| `DB_HOST` | If set, `db.py` connects to PostgreSQL instead of local SQLite |
| `DB_NAME` | PostgreSQL database name (default: `earningsdb`) |
| `DB_USER` | PostgreSQL username |
| `DB_PASSWORD` | PostgreSQL password |
| `DB_PORT` | PostgreSQL port (default: `5432`) |
| `PORT` | Flask dev server port (default: `5001`); set automatically by the preview server when `autoPort: true` |
| `EXPERIMENTAL` | Mount the experimental Blueprint (default: `1` = enabled); set `0` to disable all `/experimental/*` routes in production |

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
