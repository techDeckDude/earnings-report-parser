# Earnings Report Parser

The public earnings site (10qs.io). Data comes from the shared Postgres database, which [core-data](../core-data) owns: its connection pool, schema migrations, EDGAR client, XBRL extraction, and ingestion jobs. This repo keeps only what is specific to it — the Flask site and its static build.

## Table of Contents

- [Usage](#usage)
- [How It Works](#how-it-works)
  - [1. Web site](#1-web-site-apppy--templates)
  - [2. Getting data in](#2-getting-data-in)
- [Project Structure](#project-structure)
- [Experimental Features](#experimental-features)
- [Deployment](#deployment)
- [Known Limitations](#known-limitations)
- [Design Patterns & Infrastructure](#design-patterns--infrastructure)
- [Changelog](#changelog)

## Usage

```bash
pip3 install -e ../core-data                   # DB access, models, EDGAR ingestion (psycopg 3)
pip3 install flask python-dotenv
# .env: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (Postgres)

python3 app.py                                 # the site, live from the database → http://localhost:5001
```

Loading earnings data is core-data's job (see [2. Getting data in](#2-getting-data-in)):

```bash
ingest-earnings NVDA                           # since the last pull; full XBRL history the first time
ingest-earnings --all                          # every tracked stock
```

## How It Works

### 1. Web site (`app.py` + `templates/`)

A Flask app that reads the shared Postgres database through core-data and renders two pages at `http://localhost:5001`. Each request borrows one pooled connection and always returns it (`core_data.flask`). At startup it prints which database it is reading — `* Database: postgresql://user:***@host:port/dbname`, password redacted. The site only reads; it never migrates the schema (the admin dashboard and `core-data-migrate` do that).

**Routes:**
- **`GET /`** — earnings page (`earnings.html`): **Single mode** — ticker search filter (press `/` to focus, `Enter` to jump to first match, `Esc` to clear) above a horizontally-scrollable ticker selector; scrollable metric pill row; metric chart with a BAR/LINE toggle (bar view uses a per-bar gradient from medium emerald for low values to deep forest green for high values; line view uses the original dots-and-line design) plus a QoQ/YoY analytics strip; and a full quarterly metrics table. **Compare mode** — two autocomplete search inputs (one per stock) each with a selected-ticker chip; a grouped bar chart showing both stocks' metrics side by side per period (green = Stock A, blue = Stock B); the y-axis rescales dynamically as the user scrolls so that only the currently visible bars determine the scale, keeping small-cap and large-cap stocks visually comparable across the timeline
- **`GET /api/revenue`** — revenue records for all companies as JSON
- **`GET /api/tickers`** — list of all known ticker symbols and company names
- **`GET /api/metrics/<ticker>`** — every stored quarter for a ticker (`core_data.repositories.earnings.quarterly_table`): `{ticker, name, periods: [{period, period_end_date, filing_type}], data: {statement: {metric_name: [value_per_period]}}}`, ordered by `period_end_date`. A `null` value means the filing didn't report that metric
- **`GET /api/news`** — all news articles grouped into Mon–Sun calendar weeks, newest first; each week includes `week_start`, `week_end`, `period`, `headlines`, and dynamically-computed `summary_stats`
- **`GET /news`** — AI market news feed page; spacing and mobile layout aligned with the earnings page; reads from `/api/news`

New companies and periods appear automatically as data is ingested — no UI changes needed.

The app runs in two modes from a single codebase:

| Mode | How to run | API |
|---|---|---|
| **Live** | `python3 app.py` → `localhost:5001` | Flask routes query Postgres in real time |
| **Static** | `python3 generate.py` → serve `static/` | Pre-built `.json` files (Cloudflare Pages) |

```bash
# Live mode (local dev)
python3 app.py

# Build static output (STATIC_OUT=dir to build somewhere other than static/)
python3 generate.py

# Verify live and static are in sync
python3 verify.py

# Serve static locally to preview before deploying
python3 -m http.server 8080 --directory static
```

### 2. Getting data in

Everything that used to live here as separate scripts now comes from core-data, shared with the admin dashboard:

| Was (this repo) | Now (core-data) |
|---|---|
| `ingest_xbrl.py`, `ingest_10k.py`, `bulk_ingest.py` | `ingest-earnings TICKER…` / `--all` — one durable job per ticker: every 10-Q since the last pull plus derived Q4s, one transaction per quarter, resumable after a crash. `--reload` re-ingests everything (repairs older data) |
| `add_stock.py` | `ingest-earnings TICKER` tracks an untracked ticker first (CIK + name from SEC), or use the admin dashboard's Stocks page |
| `scan_filings.py` | `scan-filings --save` |
| `ingest_news.py`, `scheduler.py` | `ingest-news`, `run-scheduler` |
| `db.py`, `models.py`, `edgar.py`, `extractors/xbrl.py` | `core_data.db` / `.repositories`, `core_data.models`, `core_data.sources`, `core_data.extractors` |
| `migrate_sqlite_to_pg.py` | Removed — SQLite is no longer supported; schema changes are versioned migrations (`core-data-migrate`) |
| `main.py`, `loader.py`, `extractors/` (Palantir/Marvell PDF and iXBRL parsing, S3 contracts) | Removed — every stock now comes from EDGAR's XBRL API through core-data |

Q4 is derived from each 10-K (`Q4 = annual − Q1 − Q2 − Q3` for flows; the year-end snapshot for the balance sheet; EPS = Q4 net income ÷ annual weighted shares). See core-data's [tracking & ingestion guide](../core-data/docs/guides/tracking-and-ingestion.md) for every way a stock gets tracked and its earnings loaded, with diagrams.

## Project Structure

```
earnings-report-parser/
├── app.py               # Flask site + API over the shared DB (core_data.flask: one pooled connection per request)
├── generate.py          # Build static/ from live Flask (STATIC_BUILD=true; STATIC_OUT overrides the output dir)
├── verify.py            # Diff live API responses against static JSON files; exits 1 on mismatch
├── templates/
│   ├── earnings.html    # Earnings page: ticker selector, metric chart, quarterly metrics table
│   └── news.html        # AI news feed: weekly carousel, sentiment chart, swipe nav
├── experimental/
│   ├── __init__.py      # Flask Blueprint definition (url_prefix="/experimental")
│   └── routes.py        # Route handlers for experimental features
├── tests/               # pytest against a throwaway Postgres (see tests/conftest.py); never the .env database
│   └── fixtures/        # PLTR / MRVL report JSONs used to seed the test database
├── static/              # Built static site (committed; deployed to Cloudflare Pages)
├── docs/                # Pipeline walkthrough, AWS plan, Postgres ops runbook, diagrams
├── deploy.sh            # Deploy script: merge develop → main (code + build commits), tag, push to origin
├── .claude/agents/      # Claude Code skills (news-aggregator)
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

## Known Limitations

- **Data written before the move to core-data may be wrong** — cumulative (YTD) quarterly cash flows, and quarters stored under a mis-tagged label. Run `ingest-earnings --all --reload` once to repair it
- **Early-XBRL Q4 EPS can be wildly off** (e.g. NVDA Q4 2011 shows ~$298) — Q4 EPS divides by the 10-K's share count, which some early filings tag at the wrong scale
- **Quarters with untagged core fields are skipped** — EDGAR XBRL is now the only source; a quarter missing revenue, net income or diluted EPS (or failing a cross-check) isn't stored. Earlier PDF-extracted quarters already in the database stay as they are
- **The site needs Postgres** — SQLite support was removed with the move to core-data

---

## Design Patterns & Infrastructure

### Design Patterns

| Pattern | Where Applied | Purpose |
|---|---|---|
| **Experimental Blueprint** | `experimental/` Flask Blueprint mounted at `/experimental` | Isolate prototype features (mock data, unvalidated UI) from the production surface; controlled by `EXPERIMENTAL` env var; see `CLAUDE.md` for the promotion checklist |
| **Repository** | core-data `core_data.repositories` (used by `app.py`) | All SQL lives in core-data, shared with the admin dashboard; this repo never opens or commits a connection itself |
| **Connection pool, per-request borrow** | `app.py` → `core_data.flask.init_app` / `request_connection()` | One pooled connection per request, always returned; replaces a single global connection shared across request threads |

### Infrastructure

| Layer | Technology | Notes |
|---|---|---|
| Database | `PostgreSQL` via core-data (`psycopg` 3 + `psycopg_pool`) | Required; schema owned by core-data's versioned migrations |
| Web server | `Flask` | Serves the site at `localhost:5001`; routes: `/`, `/news`, `/api/revenue`, `/api/tickers`, `/api/metrics/<ticker>`, `/api/news` |
| Fonts | `IBM Plex Mono` + `IBM Plex Sans` (Google Fonts) | Terminal aesthetic: mono for all UI chrome (nav, labels, values), sans-serif for body text |

### Environment Variables

| Variable | Effect |
|---|---|
| `DB_HOST` / `DB_USER` / `DB_PASSWORD` | Postgres connection (required), read by core-data |
| `DB_NAME` / `DB_PORT` | Database name (default `earningsdb`) and port (default `5432`) |
| `DB_CONNECT_TIMEOUT` | Seconds before giving up on an unreachable server (default `10`) |
| `DB_POOL_MIN` / `DB_POOL_MAX` / `DB_POOL_TIMEOUT` | Connection pool sizing (defaults `1` / `10` / `30`s) |
| `STATIC_OUT` | Output directory for `generate.py` / `verify.py` (default `static`) |
| `PORT` | Flask dev server port (default: `5001`) |
| `EXPERIMENTAL` | Mount the experimental Blueprint (default: `1` = enabled); set `0` to disable all `/experimental/*` routes in production |

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
