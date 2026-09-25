# Earnings Ingestion Pipeline

How a 10-Q filing goes from the SEC's servers to the dashboard.

---

## Overview

```
target_stocks table
       │
       ▼
edgar.py  ──── EDGAR Submissions API ────► FilingRecord list
       │                                   (ticker, CIK, accession number,
       │                                    period_end, filed_date)
       ▼
main.py ──── download / locate filing ───► PDF or iXBRL ZIP
       │
       ▼
extractors/  (Strategy pattern)
  ├── PalantirExtractor  ── pdfplumber + regex ──► raw financial figures
  └── MarvellExtractor   ── iXBRL ZIP + US-GAAP tag lookup ──► raw financial figures
       │
       ▼
models.py  ── Pydantic validation ──► EarningsReport
  (cross-field checks: gross_profit = revenue − COGS, balance sheet balances)
       │
       ├──► data/outputs/{TICKER}/FY{year}Q{quarter}.json  (local contract)
       ├──► S3 (if S3_BUCKET env var is set)
       └──► db.py ── upsert_report() ──► SQLite / PostgreSQL
                                               │
                                               ▼
                                         generate.py
                                         (static build → static/)
```

---

## Step 1 — Filing Discovery (`edgar.py`)

Before any extraction happens, the pipeline needs to know which filings exist and which are new.

### CIK lookup

Every company on EDGAR has a unique numeric identifier called a CIK (Central Index Key). `get_cik(ticker, conn)` resolves a ticker symbol to its 10-digit zero-padded CIK:

1. **Cache check**: if the `target_stocks` table already has a `cik` value for this ticker, return it immediately — no network call.
2. **EDGAR bulk file**: on a cache miss, fetches `https://www.sec.gov/files/company_tickers.json` — a single JSON file that maps every registered company to its CIK. Scans for a case-insensitive ticker match, then writes the result back to `target_stocks.cik` for future calls.

### New filing discovery

`get_new_filings(ticker, cik, since_date)` fetches the company's full submission history from:

```
https://data.sec.gov/submissions/CIK{cik}.json
```

It filters to `form = "10-Q"` entries and, if `since_date` is provided, skips any filing whose `reportDate` is on or before that date. Results are sorted oldest-first so the pipeline processes filings in chronological order.

The returned `FilingRecord` dataclass carries:

| Field | Example |
|---|---|
| `ticker` | `"PLTR"` |
| `cik` | `"0001321655"` |
| `accession_number` | `"0001321655-26-000012"` |
| `period_end` | `"2026-04-30"` |
| `filed_date` | `"2026-05-12"` |

### Rate limiting

EDGAR's fair-use policy allows up to 10 requests per second. `_rate_limited_get()` enforces this with a monotonic timer — it sleeps the remaining fraction of a 100ms window before each request.

---

## Step 2 — Extraction (`extractors/`)

The extractor package uses a **Strategy pattern**: a registry of extractors, each responsible for one company's filing format. `get_extractor(file_path)` scans the registry and returns the first one whose `can_handle()` returns `True`.

```python
# extractors/__init__.py
_REGISTRY = [
    PalantirExtractor(),
    MarvellExtractor(),
]
```

### PalantirExtractor

- **Input**: PDF (10-Q PDF downloaded from EDGAR or placed manually in `data/inputs/PLTR/`)
- **Library**: `pdfplumber` — extracts raw text from specific page numbers
- **Method**: regex patterns tuned to PLTR's label wording across Q1 2024 – Q2 2026
- **Fragile points**: label wording varies slightly between filings (parenthetical negatives, split line items, `$` presence). Patterns cover known variants; a new variant surfaces as a `Pattern not found` error — see the debugging guide in the main README.

### MarvellExtractor

- **Input**: iXBRL ZIP (downloaded from EDGAR; contains inline XBRL documents)
- **Library**: `zipfile` + `xml.etree.ElementTree`
- **Method**: US-GAAP tag lookup (e.g. `us-gaap:Revenues`, `us-gaap:GoodwillAndIntangibleAssetsDisclosureAbstract`). More reliable than regex because XBRL tags are standardized; the challenge is picking the right context (period, filing unit) when a tag appears multiple times.

### Adding support for a new company

1. Create `extractors/{company}.py` implementing `BaseExtractor`:
   - `can_handle(file_path) -> bool` — inspect the filename, cover page, or XBRL namespace to identify the company
   - `extract(file_path) -> EarningsReport` — parse the filing and return a populated model
2. Add an instance to `_REGISTRY` in `extractors/__init__.py`

Nothing else needs to change — `main.py` calls `get_extractor()` and is unaware of the implementation.

---

## Step 3 — Validation (`models.py`)

The raw figures from the extractor are fed into Pydantic models. Validation catches extraction errors before anything hits the database.

