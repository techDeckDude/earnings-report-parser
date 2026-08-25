from __future__ import annotations
import os
import sqlite3
from models import EarningsReport

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA_SQLITE = """
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
    statement       TEXT NOT NULL,
    metric_name     TEXT NOT NULL,
    value           REAL NOT NULL,
    UNIQUE(report_id, statement, metric_name)
);
"""

_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS companies (
    id          SERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS earnings_reports (
    id              SERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    period          TEXT NOT NULL,
    period_end_date DATE NOT NULL,
    filing_type     TEXT NOT NULL,
    units           TEXT NOT NULL DEFAULT 'thousands',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, period)
);
CREATE TABLE IF NOT EXISTS financial_metrics (
    id              SERIAL PRIMARY KEY,
    report_id       INTEGER NOT NULL REFERENCES earnings_reports(id),
    statement       TEXT NOT NULL,
    metric_name     TEXT NOT NULL,
    value           DOUBLE PRECISION NOT NULL,
    UNIQUE(report_id, statement, metric_name)
);
"""


# ── Backend detection ─────────────────────────────────────────────────────────

def _is_pg(conn) -> bool:
    return not isinstance(conn, sqlite3.Connection)


def _ph(conn) -> str:
    """Parameter placeholder for the given connection."""
    return "%s" if _is_pg(conn) else "?"


def _execute(conn, sql: str, params=()):
    """Unified execute that works for both sqlite3 and psycopg2."""
    if _is_pg(conn):
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur
    return conn.execute(sql, params)


def _executemany(conn, sql: str, params_list):
    if _is_pg(conn):
        conn.cursor().executemany(sql, params_list)
    else:
        conn.executemany(sql, params_list)


# ── Public API ────────────────────────────────────────────────────────────────

def init_db(db_path: str = "earnings.db"):
    """
    Return an open DB connection. Uses Postgres when DB_HOST is set,
    otherwise falls back to SQLite for local development.
    """
    if os.environ.get("DB_HOST"):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed. Run: pip install psycopg2-binary")
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            dbname=os.environ.get("DB_NAME", "earningsdb"),
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            port=int(os.environ.get("DB_PORT", 5432)),
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        cur = conn.cursor()
        for stmt in _SCHEMA_PG.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)
        conn.commit()
        return conn
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA_SQLITE)
        conn.commit()
        return conn


def upsert_report(conn, report: EarningsReport) -> int:
    """Insert or update the report and all metrics. Returns report_id."""
    P = _ph(conn)

    if _is_pg(conn):
        _execute(conn,
            f"INSERT INTO companies (ticker, name) VALUES ({P}, {P}) ON CONFLICT(ticker) DO NOTHING",
            (report.ticker, report.company_name),
        )
    else:
        _execute(conn,
            f"INSERT OR IGNORE INTO companies (ticker, name) VALUES ({P}, {P})",
            (report.ticker, report.company_name),
        )

    company_id = _execute(conn,
        f"SELECT id FROM companies WHERE ticker = {P}", (report.ticker,)
    ).fetchone()["id"]

    _execute(conn, f"""
        INSERT INTO earnings_reports (company_id, period, period_end_date, filing_type, units)
        VALUES ({P}, {P}, {P}, {P}, {P})
        ON CONFLICT(company_id, period) DO UPDATE SET
            period_end_date = EXCLUDED.period_end_date,
            filing_type     = EXCLUDED.filing_type,
            units           = EXCLUDED.units
        """,
        (company_id, report.period, report.period_end_date.isoformat(),
         report.filing_type, report.units),
    )

    report_id = _execute(conn,
        f"SELECT id FROM earnings_reports WHERE company_id = {P} AND period = {P}",
        (company_id, report.period),
    ).fetchone()["id"]

    metrics = [
        (report_id, statement, field_name, float(value))
        for statement, model in [
            ("income_statement", report.income_statement),
            ("balance_sheet",    report.balance_sheet),
            ("cash_flow",        report.cash_flow),
        ]
        for field_name, value in model.model_dump().items()
        if value is not None
    ]

    _executemany(conn, f"""
        INSERT INTO financial_metrics (report_id, statement, metric_name, value)
        VALUES ({P}, {P}, {P}, {P})
        ON CONFLICT(report_id, statement, metric_name) DO UPDATE SET value = EXCLUDED.value
        """,
        metrics,
    )

    conn.commit()
    return report_id


def query_report(conn, ticker: str, period: str) -> dict:
    P = _ph(conn)
    rows = _execute(conn, f"""
        SELECT fm.statement, fm.metric_name, fm.value
        FROM financial_metrics fm
        JOIN earnings_reports er ON fm.report_id = er.id
        JOIN companies c ON er.company_id = c.id
        WHERE c.ticker = {P} AND er.period = {P}
        ORDER BY fm.statement, fm.metric_name
        """,
        (ticker, period),
    ).fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        result.setdefault(row["statement"], {})[row["metric_name"]] = row["value"]
    return result
