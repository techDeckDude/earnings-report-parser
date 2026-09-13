# Scaled 10-Q Ingestion Pipeline

**Status**: Planned — not yet implemented  
**Branch**: develop  
**Goal**: Automate discovery, extraction, validation, and loading of 10-Q filings for all 100 companies in `target_stocks`, without writing per-company parsers.

---

## Core Insight: The EDGAR XBRL API

The SEC provides structured financial data for every public XBRL filer at no cost:

```
https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
```

This returns all historical financials for a company, already tagged with US-GAAP concept names — no PDF parsing, no regex, no AI extraction required for the primary path. All 100 companies in `target_stocks` are large-cap XBRL filers. This covers ~95% of required data with a single generic mapper, making per-company extractors the exception rather than the rule.

---

## Pipeline Overview

```
EDGAR API
    │
    ├── Phase 1: Discovery
    │     CIK lookup (ticker → CIK, cached)
    │     Filing discovery (new 10-Qs since last ingested period)
    │
    ├── Phase 2: Extraction
    │     Tier 1 — EDGAR Company Facts API   (initial implementation)
    │     Tier 2 / Tier 3 — deferred pending success rate review
    │
    ├── Phase 3: Normalization
    │     Map extracted values → EarningsReport (Pydantic)
    │     Tag with extraction source + raw values for audit
    │
    ├── Phase 4: Validation
    │     Layer A — Accounting identities (hard constraints)
    │     Layer B — Temporal sanity checks (soft constraints)
    │     Layer C — Cross-source reconciliation
    │
    └── Phase 5: Load
          passed   → upsert_report() → DB, mark target_stocks.ingested = 1
          flagged  → pipeline_runs log, surface for review
          rejected → pipeline_runs log, error details
```

---

## Phase 1: Discovery (`edgar.py`)

**Responsibilities**:
1. **CIK lookup** — resolve a ticker symbol to the SEC's Central Index Key (CIK). One-time per company; cached in a new `target_stocks.cik` column.
   - Endpoint: `https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt=2020-01-01&forms=10-Q`
   - Or via the company tickers JSON: `https://www.sec.gov/files/company_tickers.json`

2. **Filing discovery** — find 10-Q filings filed after the company's last ingested period.
   - Endpoint: `https://data.sec.gov/submissions/CIK{cik}.json`
   - Returns full filing history with `form`, `filingDate`, `accessionNumber`, `reportDate`
   - Filter: `form == "10-Q"` and `reportDate > last_ingested_period_end`

**Output**: A queue of `(ticker, cik, accession_number, period, filed_date)` tuples.

**Rate limit**: EDGAR allows 10 requests/second. The pipeline respects this with a simple throttle.

---

## Phase 2: Extraction

**Initial implementation: Tier 1 only.** We will build and ship the EDGAR Company Facts API extractor, measure its real-world success rate across the 100 target stocks, and revisit Tier 2 (iXBRL document parsing) and Tier 3 (Claude AI extraction) only if the data shows meaningful gaps.

### Tier 1 — EDGAR Company Facts API

- **Endpoint**: `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`
- Returns all historical financials structured as:
  ```json
  {
    "facts": {
      "us-gaap": {
        "Revenues": {
          "units": { "USD": [{ "end": "2024-01-28", "val": 22103000000, "form": "10-Q", "fp": "Q3", "fy": 2024 }] }
        }
      }
    }
  }
  ```
- A **generic US-GAAP concept map** (`extractors/xbrl.py`) maps concept names to `EarningsReport` fields:

  | US-GAAP Concept | EarningsReport Field |
  |---|---|
  | `Revenues` / `RevenueFromContractWithCustomerExcludingAssessedTax` | `revenue` |
  | `CostOfRevenue` / `CostOfGoodsAndServicesSold` | `cost_of_revenue` |
  | `GrossProfit` | `gross_profit` |
  | `ResearchAndDevelopmentExpense` | `research_and_development` |
  | `SellingGeneralAndAdministrativeExpense` | `sg_and_a` |
  | `OperatingIncomeLoss` | `operating_income` |
  | `NetIncomeLoss` | `net_income` |
  | `EarningsPerShareBasic` | `eps_basic` |
  | `EarningsPerShareDiluted` | `eps_diluted` |
  | `CashAndCashEquivalentsAtCarryingValue` | `cash_and_equivalents` |
  | `Assets` | `total_assets` |
  | `Liabilities` | `total_liabilities` |
  | `StockholdersEquity` | `total_equity` |
  | `NetCashProvidedByUsedInOperatingActivities` | `operating_cash_flow` |
  | `PaymentsToAcquirePropertyPlantAndEquipment` | `capital_expenditures` |

- Many companies use alternate concept names for the same metric; the mapper tries a priority-ordered list of aliases per field.
- Filter records by `form = "10-Q"` and the target `reportDate`.
- Every extraction records `extraction_tier = "edgar_api"` for tracking in `pipeline_runs`.

**Success tracking**: The `pipeline_runs` table records which fields were populated vs. null for every run. After ingesting the initial batch of target stocks, we will review the null rates per field to determine whether Tier 2 or Tier 3 is warranted.

### Future Tiers (deferred)

