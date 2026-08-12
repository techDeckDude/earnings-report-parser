# Earnings Report Parser

A prototype pipeline that extracts structured financial data from SEC 10-Q PDF filings, validates it with Pydantic, and persists it to a SQLite database. Built and tested against the Palantir Technologies Q2 2026 10-Q.

## Usage

```bash
pip install pdfplumber pydantic
python main.py path/to/10-Q.pdf [earnings.db]
```

This produces:
- Console output with a formatted financial summary
- A SQLite database (default: `earnings.db`) with the extracted data
- A JSON file alongside the PDF with the full extracted payload

## How It Works

The pipeline runs in four steps:

```
PDF → extractor.py → models.py → db.py → earnings.db
                          ↓
                    validation error
                    (stops the run)
```

### 1. Extraction (`extractor.py`)

`pdfplumber` opens the PDF and pulls raw text from specific pages where each financial statement lives in the Palantir 10-Q:

| Page (0-indexed) | Content |
|---|---|
| 2 | Balance Sheet |
| 3 | Income Statement |
| 7–8 | Cash Flow Statement |

Each statement has its own extraction function (`_extract_income_statement`, `_extract_balance_sheet`, `_extract_cash_flow`). These use regex patterns to find known line-item labels and capture the number that follows. Dollar signs, commas, and parenthetical negatives (e.g. `(1,509,665)`) are all normalized by `_parse_num`.

The cover page is scanned separately to extract the company name, filing period, and period-end date.

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

Calls each step in sequence, prints a human-readable summary to stdout, and writes a full JSON dump of the extracted report.

## Project Structure

```
earnings-report-parser/
├── main.py        # Entry point and CLI
├── extractor.py   # PDF parsing and regex extraction
├── models.py      # Pydantic data models and validators
├── db.py          # SQLite schema and persistence
└── README.md
```

## Known Limitations

The extractor is tightly coupled to the Palantir 10-Q format:

- **Page numbers are hardcoded** — other filings put financial statements on different pages
- **Regex labels match PLTR's exact wording** — other companies use different names for the same line items
- **Column order is assumed** — the income statement has four columns (current quarter, prior quarter, YTD, prior YTD); the regex always captures the first, which is the current quarter

It will work reliably for any Palantir quarterly filing with the same page layout, but would need changes to handle other companies or annual 10-K filings.
