from __future__ import annotations

import pytest
from unittest.mock import patch

from edgar import FilingRecord, get_cik, get_new_filings


# ── Fixture data matching real EDGAR API shapes ───────────────────────────────

SAMPLE_TICKERS = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 1321655, "ticker": "PLTR", "title": "Palantir Technologies Inc."},
    "2": {"cik_str": 1835632, "ticker": "MRVL", "title": "Marvell Technology, Inc."},
}

SAMPLE_SUBMISSIONS = {
    "name": "NVIDIA CORP",
    "tickers": ["NVDA"],
    "filings": {
        "recent": {
            "accessionNumber": [
                "0001045810-25-000050",
                "0001045810-24-000099",
                "0001045810-24-000050",
                "0001045810-24-000010",
            ],
            "filingDate": [
                "2025-06-05",
                "2024-11-20",
                "2024-08-28",
                "2024-12-15",
            ],
            "reportDate": [
                "2025-04-27",
                "2024-10-27",
                "2024-07-28",
                "2024-10-27",
            ],
            "form": ["10-Q", "10-Q", "10-Q", "10-K"],
        }
    },
}


# ── get_cik ───────────────────────────────────────────────────────────────────

def test_get_cik_returns_zero_padded():
    with patch("edgar._rate_limited_get", return_value=SAMPLE_TICKERS):
        assert get_cik("NVDA") == "0001045810"


def test_get_cik_case_insensitive():
    with patch("edgar._rate_limited_get", return_value=SAMPLE_TICKERS):
        assert get_cik("nvda") == "0001045810"


def test_get_cik_unknown_ticker_raises():
    with patch("edgar._rate_limited_get", return_value=SAMPLE_TICKERS):
        with pytest.raises(ValueError, match="AAPL"):
            get_cik("AAPL")


def test_get_cik_caches_in_db(mem_db):
    mem_db.execute("INSERT OR IGNORE INTO target_stocks (ticker, name) VALUES ('NVDA', 'NVIDIA CORP')")
    mem_db.commit()
    with patch("edgar._rate_limited_get", return_value=SAMPLE_TICKERS):
        cik = get_cik("NVDA", conn=mem_db)
    assert cik == "0001045810"
    row = mem_db.execute("SELECT cik FROM target_stocks WHERE ticker='NVDA'").fetchone()
    assert row["cik"] == "0001045810"


def test_get_cik_reads_from_cache_no_network(mem_db):
    mem_db.execute(
        "INSERT OR IGNORE INTO target_stocks (ticker, name, cik) VALUES ('NVDA', 'NVIDIA CORP', '0001045810')"
    )
    mem_db.commit()
    with patch("edgar._rate_limited_get") as mock_get:
        cik = get_cik("NVDA", conn=mem_db)
    assert cik == "0001045810"
    mock_get.assert_not_called()


# ── get_new_filings ───────────────────────────────────────────────────────────

def test_get_new_filings_returns_all_without_since_date():
    with patch("edgar._rate_limited_get", return_value=SAMPLE_SUBMISSIONS):
        filings = get_new_filings("NVDA", "0001045810")
    # 3 x 10-Q, 1 x 10-K — only 10-Qs returned
    assert len(filings) == 3
    assert all(isinstance(f, FilingRecord) for f in filings)


def test_get_new_filings_skips_non_10q():
    with patch("edgar._rate_limited_get", return_value=SAMPLE_SUBMISSIONS):
        filings = get_new_filings("NVDA", "0001045810")
    assert all(f.filed_date != "2024-12-15" for f in filings)  # 10-K excluded


def test_get_new_filings_filters_by_since_date():
    with patch("edgar._rate_limited_get", return_value=SAMPLE_SUBMISSIONS):
        filings = get_new_filings("NVDA", "0001045810", since_date="2024-10-27")
    # only 2025-04-27 is strictly > 2024-10-27
    assert len(filings) == 1
    assert filings[0].period_end == "2025-04-27"


def test_get_new_filings_sorted_oldest_first():
    with patch("edgar._rate_limited_get", return_value=SAMPLE_SUBMISSIONS):
        filings = get_new_filings("NVDA", "0001045810")
    dates = [f.period_end for f in filings]
    assert dates == sorted(dates)


def test_get_new_filings_record_fields():
    with patch("edgar._rate_limited_get", return_value=SAMPLE_SUBMISSIONS):
        filings = get_new_filings("NVDA", "0001045810")
    newest = filings[-1]
    assert newest.ticker == "NVDA"
    assert newest.cik == "0001045810"
    assert newest.accession_number == "0001045810-25-000050"
    assert newest.period_end == "2025-04-27"
    assert newest.filed_date == "2025-06-05"


def test_get_new_filings_empty_when_all_filtered():
    with patch("edgar._rate_limited_get", return_value=SAMPLE_SUBMISSIONS):
        filings = get_new_filings("NVDA", "0001045810", since_date="2025-12-31")
    assert filings == []
