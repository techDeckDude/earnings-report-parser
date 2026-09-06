# Changelog

Entries are newest-first. Each entry describes the change from a user/operator perspective.

- **2026-09-06** — Made Flask port configurable via `PORT` env var so the preview server can assign a free port automatically; `launch.json` updated with `autoPort: true`
- **2026-09-06** — Added dual-mode static deploy support: `generate.py` pre-builds JSON and HTML into `static/` for Cloudflare Pages; `verify.py` diffs live vs static and exits non-zero on mismatch; templates use a single `API_EXT` flag (injected at build time) to switch between Flask routes and flat files; `main.py` chains both scripts after every ingestion
- **2026-08-25** — Added stock detail page (`/stock`): per-ticker metrics table across all quarters, toggleable metric line chart, derived metrics (Gross Margin, FCF), and navigation link from the dashboard
- **2026-08-22** — Added interactive revenue line chart above the table; ticker selector buttons switch the chart between companies; y-axis rescales automatically per company
- **2026-08-22** — Added Marvell Technology (MRVL) support: `MarvellExtractor` parses iXBRL ZIP filings using US-GAAP tag lookup instead of PDF regex; models updated to support optional company-specific fields; 10 MRVL filings (Q1 2024–Q1 2027) ingested and showing in dashboard alongside PLTR
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
