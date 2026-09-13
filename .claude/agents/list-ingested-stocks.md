---
name: list-ingested-stocks
description: Query the local SQLite database to show which stocks (tickers) have already been ingested into the earnings app, including the filing count and period range for each. Use this whenever the user asks what stocks are in the database, what has been ingested, or what tickers are available.
---

# List Ingested Stocks

Query the earnings database and report which companies have been ingested, with a summary of their filings.

## Steps

Run this query against the database at `/Users/justinbullock/Documents/code-repositories/earnings-report-parser/earnings.db`:

```bash
sqlite3 /Users/justinbullock/Documents/code-repositories/earnings-report-parser/earnings.db \
  "SELECT c.ticker, c.name, COUNT(er.id) AS filings, MIN(er.period) AS earliest, MAX(er.period) AS latest
   FROM companies c
   LEFT JOIN earnings_reports er ON c.id = er.company_id
   GROUP BY c.id
   ORDER BY c.ticker;"
```

Then present the results in a clean table showing:
- **Ticker** — stock symbol
- **Company** — full company name
- **Filings** — number of quarters ingested
- **Period range** — earliest to latest quarter (e.g. Q1 2024 – Q3 2026)

If the database file does not exist, say so and remind the user to run the ingestion pipeline first (`python main.py "<pdf file>"`).
