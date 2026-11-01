---
name: list-ingested-stocks
description: Query the shared Postgres database to show which stocks (tickers) have earnings data in the earnings app, including the quarter count and period range for each. Use this whenever the user asks what stocks are in the database, what has been ingested, or what tickers are available.
---

# List Ingested Stocks

Query the earnings database and report which companies have earnings data, with a summary of their quarters.

## Steps

Run this query against the Postgres database configured in this repo's `.env` (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`). Load the variables without printing them:

```bash
set -a; source .env; set +a
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" -c \
  "SELECT c.ticker, c.name, COUNT(er.id) AS quarters,
          MIN(er.period_end_date) AS earliest, MAX(er.period_end_date) AS latest
   FROM companies c
   LEFT JOIN earnings_reports er ON c.id = er.company_id
   GROUP BY c.id
   ORDER BY c.ticker;"
```

Then present the results in a clean table showing:
- **Ticker** — stock symbol
- **Company** — full company name
- **Quarters** — number of quarters stored (Q4s are derived from 10-Ks)
- **Period range** — earliest to latest period end date

If the query fails to connect, say so and suggest checking the `DB_*` settings in `.env`. If there are no rows, remind the user they can load a stock with `ingest-earnings TICKER` (core-data) or the admin dashboard's Stocks page.
