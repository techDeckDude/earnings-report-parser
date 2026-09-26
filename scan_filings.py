#!/usr/bin/env python3
"""
Scan EDGAR filing history for every ticker in target_stocks and report
how many 10-Q filings exist and what date range they cover.

Stores the oldest period in earliest_xbrl_period so ingest_xbrl.py
can skip the check at runtime. Does not download any financial data.

Usage:
    python3 scan_filings.py           # all tickers with a CIK
    python3 scan_filings.py --save    # also write results to target_stocks
"""
from __future__ import annotations

import argparse
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import init_db, set_earliest_xbrl_period
from edgar import get_cik, get_new_filings


def run(save: bool = False) -> None:
    conn = init_db()
    rows = conn.execute(
        "SELECT ticker, name, cik, ingested, earliest_xbrl_period "
        "FROM target_stocks ORDER BY ticker"
    ).fetchall()

    no_cik = [r for r in rows if not r["cik"]]
    with_cik = [r for r in rows if r["cik"]]

    print(f"Scanning {len(with_cik)} tickers ({len(no_cik)} skipped — no CIK)\n")
    print(f"{'TICKER':<8} {'INGESTED':<10} {'10-Qs':>6}  {'OLDEST':>12}  {'NEWEST':>12}  {'YRS':>4}  NAME")
    print("─" * 90)

    errors = []
    for row in with_cik:
        ticker = row["ticker"]
        cik    = row["cik"]
        try:
            filings = get_new_filings(ticker, cik, since_date=None)
            if not filings:
                print(f"{ticker:<8} {'yes' if row['ingested'] else 'no':<10} {'—':>6}  {'no filings':>12}  {'':>12}  {'':>4}  {row['name']}")
                continue

            oldest = filings[0].period_end
            newest = filings[-1].period_end
            count  = len(filings)

            from datetime import date
            yrs = round((date.fromisoformat(newest) - date.fromisoformat(oldest)).days / 365.25, 1)

            ingested = "yes" if row["ingested"] else "no"
            print(f"{ticker:<8} {ingested:<10} {count:>6}  {oldest:>12}  {newest:>12}  {yrs:>4}  {row['name']}")

            if save:
                set_earliest_xbrl_period(conn, ticker, oldest)

        except Exception as e:
            print(f"{ticker:<8} {'error':<10}  — {e}")
            errors.append(ticker)

    if no_cik:
        print(f"\nNo CIK (skipped): {', '.join(r['ticker'] for r in no_cik)}")

    if save:
        print(f"\nSaved earliest_xbrl_period for {len(with_cik) - len(errors)} tickers.")
    else:
        print(f"\nRun with --save to write oldest period to target_stocks.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Scan EDGAR 10-Q history for all target stocks")
    p.add_argument("--save", action="store_true",
                   help="Write oldest period to target_stocks.earliest_xbrl_period")
    args = p.parse_args()
    run(save=args.save)