| Model | Cross-field check |
|---|---|
| `IncomeStatement` | `gross_profit == revenue − cost_of_revenue` (±$5K tolerance) |
| `BalanceSheet` | `total_assets == total_liabilities + total_equity` (±$500K tolerance) |

`EarningsReport` is the top-level model. All monetary values are in **thousands of USD** unless `units` says otherwise.

Fields are split into **required** (universal across all supported companies) and **optional** (company-specific). This means the same schema handles both PLTR's separate S&M/G&A lines and MRVL's combined SG&A line — optional fields that don't apply simply remain `None` and are excluded from the DB insert.

---

## Step 4 — Persistence (`db.py`)

### Backend selection

`init_db()` checks for `DB_HOST` in the environment:

- **Set** → connects to PostgreSQL using `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`
- **Not set** → opens a local SQLite file (default: `earnings.db`)

Both backends run from the same query layer (`_execute`, `_executemany`, `_ph`) which swaps `?` placeholders (SQLite) for `%s` (psycopg2) transparently.

### Schema

```
companies          (id, ticker, name, category)
earnings_reports   (id, company_id, period, period_end_date, filing_type, units)
financial_metrics  (id, report_id, statement, metric_name, value)
target_stocks      (ticker, name, category, cik, ingested)
```

`upsert_report()` writes to all three earnings tables in one transaction and marks the ticker as `ingested = true` in `target_stocks`. It uses `ON CONFLICT ... DO UPDATE` (upsert) so re-running the pipeline on the same period is safe.

### Contract JSON

Alongside the database write, `main.py` writes the full `EarningsReport` as JSON to `data/outputs/{TICKER}/FY{year}Q{quarter}.json`. This is the **canonical record** of what was extracted — useful for auditing, replaying into a different database, or debugging a bad parse without re-fetching the filing.

To replay a contract into the database without re-parsing the PDF:

```bash
python loader.py data/outputs/PLTR/FY2026Q2.json
# or from S3:
python loader.py s3://your-bucket/PLTR/10-Q/FY2026Q2.json
```

---

## Step 5 — Static Build (`generate.py`)

After every ingestion run, `main.py` calls `generate.py` to rebuild the static site into `static/`. This is what Cloudflare Pages actually serves.

`generate.py` spins up Flask's test client with `STATIC_BUILD=true`, hits every API route, and writes the responses as flat files:

| Output file | Source route |
|---|---|
| `static/api/revenue.json` | `GET /api/revenue` |
| `static/api/tickers.json` | `GET /api/tickers` |
| `static/api/metrics/{TICKER}.json` | `GET /api/metrics/{ticker}` |
| `static/api/news.json` | `GET /api/news` |
| `static/index.html` | `GET /` |
| `static/earnings/index.html` | `GET /` |
| `static/news/index.html` | `GET /news` |

Templates use a `{{ API_EXT }}` variable injected at build time: in development this is empty (routes hit Flask directly), in the static build it resolves to `.json` so `fetch("/api/revenue")` becomes `fetch("/api/revenue.json")`.

---

## The `target_stocks` Table

This table is the ingestion queue. It tracks which tickers are planned for ingestion and which have already been processed.

```sql
SELECT ticker, name, category, cik, ingested FROM target_stocks;
```

| Column | Purpose |
|---|---|
| `ticker` | Primary key (e.g. `PLTR`) |
| `name` | Display name |
| `category` | AI sector grouping (e.g. `Infrastructure`, `Applications`) |
| `cik` | Cached EDGAR CIK — populated on first `get_cik()` call |
| `ingested` | `1` once `upsert_report()` has run successfully for this ticker |

Use the built-in skills to query the queue:
- `/list-ingested-stocks` — what's already in the database
- `/pending-ingestion` — what's still waiting

---

## Running the Pipeline

### Ingest a single filing (PDF on disk)

```bash
python main.py data/inputs/PLTR/your-10-Q.pdf
```

### Check for new filings via EDGAR and ingest them

`edgar.py` is a library module — there's no standalone runner yet. To drive it from a script:

```python
from db import init_db
from edgar import get_cik, get_new_filings

conn = init_db()
ticker = "PLTR"
cik = get_cik(ticker, conn)
filings = get_new_filings(ticker, cik, since_date="2026-06-30")
for f in filings:
    print(f.period_end, f.accession_number)
    # download the filing, then: python main.py path/to/filing
```

### Debugging a parse failure

```
ERROR during extraction: Pattern not found: 'Some label pattern here'
```

Open a Python shell and print the raw page text to see the actual label wording:

```python
import pdfplumber
with pdfplumber.open("data/inputs/PLTR/your-10-Q.pdf") as pdf:
    print(pdf.pages[3].extract_text())   # income statement
    print(pdf.pages[2].extract_text())   # balance sheet
```

Find the label that doesn't match, update the regex in `extractors/palantir.py`, and re-run.
