from __future__ import annotations
import pytest
from db import _execute, upsert_report


# ── Schema ────────────────────────────────────────────────────────────────────

def test_init_creates_all_tables(mem_db):
    tables = {row[0] for row in mem_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    expected = {"companies", "earnings_reports", "financial_metrics",
                "news_runs", "news_articles", "target_stocks"}
    assert expected.issubset(tables)


# ── upsert_report ─────────────────────────────────────────────────────────────

def test_upsert_report_creates_company(mem_db, sample_pltr_report):
    upsert_report(mem_db, sample_pltr_report)
    row = mem_db.execute("SELECT ticker FROM companies WHERE ticker='PLTR'").fetchone()
    assert row is not None


def test_upsert_report_creates_earnings_report(mem_db, sample_pltr_report):
    upsert_report(mem_db, sample_pltr_report)
    row = mem_db.execute(
        "SELECT period FROM earnings_reports WHERE period='Q2 2026'"
    ).fetchone()
    assert row is not None


def test_upsert_report_creates_metrics(mem_db, sample_pltr_report):
    upsert_report(mem_db, sample_pltr_report)
    count = mem_db.execute("SELECT COUNT(*) FROM financial_metrics").fetchone()[0]
    assert count > 0


def test_upsert_report_idempotent(mem_db, sample_pltr_report):
    upsert_report(mem_db, sample_pltr_report)
    upsert_report(mem_db, sample_pltr_report)
    count = mem_db.execute("SELECT COUNT(*) FROM earnings_reports").fetchone()[0]
    assert count == 1


def test_upsert_two_periods_same_company(mem_db, sample_pltr_report, sample_mrvl_report):
    # Two different companies → two companies, two reports
    upsert_report(mem_db, sample_pltr_report)
    upsert_report(mem_db, sample_mrvl_report)
    company_count = mem_db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    report_count = mem_db.execute("SELECT COUNT(*) FROM earnings_reports").fetchone()[0]
    assert company_count == 2
    assert report_count == 2


def test_upsert_marks_target_stock_ingested(mem_db, sample_pltr_report):
    mem_db.execute(
        "INSERT INTO target_stocks (ticker, name, ingested) VALUES ('PLTR', 'Palantir', 0)"
    )
    mem_db.commit()
    upsert_report(mem_db, sample_pltr_report)
    row = mem_db.execute(
        "SELECT ingested FROM target_stocks WHERE ticker='PLTR'"
    ).fetchone()
    assert row[0] == 1


def test_upsert_no_target_stock_no_error(mem_db, sample_pltr_report):
    # ticker not in target_stocks → should not raise
    upsert_report(mem_db, sample_pltr_report)
    count = mem_db.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    assert count == 1
