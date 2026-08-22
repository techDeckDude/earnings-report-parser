# Earnings Report Parser

A pipeline that extracts structured financial data from SEC 10-Q PDF filings, validates it with Pydantic, uploads a normalized contract JSON to S3, and persists data to SQLite (local) or PostgreSQL (cloud). Built and tested against Palantir Technologies Q1 2025–Q2 2026.

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

SQLite with three tables:

```
companies
  id, ticker, name

earnings_reports
  id, company_id → companies, period, period_end_date, filing_type, units

financial_metrics
  id, report_id → earnings_reports, statement, metric_name, value
```

`financial_metrics` is a key-value store — every field from every Pydantic model is flattened into a `(statement, metric_name, value)` row. This makes it easy to add new metrics without schema changes.

All writes use `INSERT ... ON CONFLICT ... DO UPDATE`, so re-running against the same filing updates values in place rather than creating duplicates.

### 4. Orchestration (`main.py`)

Calls each step in sequence, prints a human-readable summary to stdout, writes the contract JSON locally, and uploads it to S3 if `S3_BUCKET` is set. The DB write uses Postgres when `DB_HOST` is set, SQLite otherwise — no code change required when switching environments.

### 5. Contract Loader (`loader.py`)

Reads a contract JSON from S3 (`s3://bucket/key`) or a local path, re-validates it with Pydantic, and upserts into the database. Useful for replaying ingestion without re-extracting the PDF — for example, after a schema migration or a database rebuild.

The S3 key format is `{ticker}/{filing_type}/FY{year}Q{quarter}.json` (e.g. `PLTR/10-Q/FY2026Q2.json`), making filings browsable by company and report type.

### 5. Web Dashboard (`app.py` + `templates/index.html`)

A Flask web server that reads from the SQLite database and renders an interactive revenue dashboard at `http://localhost:5001`.

- **`GET /`** — serves the dashboard HTML
- **`GET /api/revenue`** — returns all revenue records as JSON, joined across `companies`, `earnings_reports`, and `financial_metrics`

The dashboard shows a revenue table with one row per company per period — new companies and periods appear automatically as more filings are parsed.

To start the dashboard:

```bash
python app.py
# then open http://localhost:5001
```

## Project Structure

```
earnings-report-parser/
├── main.py              # CLI entry point: extract → validate → save → summarize
├── extractors/
│   ├── __init__.py      # Registry and get_extractor() strategy selector
│   ├── base.py          # BaseExtractor abstract interface
│   └── palantir.py      # Palantir 10-Q implementation of BaseExtractor
├── models.py            # Pydantic data models and validators
├── db.py                # SQLite schema and persistence
├── app.py               # Flask web server and API
├── templates/
│   └── index.html       # Revenue dashboard
├── data/
│   ├── inputs/
│   │   └── PLTR/        # Place 10-Q PDFs here before running main.py
│   └── outputs/
│       └── PLTR/        # Extracted contract JSONs (FY{year}Q{quarter}.json)
├── docs/
│   ├── aws-deployment.md              # Plan for deploying to S3 + EC2 + RDS
│   └── architecture-diagram-8-22-26.png  # Visual architecture diagram
├── loader.py            # Load a contract JSON from S3 or local path into the DB
├── CLAUDE.md            # AI agent rules for this project
└── README.md
```

## Deployment

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
- **Only Palantir is implemented** — adding a new company requires writing a new `BaseExtractor` subclass in `extractors/`

Tested and working against: PLTR Q1 2025, Q2 2025, Q3 2025, Q1 2026, Q2 2026.

---

## Design Patterns & Infrastructure

### Design Patterns

| Pattern | Where Applied | Purpose |
|---|---|---|
| **Strategy** | `extractors/` — `BaseExtractor` ABC + per-company subclasses, `get_extractor()` registry | Decouple PDF parsing logic from the orchestrator; new company = new file, nothing else changes |
| **S3 Contract / Landing Zone** | `main.py` → `data/outputs/{ticker}/FY{year}Q{quarter}.json` → S3 → `loader.py` → DB | Decouple extraction from loading; contracts are the durable intermediate record; DB can be rebuilt from S3 without re-parsing PDFs |
| **Repository** | `db.py` — `upsert_report()`, `init_db()` | Isolate all DB read/write logic; callers (`main.py`, `loader.py`, `app.py`) never write SQL directly |
| **Dual-backend detection** | `db.py` — `isinstance(conn, sqlite3.Connection)` | Single codebase supports SQLite (local dev) and PostgreSQL (cloud) with no code changes; switching is env-var-driven |

### Infrastructure

| Layer | Technology | Notes |
|---|---|---|
| PDF parsing | `pdfplumber` | Text extraction from specific pages; cash flow page discovered dynamically |
| Data validation | `Pydantic v2` | Schema enforcement + cross-field math checks (gross profit, balance sheet equation) |
| Local database | `SQLite` | Default; auto-initialized at `earnings.db`; no env vars needed |
| Cloud database | `PostgreSQL` (via `psycopg2`) | Enabled when `DB_HOST` env var is set |
| Contract storage | `AWS S3` (via `boto3`) | Enabled when `S3_BUCKET` env var is set; key format `{ticker}/{filing_type}/FY{year}Q{quarter}.json` |
| Web server | `Flask` | Serves dashboard at `localhost:5001`; single `/api/revenue` JSON endpoint |
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

---

## Changelog

- **2026-08-22** — Organized input/output files into `data/inputs/{ticker}/` and `data/outputs/{ticker}/` structure; `main.py` now writes contract JSONs there automatically
- **2026-08-22** — Refactored extractor to Strategy pattern: `extractors/base.py` defines the `BaseExtractor` interface, `extractors/palantir.py` holds all PLTR-specific logic, `get_extractor()` selects the right implementation at runtime from the cover page
- **2026-08-22** — Added architecture diagram to `docs/`
- **2026-08-14** — Implemented S3 contract pattern: extraction now uploads a normalized JSON to S3; added `loader.py` to replay contracts into the DB without re-parsing PDFs; added PostgreSQL support via `psycopg2` with env-var-driven backend detection
- **2026-08-12** — Added AWS deployment documentation (`docs/aws-deployment.md`) covering S3 + EC2 + RDS setup
- **2026-08-12** — Added end-to-end ingestion workflow to README including common failure modes and debugging steps
- **2026-08-12** — Fixed extractor to handle label variations across Q1 2025–Q2 2026 filings (parenthetical negatives, optional `$`, split accounts payable, EPS label wording, dynamic cash flow page)
- **2026-08-12** — Removed bar chart from dashboard; revenue table only
- **2026-08-12** — Added Flask web dashboard (`app.py` + `templates/index.html`) serving revenue data from SQLite
- **2026-08-12** — Initial prototype: PDF → `pdfplumber` extraction → Pydantic validation → SQLite persistence
