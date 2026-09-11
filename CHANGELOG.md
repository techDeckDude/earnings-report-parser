# Changelog

Entries are newest-first. Each entry describes the change from a user/operator perspective.

- **2026-09-11** — Wired news feed to a real backend: added news_runs and news_articles database tables, ingest_news.py CLI script (calls Claude with web search via Anthropic SDK), GET /api/news endpoint, and updated the News page to fetch live data instead of using hardcoded headlines
- **2026-09-11** — Hidden News nav link from static builds: the experimental /themes page is not built statically so the link is now suppressed with {% if experimental and not static_build %}
- **2026-09-11** — Added browser tab favicon: 2×2 quad-grid SVG in green on black — four squares with ascending opacity, matching the terminal aesthetic
- **2026-09-11** — Fixed chart tooltip text being unreadable in light mode: tooltip background is now theme-aware (#161616 dark / #ffffff light) via a --tooltip-bg CSS variable
- **2026-09-11** — Improved contrast for secondary and tertiary text in both light and dark modes; standardized page max-width to 940px across both pages; made the nav bar sticky so it stays pinned at the top of the viewport while scrolling
- **2026-09-11** — Added light/dark mode toggle to both pages: button in the nav bar switches between a warm off-white light theme and the default black terminal dark theme; preference is persisted in localStorage and shared across pages
- **2026-09-11** — Fixed responsive layout on News and Earnings pages: content now centers and scales correctly on large screens via max-width (940px News, 1280px Earnings) with margin:auto; html background fills the full viewport gutter
- **2026-09-11** — Restyled both pages to match a terminal/Bloomberg aesthetic: pure black background (#0a0a0a), IBM Plex Mono + IBM Plex Sans fonts, #00e664 green accent, hairline 0.5px borders, subtle green grid overlay, and radial vignette; chart lines, active states, derived metric values, and ticker tags all updated to green
- **2026-09-11** — Removed the separate revenue table dashboard; stock metrics page (stock.html) is now the root / and the sole earnings page
- **2026-09-11** — Introduced Experimental Blueprint pattern (`experimental/` package, `/experimental` URL prefix): prototype features now live in a separate Flask Blueprint, isolated from the production surface, enabled by default and disableable via `EXPERIMENTAL=0`; full usage and promotion checklist documented in `CLAUDE.md` and `README.md`
- **2026-09-11** — Added sentiment line chart to the News page: X-axis = article order, Y-axis = score −2 to +2, green/red split-fill area above/below the neutral line, hover tooltip shows full headline and score label
- **2026-09-11** — Added News page (`/themes`): AI market news feed with clickable headline links, 5-level sentiment pills, source badges, ⚠ Unverified badge for unconfirmed URLs, and summary stat chips
- **2026-09-11** — Added URL verification step to news-aggregator skill: targeted follow-up search for any unconfirmed URL; headlines without a verifiable source surface url_verified: false as an honest signal rather than fabricating a link
- **2026-09-11** — Added mandatory self-critic pass to news-aggregator skill: verifies URL uniqueness, sentiment score boundaries, ticker accuracy, and confirmed-vs-potential language before output
- **2026-09-11** — Updated news-aggregator skill to cover the past 7 days, added direct article URLs, and replaced binary sentiment with a 5-level scale (−2 to +2) based on confirmed vs. potential revenue/earnings impact
- **2026-09-08** — Added news-aggregator Claude Code skill for fetching and sentiment-scoring AI stock market headlines from the past 24 hours
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
