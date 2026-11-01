---
name: pending-ingestion
description: Query the shared Postgres database to show which tracked stocks have NOT yet been ingested into the earnings app. Use this whenever the user asks what stocks are still pending, what hasn't been ingested yet, or what's left in the pipeline.
---

# Pending Ingestion

Query the earnings database and report which tracked stocks are still waiting to be ingested.

## Steps

Run this query against the Postgres database configured in this repo's `.env` (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`). Load the variables without printing them:

```bash
set -a; source .env; set +a
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" -c \
  "SELECT ticker, name, cik, added_at FROM target_stocks WHERE ingested = FALSE ORDER BY added_at;"
```

If the result is empty, say: "All tracked stocks have been ingested." and list the already-ingested tickers from:

```bash
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" -c \
  "SELECT ticker, name FROM target_stocks WHERE ingested = TRUE ORDER BY ticker;"
```

If there are pending stocks, present them in a table with columns:
- **Ticker** — stock symbol
- **Company** — full company name
- **CIK** — SEC identifier ("—" if not resolved yet)
- **Added** — date added to the tracked list

Then remind the user they can ingest pending stocks with core-data's CLI:
`ingest-earnings TICKER` for one, or `ingest-earnings --all` for every tracked stock — or with "load all" on the admin dashboard's Stocks page.
