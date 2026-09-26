#!/usr/bin/env python3
"""
Ingest all available 10-Q XBRL data for every ticker in target_stocks
that has a CIK and a known earliest_xbrl_period.

Usage:
    python3 bulk_ingest.py           # ingest all pending tickers
    python3 bulk_ingest.py --dry-run # validate without writing to DB
    python3 bulk_ingest.py --skip-ingested  # skip tickers already marked ingested
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import init_db
from ingest_xbrl import run as ingest_one


@dataclass
class Result:
    ticker: str
    quarters: int = 0
    failed: int = 0
    error: str = ""


def run_bulk(dry_run: bool = False, skip_ingested: bool = False) -> None:
    conn = init_db()
    rows = conn.execute("""
        SELECT ticker, name, cik, ingested, earliest_xbrl_period
        FROM target_stocks
        WHERE cik IS NOT NULL
          AND earliest_xbrl_period IS NOT NULL
        ORDER BY ticker
    """).fetchall()

    if skip_ingested:
        rows = [r for r in rows if not r["ingested"]]

    skipped_no_data = conn.execute("""
        SELECT ticker FROM target_stocks
        WHERE cik IS NOT NULL AND earliest_xbrl_period IS NULL
    """).fetchall()

    skipped_no_cik = conn.execute("""
        SELECT ticker FROM target_stocks WHERE cik IS NULL
    """).fetchall()

    total = len(rows)
    print(f"Bulk ingestion: {total} tickers to process")
    if skipped_no_data:
        print(f"Skipping {len(skipped_no_data)} with no EDGAR 10-Q filings: "
              + ", ".join(r["ticker"] for r in skipped_no_data))
    if skipped_no_cik:
        print(f"Skipping {len(skipped_no_cik)} with no CIK: "
              + ", ".join(r["ticker"] for r in skipped_no_cik))
    if dry_run:
        print("DRY RUN — no data will be written\n")
    print()

    results: list[Result] = []
    start_time = time.monotonic()

    for i, row in enumerate(rows, 1):
        ticker = row["ticker"]
        since  = str(row["earliest_xbrl_period"])
        prefix = f"[{i:>3}/{total}] {ticker:<8}"

        print(f"{prefix} ingesting from {since}...", flush=True)

        # Capture stdout from ingest_one by temporarily redirecting
        import io, contextlib
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                ingest_one(ticker, since_date=since, dry_run=dry_run)
            output = buf.getvalue()
            # Count successes and failures from the output lines
            ok  = output.count("✓") + output.count("[dry-run]")
            err = output.count("✗")
            results.append(Result(ticker=ticker, quarters=ok, failed=err))
            status = f"{ok} quarters"
            if err:
                status += f", {err} failed"
            print(f"{prefix} done — {status}")
        except Exception as e:
            results.append(Result(ticker=ticker, error=str(e)))
            print(f"{prefix} ERROR — {e}")

    elapsed = time.monotonic() - start_time

    # ── Summary ───────────────────────────────────────────────────────────────
    total_quarters = sum(r.quarters for r in results)
    ticker_errors  = [r for r in results if r.error]
    partial        = [r for r in results if r.failed > 0 and not r.error]

    print()
    print("=" * 60)
    print(f"Bulk ingestion complete in {elapsed:.0f}s")
    print(f"  Tickers processed : {len(results)}")
    print(f"  Quarters ingested : {total_quarters}")
    if ticker_errors:
        print(f"  Tickers failed    : {len(ticker_errors)}")
        for r in ticker_errors:
            print(f"    {r.ticker}: {r.error}")
    if partial:
        print(f"  Partial failures  :")
        for r in partial:
            print(f"    {r.ticker}: {r.failed} quarter(s) failed")
    if not ticker_errors and not partial:
        print(f"  All tickers clean ✓")
    print("=" * 60)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Bulk ingest all target stocks via EDGAR XBRL")
    p.add_argument("--dry-run", action="store_true", help="Validate without writing to DB")
    p.add_argument("--skip-ingested", action="store_true",
                   help="Skip tickers already marked ingested=1")
    args = p.parse_args()
    run_bulk(dry_run=args.dry_run, skip_ingested=args.skip_ingested)
