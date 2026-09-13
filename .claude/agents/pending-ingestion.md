---
name: pending-ingestion
description: Query the local SQLite database to show which target stocks have NOT yet been ingested into the earnings app. Use this whenever the user asks what stocks are still pending, what hasn't been ingested yet, or what's left in the pipeline.
---

# Pending Ingestion

Query the earnings database and report which target stocks are still waiting to be ingested.

## Steps

Run this query against the database at `/Users/justinbullock/Documents/code-repositories/earnings-report-parser/earnings.db`:

```bash
sqlite3 /Users/justinbullock/Documents/code-repositories/earnings-report-parser/earnings.db \
  "SELECT ticker, name, added_at FROM target_stocks WHERE ingested = 0 ORDER BY added_at;"
```

If the result is empty, say: "All target stocks have been ingested." and list the already-ingested tickers from:

```bash
sqlite3 /Users/justinbullock/Documents/code-repositories/earnings-report-parser/earnings.db \
  "SELECT ticker, name FROM target_stocks WHERE ingested = 1 ORDER BY ticker;"
```

If there are pending stocks, present them in a table with columns:
- **Ticker** — stock symbol
- **Company** — full company name
- **Added** — date added to the target list

Then remind the user they can ingest a pending stock by running:
`python main.py "<PDF file for TICKER>"`
