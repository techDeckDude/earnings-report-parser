# Testing Strategy

**Framework**: `pytest`  
**Test root**: `tests/`  
**Run**: `pytest tests/ -v`

---

## Philosophy

- **No mocks where avoidable.** Hit real SQLite (in-memory), real Flask routes, real Pydantic validators. Mocks hide the integration problems that matter most.
- **Isolate state.** Every DB test uses an in-memory SQLite connection spun up and torn down per test — the live `earnings.db` is never written to by tests.
- **Real fixture data.** Fixture JSON contracts are taken verbatim from actual parsed 10-Q filings (`data/outputs/`), not hand-crafted. If the fixtures pass Pydantic validation, they are structurally correct.
- **Test behavior, not implementation.** Tests assert what the function returns or what ends up in the DB — not how it got there.

---

## Structure

```
tests/
  conftest.py              # shared fixtures (mem_db, sample reports, flask client)
  test_models.py           # Pydantic cross-field validators in models.py
  test_db.py               # DB read/write layer (upsert_report, init_db)
  test_news_db.py          # News ingestion DB layer (upsert_news_run, get_all_news_runs)
  test_api.py              # Flask API endpoint shape and status codes
  test_loader.py           # loader.py contract loading from local JSON
  test_static_build.py     # generate.py output + verify.py sync check
  fixtures/
    pltr_q2_2026.json      # Real PLTR Q2 2026 contract from data/outputs/
    mrvl_q3_2024.json      # Real MRVL Q3 2024 contract from data/outputs/
```

---

## Fixtures (`conftest.py`)

| Fixture | Scope | What it provides |
|---|---|---|
| `mem_db` | function | Fresh in-memory SQLite with full schema applied |
| `sample_pltr_report` | session | `EarningsReport` from PLTR Q2 2026 fixture JSON |
| `sample_mrvl_report` | session | `EarningsReport` from MRVL Q3 2024 fixture JSON |
| `flask_client` | function | Flask test client against the live `earnings.db` (read-only tests) |

---

## Test Modules

### `test_models.py` — Pydantic Validators

Tests the cross-field math checks in `models.py`. These are the first correctness gate and the only validation logic that exists today.

| Test | Assertion |
|---|---|
| `test_gross_profit_valid` | Passes when `gross_profit == revenue − cost_of_revenue` |
| `test_gross_profit_rounding_tolerance` | Passes with a ≤$5k gap (rounding in reported figures) |
| `test_gross_profit_invalid` | Raises `ValidationError` when off by >$5k |
| `test_balance_sheet_balances` | Passes when `assets == liabilities + equity` (±$500k) |
| `test_balance_sheet_doesnt_balance` | Raises `ValidationError` when off by >$500k |
| `test_full_pltr_report_valid` | Real PLTR contract builds without error |
| `test_full_mrvl_report_valid` | Real MRVL contract builds without error |
| `test_optional_fields_default_none` | Optional fields absent → `None`, no error |
| `test_schema_version_default` | `schema_version` defaults to `"1.0"` |

### `test_db.py` — Database Layer

All tests use `mem_db` (in-memory SQLite). No writes to `earnings.db`.

| Test | Assertion |
|---|---|
| `test_init_creates_all_tables` | All 6 tables exist after `init_db()` |
| `test_upsert_report_creates_company` | Company row exists in `companies` after upsert |
| `test_upsert_report_creates_report` | Row exists in `earnings_reports` after upsert |
| `test_upsert_report_creates_metrics` | Rows exist in `financial_metrics` after upsert |
| `test_upsert_report_idempotent` | Second upsert of same period updates, does not duplicate |
| `test_upsert_two_periods_same_company` | Two quarters → two report rows, one company row |
| `test_upsert_marks_target_stock_ingested` | If ticker in `target_stocks`, `ingested` flips to 1 |
| `test_upsert_no_target_stock_no_error` | Ticker absent from `target_stocks` → no crash |

### `test_news_db.py` — News Ingestion DB Layer

