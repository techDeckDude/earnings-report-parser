from __future__ import annotations
import json
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
    category    TEXT,
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
CREATE TABLE IF NOT EXISTS news_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at              DATETIME NOT NULL,
    period              TEXT NOT NULL,
    total_headlines     INTEGER NOT NULL DEFAULT 0,
    score_distribution  TEXT NOT NULL DEFAULT '{}',
    weighted_sentiment  REAL NOT NULL DEFAULT 0,
    net_sentiment_label TEXT NOT NULL DEFAULT 'Neutral'
);
CREATE TABLE IF NOT EXISTS news_articles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           INTEGER NOT NULL REFERENCES news_runs(id),
    headline         TEXT NOT NULL,
    source           TEXT NOT NULL,
    url              TEXT,
    url_verified     INTEGER NOT NULL DEFAULT 0,
    stocks_mentioned TEXT NOT NULL DEFAULT '[]',
    sentiment_score  INTEGER NOT NULL DEFAULT 0,
    sentiment_label  TEXT NOT NULL DEFAULT 'Neutral',
    summary          TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS target_stocks (
    ticker      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT,
    ingested    INTEGER NOT NULL DEFAULT 0,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

_SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS companies (
    id          SERIAL PRIMARY KEY,
    ticker      TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    category    TEXT,
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
CREATE TABLE IF NOT EXISTS news_runs (
    id                  SERIAL PRIMARY KEY,
    run_at              TIMESTAMPTZ NOT NULL,
    period              TEXT NOT NULL,
    total_headlines     INTEGER NOT NULL DEFAULT 0,
    score_distribution  TEXT NOT NULL DEFAULT '{}',
    weighted_sentiment  DOUBLE PRECISION NOT NULL DEFAULT 0,
    net_sentiment_label TEXT NOT NULL DEFAULT 'Neutral'
);
CREATE TABLE IF NOT EXISTS news_articles (
    id               SERIAL PRIMARY KEY,
    run_id           INTEGER NOT NULL REFERENCES news_runs(id),
    headline         TEXT NOT NULL,
    source           TEXT NOT NULL,
    url              TEXT,
    url_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    stocks_mentioned TEXT NOT NULL DEFAULT '[]',
    sentiment_score  INTEGER NOT NULL DEFAULT 0,
    sentiment_label  TEXT NOT NULL DEFAULT 'Neutral',
    summary          TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS target_stocks (
    ticker      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT,
    ingested    BOOLEAN NOT NULL DEFAULT FALSE,
    added_at    TIMESTAMPTZ DEFAULT NOW()
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

    _execute(conn,
        f"UPDATE target_stocks SET ingested = {1 if not _is_pg(conn) else 'TRUE'} WHERE ticker = {P}",
        (report.ticker,),
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


def upsert_news_run(conn, data: dict) -> int:
    """Insert a news ingestion run and all its articles. Returns run_id."""
    from datetime import datetime, timezone

    P = _ph(conn)
    stats = data.get("summary_stats", {})
    run_at = data.get("timestamp") or datetime.now(timezone.utc).isoformat()
    headlines = data.get("headlines", [])

    cur = _execute(conn, f"""
        INSERT INTO news_runs (run_at, period, total_headlines, score_distribution, weighted_sentiment, net_sentiment_label)
        VALUES ({P}, {P}, {P}, {P}, {P}, {P})
        RETURNING id
        """,
        (
            run_at,
            data.get("period", "past 7 days"),
            stats.get("total_headlines", len(headlines)),
            json.dumps(stats.get("score_distribution", {})),
            stats.get("weighted_sentiment", 0.0),
            stats.get("net_sentiment_label", "Neutral"),
        ),
    )
    run_id = cur.fetchone()["id"]

    _executemany(conn, f"""
        INSERT INTO news_articles
            (run_id, headline, source, url, url_verified, stocks_mentioned, sentiment_score, sentiment_label, summary)
        VALUES ({P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P})
        """,
        [
            (
                run_id,
                a["headline"],
                a["source"],
                a.get("url"),
                1 if a.get("url_verified") else 0,
                json.dumps(a.get("stocks_mentioned", [])),
                a.get("sentiment_score", 0),
                a.get("sentiment_label", "Neutral"),
                a.get("summary", ""),
            )
            for a in headlines
        ],
    )

    conn.commit()
    return run_id


def get_all_news_runs(conn) -> list[dict]:
    """Return all ingestion runs with their articles, newest first."""
    runs = _execute(conn, """
        SELECT id, run_at, period, total_headlines, score_distribution, weighted_sentiment, net_sentiment_label
        FROM news_runs
        ORDER BY run_at DESC
    """).fetchall()

    result = []
    for run in runs:
        articles = _execute(conn, f"""
            SELECT headline, source, url, url_verified, stocks_mentioned, sentiment_score, sentiment_label, summary
            FROM news_articles
            WHERE run_id = {_ph(conn)}
            ORDER BY id
            """,
            (run["id"],),
        ).fetchall()

        run_at = run["run_at"]
        if not isinstance(run_at, str):
            run_at = run_at.isoformat()

        result.append({
            "run_id": run["id"],
            "run_at": run_at,
            "period": run["period"],
            "headlines": [
                {
                    "headline": a["headline"],
                    "source": a["source"],
                    "url": a["url"],
                    "url_verified": bool(a["url_verified"]),
                    "stocks_mentioned": json.loads(a["stocks_mentioned"]),
                    "sentiment_score": a["sentiment_score"],
                    "sentiment_label": a["sentiment_label"],
                    "summary": a["summary"],
                }
                for a in articles
            ],
            "summary_stats": {
                "total_headlines": run["total_headlines"],
                "score_distribution": json.loads(run["score_distribution"]),
                "weighted_sentiment": run["weighted_sentiment"],
                "net_sentiment_label": run["net_sentiment_label"],
            },
        })

    return result


def get_latest_news(conn) -> dict | None:
    """Return the most recent ingestion run with all its articles, or None."""
    run = _execute(conn, """
        SELECT id, run_at, period, total_headlines, score_distribution, weighted_sentiment, net_sentiment_label
        FROM news_runs
        ORDER BY run_at DESC
        LIMIT 1
    """).fetchone()

    if not run:
        return None

    articles = _execute(conn, f"""
        SELECT headline, source, url, url_verified, stocks_mentioned, sentiment_score, sentiment_label, summary
        FROM news_articles
        WHERE run_id = {_ph(conn)}
        ORDER BY id
        """,
        (run["id"],),
    ).fetchall()

    run_at = run["run_at"]
    if not isinstance(run_at, str):
        run_at = run_at.isoformat()

    return {
        "run_at": run_at,
        "period": run["period"],
        "headlines": [
            {
                "headline": a["headline"],
                "source": a["source"],
                "url": a["url"],
                "url_verified": bool(a["url_verified"]),
                "stocks_mentioned": json.loads(a["stocks_mentioned"]),
                "sentiment_score": a["sentiment_score"],
                "sentiment_label": a["sentiment_label"],
                "summary": a["summary"],
            }
            for a in articles
        ],
        "summary_stats": {
            "total_headlines": run["total_headlines"],
            "score_distribution": json.loads(run["score_distribution"]),
            "weighted_sentiment": run["weighted_sentiment"],
            "net_sentiment_label": run["net_sentiment_label"],
        },
    }
