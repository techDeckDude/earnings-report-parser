#!/usr/bin/env python3
"""
Ingest 10-Q filings for a ticker using the EDGAR XBRL API (Tier 1).

Usage:
    python ingest_xbrl.py AMD                  # all available filings
    python ingest_xbrl.py AMD --since 2016-01-01
    python ingest_xbrl.py AMD --dry-run
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

from db import init_db, upsert_report, set_earliest_xbrl_period
from edgar import get_cik, get_new_filings
from extractors.xbrl import XBRLExtractor


def run(ticker: str, since_date: str | None = None, dry_run: bool = False) -> None:
    conn = init_db()

    print(f"Resolving CIK for {ticker}...")
    cik = get_cik(ticker, conn)
    print(f"  CIK: {cik}")

    print(f"Fetching filing list from EDGAR...")
    filings = get_new_filings(ticker, cik, since_date)
    if not filings:
        print(f"  No new 10-Q filings found (since_date={since_date})")
        return
    print(f"  Found {len(filings)} 10-Q filings")

    print(f"Fetching XBRL company facts (one request for all periods)...")
    extractor = XBRLExtractor()
    facts = extractor.fetch_company_facts(cik)
    print(f"  Entity: {facts.get('entityName', ticker)}")

    success, failed = 0, 0
    earliest: str | None = None
    for filing in filings:
        try:
            report = extractor.extract(ticker, cik, filing.period_end, facts)
            if dry_run:
                print(f"  [dry-run] {report.period} ({filing.period_end}) — "
                      f"revenue={report.income_statement.revenue:,.0f}K")
            else:
                upsert_report(conn, report)
                print(f"  ✓ {report.period} ({filing.period_end}) — "
                      f"revenue={report.income_statement.revenue:,.0f}K")
                if earliest is None or filing.period_end < earliest:
                    earliest = filing.period_end
            success += 1
        except Exception as e:
            print(f"  ✗ {filing.period_end}: {e}")
            failed += 1

    if not dry_run and earliest:
        set_earliest_xbrl_period(conn, ticker, earliest)

    action = "Would ingest" if dry_run else "Ingested"
    print(f"\n{action} {success}/{len(filings)} filings for {ticker}"
          + (f" ({failed} failed)" if failed else ""))
    if not dry_run and earliest:
        print(f"Earliest XBRL period recorded: {earliest}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ingest 10-Q data via EDGAR XBRL API")
    p.add_argument("ticker", help="Ticker symbol, e.g. AMD")
    p.add_argument("--since", metavar="YYYY-MM-DD",
                   help="Only ingest filings after this date (default: all available)")
    p.add_argument("--dry-run", action="store_true",
                   help="Extract and validate without writing to DB")
    args = p.parse_args()
    run(args.ticker, since_date=args.since, dry_run=args.dry_run)
