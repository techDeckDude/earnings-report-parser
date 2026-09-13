from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Optional

USER_AGENT = "earnings-report-parser/1.0 justinbullock025@gmail.com"
_RATE_INTERVAL = 1.0 / 10  # 10 requests/second max per EDGAR policy
_last_request: float = 0.0


@dataclass
class FilingRecord:
    ticker: str
    cik: str           # 10-digit zero-padded, e.g. "0001045810"
    accession_number: str
    period_end: str    # YYYY-MM-DD  (reportDate from EDGAR)
    filed_date: str    # YYYY-MM-DD  (filingDate from EDGAR)


def _rate_limited_get(url: str) -> dict:
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < _RATE_INTERVAL:
        time.sleep(_RATE_INTERVAL - elapsed)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    _last_request = time.monotonic()
    return data


def get_cik(ticker: str, conn=None) -> str:
    """
    Return the 10-digit zero-padded CIK for ticker.

    If conn is provided, reads from target_stocks.cik first (cache hit = no
    network request) and writes back on a cache miss.
    """
    if conn is not None:
        from db import _execute, _ph
        row = _execute(
            conn,
            f"SELECT cik FROM target_stocks WHERE ticker = {_ph(conn)}",
            (ticker,),
        ).fetchone()
        if row and row["cik"]:
            return row["cik"]

    data = _rate_limited_get("https://www.sec.gov/files/company_tickers.json")
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry["ticker"].upper() == ticker_upper:
            cik = str(entry["cik_str"]).zfill(10)
            if conn is not None:
                from db import _execute, _ph
                _execute(
                    conn,
                    f"UPDATE target_stocks SET cik = {_ph(conn)} WHERE ticker = {_ph(conn)}",
                    (cik, ticker),
                )
                conn.commit()
            return cik

    raise ValueError(f"Ticker {ticker!r} not found in SEC company tickers list")


def get_new_filings(
    ticker: str,
    cik: str,
    since_date: Optional[str] = None,
) -> list[FilingRecord]:
    """
    Return 10-Q FilingRecords for ticker where reportDate > since_date.

    since_date: YYYY-MM-DD string representing the last ingested period end.
                Pass None to return all 10-Q filings on record.
    Results are sorted oldest-first so the pipeline processes them in order.
    """
    data = _rate_limited_get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    recent = data["filings"]["recent"]

    forms = recent["form"]
    accessions = recent["accessionNumber"]
    report_dates = recent["reportDate"]
    filing_dates = recent["filingDate"]

    results: list[FilingRecord] = []
    for i, form in enumerate(forms):
        if form != "10-Q":
            continue
        period_end = report_dates[i]
        if not period_end:
            continue
        if since_date and period_end <= since_date:
            continue
        results.append(FilingRecord(
            ticker=ticker,
            cik=cik,
            accession_number=accessions[i],
            period_end=period_end,
            filed_date=filing_dates[i],
        ))

    results.sort(key=lambda r: r.period_end)
    return results