| Tier | Strategy | Trigger to implement |
|---|---|---|
| Tier 2 | iXBRL document parser | Tier 1 null rate > 10% on any required field |
| Tier 3 | Claude AI extraction | Companies that don't file XBRL, or Tier 2 still insufficient |

---

## Phase 3: Normalization

The existing `EarningsReport` Pydantic model is the contract. Two additions:

- **`extraction_source: str`** — which tier produced this record (`"edgar_api"` | `"ixbrl"` | `"claude"`)
- **`raw_values: dict`** — the unmapped source values before normalization (for audit and debugging)

Output is the same JSON contract uploaded to S3 and loaded into the DB via `loader.py`. No changes to the load path.

---

## Phase 4: Validation (`validate.py`)

Three layers. All must pass for a record to load automatically.

### Layer A — Accounting Identities (hard constraints)

Failure = record rejected outright.

```
Gross Profit       = Revenue − Cost of Revenue          (±0.5% tolerance)
Operating Income   ≈ Gross Profit − R&D − SG&A          (±1% tolerance)
Net Income         ≈ Operating Income + non-op items     (±2% tolerance)
Total Assets       = Total Liabilities + Total Equity    (±0.1% tolerance)
Free Cash Flow     = Operating Cash Flow − CapEx
```

Tolerances account for rounding in reported figures.

### Layer B — Temporal Sanity (soft constraints)

Failure = record flagged for human review, not rejected.

- No metric moves more than 5× QoQ without an acquisition/divestiture annotation
- Revenue cannot be negative
- Gross margin stays within the company's historical ±20 percentage point range
- EPS sign matches Net Income sign

### Layer C — Cross-Source Reconciliation

Only runs when multiple tiers extracted data for the same period.

- Tier 1 and Tier 2 values for the same field must agree within 1%
- Discrepancy → record flagged, both values logged for review

### Validation Output

Each record gets:
- **`validation_status`**: `passed` | `flagged` | `rejected`
- **`confidence_score`**: 0–100
  - Tier 1 extraction + all Layer A checks passed: 95–100
  - Tier 2 extraction + all checks passed: 80–94
  - Tier 3 extraction: 60–79
  - Any Layer B flag: −10 points
  - Any Layer C discrepancy: −20 points

Only `passed` records load automatically. `flagged` records are logged for review. `rejected` records are never loaded.

---

## Phase 5: Load & Status Tracking

**Load path** (unchanged): `validate() → upsert_report() → DB`

On successful load:
- `target_stocks.ingested` flips to `1` (already wired in `upsert_report()`)
- `pipeline_runs` row written with full audit details

### New DB Table: `pipeline_runs`

```sql
CREATE TABLE pipeline_runs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker             TEXT NOT NULL,
    period             TEXT NOT NULL,
    filed_date         DATE,
    extraction_tier    TEXT NOT NULL,    -- 'edgar_api' | 'ixbrl' | 'claude'
    validation_status  TEXT NOT NULL,    -- 'passed' | 'flagged' | 'rejected'
    confidence_score   INTEGER,
    error_message      TEXT,
    run_at             DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## New Files

| File | Role |
|---|---|
| `edgar.py` | EDGAR API client — CIK lookup, filing discovery, Company Facts fetch |
| `extractors/xbrl.py` | Generic US-GAAP concept → `EarningsReport` mapper (Tier 1 + 2) |
| `validate.py` | Accounting identity checks, temporal sanity, cross-source reconciliation |
| `pipeline.py` | Orchestrator — runs all phases, logs to `pipeline_runs` |

**Unchanged**: `extractors/palantir.py`, `extractors/marvell.py`, `loader.py`, `db.py`, `models.py`

> `extractors/xbrl.py` covers Tier 1 only in the initial implementation. Tier 2 iXBRL document parsing and Tier 3 Claude AI extraction are designed and documented in `scaled-ingestion-plan.md` but will not be built until the success rate data justifies it.

---

## Automation

`pipeline.py --auto` runs the full pipeline for every non-ingested ticker in `target_stocks`. Designed to be run as a weekly cron job — 10-Qs are due within 40 days of quarter end, so a Friday run after each quarter catches all new filings.

```bash
# Ingest all pending filings
python pipeline.py --auto

# Ingest a specific ticker
python pipeline.py --ticker NVDA

# Dry run (extract + validate, no DB writes)
python pipeline.py --auto --dry-run
```

---

## Implementation Order

1. `edgar.py` — CIK lookup + Company Facts fetch
2. `extractors/xbrl.py` — US-GAAP concept map + normalization (Tier 1 only)
3. `validate.py` — Layer A accounting identity checks
4. `pipeline_runs` table in `db.py`
5. `pipeline.py` — orchestrator with `--auto` and `--ticker` modes
6. Layer B + C validation
7. Cron scheduling
8. *(Deferred)* Tier 2 iXBRL fallback — revisit after reviewing `pipeline_runs` null rates
9. *(Deferred)* Tier 3 Claude AI extraction — only if Tier 2 is still insufficient

Steps 1–5 deliver a working end-to-end pipeline for the bulk of the 100 target stocks before writing a single company-specific extractor.
