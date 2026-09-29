#!/usr/bin/env python3
"""
Ingest all available 10-Q and 10-K (Q4 derivation) XBRL data for every ticker
in target_stocks that has a CIK and a known earliest_xbrl_period.

Usage:
    python3 bulk_ingest.py           # ingest all tickers (10-Q + 10-K)
    python3 bulk_ingest.py --dry-run # validate without writing to DB
    python3 bulk_ingest.py --skip-ingested  # skip tickers already marked ingested
    python3 bulk_ingest.py --skip-10k       # skip 10-K Q4 derivation step
"""
from __future__ import annotations

import argparse
import io
import contextlib
import sys
import time
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import init_db, _execute, _is_pg
from ingest_xbrl import run as ingest_xbrl_one
from ingest_10k import run as ingest_10k_one


@dataclass
class Result:
    ticker: str
    quarters: int = 0
    failed: int = 0
    q4_periods: int = 0
    q4_failed: int = 0
    error: str = ""


def run_bulk(dry_run: bool = False, skip_ingested: bool = False,
             skip_10k: bool = False) -> None:
    conn = init_db()

    rows = _execute(conn, """
        SELECT ticker, name, cik, ingested, earliest_xbrl_period
        FROM target_stocks
        WHERE cik IS NOT NULL
          AND earliest_xbrl_period IS NOT NULL
        ORDER BY ticker
    """).fetchall()

    if skip_ingested:
        rows = [r for r in rows if not r["ingested"]]

    skipped_no_data = _execute(conn, """
        SELECT ticker FROM target_stocks
        WHERE cik IS NOT NULL AND earliest_xbrl_period IS NULL
    """).fetchall()

    skipped_no_cik = _execute(conn, """
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
    if skip_10k:
        print("Skipping 10-K Q4 derivation (--skip-10k)\n")
    print()

    results: list[Result] = []
    start_time = time.monotonic()

    for i, row in enumerate(rows, 1):
        ticker = row["ticker"]
        since  = str(row["earliest_xbrl_period"])
        prefix = f"[{i:>3}/{total}] {ticker:<8}"

        # ── 10-Q ingestion ─────────────────────────────────────────────────────
        print(f"{prefix} ingesting 10-Q from {since}...", flush=True)
        buf = io.StringIO()
        result = Result(ticker=ticker)
        try:
            with contextlib.redirect_stdout(buf):
                ingest_xbrl_one(ticker, since_date=since, dry_run=dry_run)
            output = buf.getvalue()
            result.quarters = output.count("✓") + output.count("[dry-run]")
            result.failed   = output.count("✗")
            status = f"{result.quarters} quarters"
            if result.failed:
                status += f", {result.failed} failed"
            print(f"{prefix} 10-Q done — {status}")
        except Exception as e:
            result.error = str(e)
            print(f"{prefix} 10-Q ERROR — {e}")
            results.append(result)
            continue

        # ── 10-K Q4 derivation ─────────────────────────────────────────────────
        if not skip_10k:
            print(f"{prefix} deriving Q4 from 10-K (since {since})...", flush=True)
            buf2 = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf2):
                    ingest_10k_one(ticker, since_date=since, dry_run=dry_run)
                output2 = buf2.getvalue()
                result.q4_periods = output2.count("✓") + output2.count("[dry-run]")
                result.q4_failed  = output2.count("✗")
                status2 = f"{result.q4_periods} Q4 periods"
                if result.q4_failed:
                    status2 += f", {result.q4_failed} failed"
                print(f"{prefix} 10-K done — {status2}")
            except Exception as e:
                print(f"{prefix} 10-K ERROR — {e}")

        results.append(result)

    elapsed = time.monotonic() - start_time

    # ── Summary ───────────────────────────────────────────────────────────────
    total_quarters = sum(r.quarters for r in results)
    total_q4       = sum(r.q4_periods for r in results)
    ticker_errors  = [r for r in results if r.error]
    partial        = [r for r in results if (r.failed > 0 or r.q4_failed > 0) and not r.error]

    print()
    print("=" * 60)
    print(f"Bulk ingestion complete in {elapsed:.0f}s")
    print(f"  Tickers processed : {len(results)}")
    print(f"  Quarters ingested : {total_quarters}")
    if not skip_10k:
        print(f"  Q4 periods derived: {total_q4}")
    if ticker_errors:
        print(f"  Tickers failed    : {len(ticker_errors)}")
        for r in ticker_errors:
            print(f"    {r.ticker}: {r.error}")
    if partial:
        print(f"  Partial failures  :")
        for r in partial:
            parts = []
            if r.failed:
                parts.append(f"{r.failed} quarter(s) failed")
            if r.q4_failed:
                parts.append(f"{r.q4_failed} Q4 period(s) failed")
            print(f"    {r.ticker}: {', '.join(parts)}")
    if not ticker_errors and not partial:
        print(f"  All tickers clean ✓")
    print("=" * 60)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Bulk ingest all target stocks via EDGAR XBRL (10-Q + 10-K Q4)"
    )
    p.add_argument("--dry-run", action="store_true", help="Validate without writing to DB")
    p.add_argument("--skip-ingested", action="store_true",
                   help="Skip tickers already marked ingested=1")
    p.add_argument("--skip-10k", action="store_true",
                   help="Skip 10-K Q4 derivation step")
    args = p.parse_args()
    run_bulk(dry_run=args.dry_run, skip_ingested=args.skip_ingested, skip_10k=args.skip_10k)
