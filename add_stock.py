#!/usr/bin/env python3
"""
Add a stock to target_stocks, resolve its CIK, and scan its EDGAR
filing history to populate earliest_xbrl_period.

Usage:
    python3 add_stock.py NVDA "NVIDIA Corporation" --category "AI Infrastructure / Semiconductors"
    python3 add_stock.py NVDA "NVIDIA Corporation"   # category optional
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import init_db, set_earliest_xbrl_period
from edgar import get_cik, get_new_filings


def run(ticker: str, name: str, category: str | None) -> None:
    ticker = ticker.upper()
    conn = init_db()

    # ── 1. Insert into target_stocks (skip if already present) ───────────────
    existing = conn.execute(
        "SELECT ticker, ingested, cik, earliest_xbrl_period FROM target_stocks WHERE ticker = ?",
        (ticker,),
    ).fetchone()

    if existing:
        print(f"{ticker} is already in target_stocks (ingested={bool(existing['ingested'])}).")
    else:
        conn.execute(
            "INSERT INTO target_stocks (ticker, name, category) VALUES (?, ?, ?)",
            (ticker, name, category),
        )
        conn.commit()
        print(f"Added {ticker} — {name}" + (f" [{category}]" if category else ""))

    # ── 2. Resolve CIK (reads from cache or hits EDGAR) ──────────────────────
    print(f"Resolving CIK...")
    try:
        cik = get_cik(ticker, conn)
        print(f"  CIK: {cik}")
    except ValueError as e:
        print(f"  ERROR: {e}")
        print("  CIK could not be resolved — stock may be a foreign private issuer (20-F filer).")
        print("  Set target_stocks.cik manually if you have the CIK, then re-run scan_filings.py --save.")
        sys.exit(1)

    # ── 3. Scan filing history ────────────────────────────────────────────────
    print(f"Scanning EDGAR 10-Q history...")
    filings = get_new_filings(ticker, cik, since_date=None)

    if not filings:
        print(f"  No 10-Q filings found. This ticker may file on Form 20-F (foreign private issuer).")
        print(f"  The XBRL extractor will not work for this stock.")
        return

    oldest = filings[0].period_end
    newest = filings[-1].period_end
    count  = len(filings)
    yrs    = round((date.fromisoformat(newest) - date.fromisoformat(oldest)).days / 365.25, 1)

    set_earliest_xbrl_period(conn, ticker, oldest)

    print(f"  {count} 10-Q filings found")
    print(f"  Oldest: {oldest}")
    print(f"  Newest: {newest}")
    print(f"  Coverage: ~{yrs} years")
    print()
    print(f"Ready to ingest. Run:")
    print(f"  python3 ingest_xbrl.py {ticker} --since {oldest}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Add a stock to target_stocks and scan its EDGAR filing history"
    )
    p.add_argument("ticker", help="Ticker symbol, e.g. NVDA")
    p.add_argument("name", help='Company name, e.g. "NVIDIA Corporation"')
    p.add_argument(
        "--category",
        help="Sector category (optional). Existing categories: "
             "AI Infrastructure / Semiconductors, AI Pure Plays, AI-Powered Software, "
             "Autonomous / Robotics / Vision, Cloud & Hyperscalers, Data & Analytics, "
             "Networking / Hardware, Semiconductors / EDA / IP, Specialty AI / Healthcare AI",
    )
    args = p.parse_args()
    run(args.ticker, args.name, args.category)