| Test | Assertion |
|---|---|
| `test_upsert_news_run_creates_run` | Row in `news_runs` after upsert |
| `test_upsert_news_run_creates_articles` | Rows in `news_articles` after upsert |
| `test_get_all_news_runs_newest_first` | Multiple runs returned newest-first by `run_at` |
| `test_get_all_news_runs_includes_articles` | Each run dict includes its `headlines` list |
| `test_get_all_news_runs_empty_db` | Returns `[]` when no runs exist |
| `test_get_latest_news_returns_most_recent` | Returns the run with the highest `run_at` |
| `test_get_latest_news_empty_db` | Returns `None` when no runs exist |

### `test_api.py` — Flask Endpoints

Uses the `flask_client` fixture against the live DB. Read-only — no writes.

| Test | Assertion |
|---|---|
| `test_root_200` | `GET /` → 200 |
| `test_news_page_200` | `GET /news` → 200 |
| `test_api_revenue_is_list` | `GET /api/revenue` → JSON list |
| `test_api_revenue_has_required_keys` | Each item has `ticker`, `period`, `revenue` |
| `test_api_tickers_is_list` | `GET /api/tickers` → JSON list |
| `test_api_tickers_has_required_keys` | Each item has `ticker`, `name` |
| `test_api_metrics_pltr` | `GET /api/metrics/PLTR` → dict with `income_statement`, `balance_sheet`, `cash_flow` |
| `test_api_metrics_mrvl` | `GET /api/metrics/MRVL` → same shape |
| `test_api_news_is_list` | `GET /api/news` → JSON list |
| `test_api_news_has_required_keys` | Each item has `run_id`, `period`, `headlines`, `summary_stats` |
| `test_api_news_headlines_have_required_keys` | Each headline has `headline`, `source`, `sentiment_score`, `sentiment_label` |

### `test_loader.py` — Contract Loading

Uses a temporary in-memory DB so real data is never touched.

| Test | Assertion |
|---|---|
| `test_load_valid_pltr_contract` | `pltr_q2_2026.json` loads → `report_id` returned, company row exists |
| `test_load_valid_mrvl_contract` | `mrvl_q3_2024.json` loads → same |
| `test_load_rejects_unknown_schema_version` | `schema_version: "99.0"` → `SystemExit` / raises |
| `test_load_rejects_missing_required_field` | Contract missing `revenue` → `ValidationError` |
| `test_load_is_idempotent` | Loading same contract twice → no duplicate row, no error |

### `test_static_build.py` — Build & Verify

Runs `generate.py` and `verify.py` as subprocesses against the live DB.

| Test | Assertion |
|---|---|
| `test_generate_creates_revenue_json` | `static/api/revenue.json` exists after `generate.py` |
| `test_generate_creates_tickers_json` | `static/api/tickers.json` exists |
| `test_generate_creates_metrics_per_ticker` | `static/api/metrics/PLTR.json` and `MRVL.json` exist |
| `test_generate_creates_news_json` | `static/api/news.json` exists |
| `test_generate_creates_html_pages` | `static/index.html`, `static/news/index.html` exist |
| `test_verify_passes_after_generate` | `verify.py` exits 0 immediately after `generate.py` |

---

## What Is Explicitly Out of Scope

| Area | Reason |
|---|---|
| Extractor unit tests (`palantir.py`, `marvell.py`) | Require real PDFs; superseded by EDGAR pipeline |
| `ingest_news.py` | Calls Anthropic API with web search — too slow and costly to run in tests |
| UI / browser tests | Needs Playwright or Selenium; deferred |
| `edgar.py`, `pipeline.py`, `validate.py` | Not built yet — tests written alongside implementation |

---

## Running

```bash
# Install
pip install pytest

# Full suite
pytest tests/ -v

# One module
pytest tests/test_models.py -v

# Filter by name
pytest tests/ -k "test_api" -v

# Stop on first failure
pytest tests/ -x
```
