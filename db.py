from __future__ import annotations
import sqlite3
from pathlib import Path
from models import EarningsReport


SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS earnings_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    period          TEXT NOT NULL,
    period_end_date DATE NOT NULL,
    filing_type     TEXT NOT NULL,
    units           TEXT NOT NULL DEFAULT 'thousands',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, period)
);

CREATE TABLE IF NOT EXISTS financial_metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES earnings_reports(id),
    statement       TEXT NOT NULL,   -- 'income_statement', 'balance_sheet', 'cash_flow'
    metric_name     TEXT NOT NULL,
    value           REAL NOT NULL,
    UNIQUE(report_id, statement, metric_name)
);
"""


def init_db(db_path: str = "earnings.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def upsert_report(conn: sqlite3.Connection, report: EarningsReport) -> int:
    """Insert or replace the report and all metrics. Returns report_id."""
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO companies (ticker, name) VALUES (?, ?)",
        (report.ticker, report.company_name),
    )
    cur.execute("SELECT id FROM companies WHERE ticker = ?", (report.ticker,))
    company_id = cur.fetchone()["id"]

    cur.execute(
        """
        INSERT INTO earnings_reports (company_id, period, period_end_date, filing_type, units)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(company_id, period) DO UPDATE SET
            period_end_date = excluded.period_end_date,
            filing_type     = excluded.filing_type,
            units           = excluded.units
        """,
        (
            company_id,
            report.period,
            report.period_end_date.isoformat(),
            report.filing_type,
            report.units,
        ),
    )
    cur.execute(
        "SELECT id FROM earnings_reports WHERE company_id = ? AND period = ?",
        (company_id, report.period),
    )
    report_id = cur.fetchone()["id"]

    metrics: list[tuple[int, str, str, float]] = []
    for statement, model in [
        ("income_statement", report.income_statement),
        ("balance_sheet", report.balance_sheet),
        ("cash_flow", report.cash_flow),
    ]:
        for field_name, value in model.model_dump().items():
            metrics.append((report_id, statement, field_name, float(value)))

    cur.executemany(
        """
        INSERT INTO financial_metrics (report_id, statement, metric_name, value)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(report_id, statement, metric_name) DO UPDATE SET value = excluded.value
        """,
        metrics,
    )

    conn.commit()
    return report_id


def query_report(conn: sqlite3.Connection, ticker: str, period: str) -> dict:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT fm.statement, fm.metric_name, fm.value
        FROM financial_metrics fm
        JOIN earnings_reports er ON fm.report_id = er.id
        JOIN companies c ON er.company_id = c.id
        WHERE c.ticker = ? AND er.period = ?
        ORDER BY fm.statement, fm.metric_name
        """,
        (ticker, period),
    )
    rows = cur.fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        result.setdefault(row["statement"], {})[row["metric_name"]] = row["value"]
    return result
