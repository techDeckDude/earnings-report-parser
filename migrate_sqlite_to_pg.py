"""
One-shot migration: copies all data from earnings.db (SQLite) into the
Postgres instance defined by DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT.

Run once:
    python3 migrate_sqlite_to_pg.py
"""
import os, sqlite3
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = os.environ.get("SQLITE_PATH", "earnings.db")

sqlite = sqlite3.connect(SQLITE_PATH)
sqlite.row_factory = sqlite3.Row

pg = psycopg2.connect(
    host=os.environ["DB_HOST"],
    dbname=os.environ.get("DB_NAME", "appdb"),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    port=int(os.environ.get("DB_PORT", 5432)),
)
pg.autocommit = False
cur = pg.cursor()

# ── Ensure schema exists ──────────────────────────────────────────────────────
from db import _SCHEMA_PG, _MIGRATIONS_PG
for stmt in _SCHEMA_PG.strip().split(";"):
    stmt = stmt.strip()
    if stmt:
        cur.execute(stmt)
for stmt in _MIGRATIONS_PG:
    cur.execute(stmt)
pg.commit()

# ── companies ─────────────────────────────────────────────────────────────────
rows = sqlite.execute("SELECT ticker, name, category, created_at FROM companies ORDER BY id").fetchall()
print(f"Migrating {len(rows)} companies...")
for r in rows:
    cur.execute("""
        INSERT INTO companies (ticker, name, category, created_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (ticker) DO NOTHING
    """, (r["ticker"], r["name"], r["category"], r["created_at"]))
pg.commit()

# Build ticker → pg id map
cur.execute("SELECT id, ticker FROM companies")
company_id_map = {row[1]: row[0] for row in cur.fetchall()}

# ── earnings_reports ──────────────────────────────────────────────────────────
rows = sqlite.execute("""
    SELECT er.id AS sqlite_id, c.ticker, er.period, er.period_end_date,
           er.filing_type, er.units, er.created_at
    FROM earnings_reports er
    JOIN companies c ON c.id = er.company_id
    ORDER BY er.id
""").fetchall()
print(f"Migrating {len(rows)} earnings reports...")
report_id_map = {}  # sqlite_id → pg_id
for r in rows:
    pg_company_id = company_id_map[r["ticker"]]
    cur.execute("""
        INSERT INTO earnings_reports (company_id, period, period_end_date, filing_type, units, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (company_id, period) DO NOTHING
        RETURNING id
    """, (pg_company_id, r["period"], r["period_end_date"], r["filing_type"], r["units"], r["created_at"]))
    result = cur.fetchone()
    if result:
        report_id_map[r["sqlite_id"]] = result[0]
    else:
        # Already existed — look it up
        cur.execute("SELECT id FROM earnings_reports WHERE company_id=%s AND period=%s",
                    (pg_company_id, r["period"]))
        report_id_map[r["sqlite_id"]] = cur.fetchone()[0]
pg.commit()

# ── financial_metrics ─────────────────────────────────────────────────────────
rows = sqlite.execute("""
    SELECT report_id, statement, metric_name, value
    FROM financial_metrics ORDER BY id
""").fetchall()
print(f"Migrating {len(rows)} financial metrics...")
batch = []
for r in rows:
    pg_report_id = report_id_map.get(r["report_id"])
    if pg_report_id is None:
        continue
    batch.append((pg_report_id, r["statement"], r["metric_name"], r["value"]))
psycopg2.extras.execute_values(cur, """
    INSERT INTO financial_metrics (report_id, statement, metric_name, value)
    VALUES %s ON CONFLICT (report_id, statement, metric_name) DO NOTHING
""", batch)
pg.commit()

# ── target_stocks ─────────────────────────────────────────────────────────────
rows = sqlite.execute("SELECT ticker, name, category, cik, ingested, added_at, earliest_xbrl_period FROM target_stocks").fetchall()
print(f"Migrating {len(rows)} target stocks...")
for r in rows:
    cur.execute("""
        INSERT INTO target_stocks (ticker, name, category, cik, ingested, added_at, earliest_xbrl_period)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ticker) DO UPDATE SET
            name=EXCLUDED.name, category=EXCLUDED.category,
            cik=EXCLUDED.cik, ingested=EXCLUDED.ingested,
            earliest_xbrl_period=EXCLUDED.earliest_xbrl_period
    """, (r["ticker"], r["name"], r["category"], r["cik"],
          bool(r["ingested"]), r["added_at"], r["earliest_xbrl_period"]))
pg.commit()

# ── news_runs ─────────────────────────────────────────────────────────────────
rows = sqlite.execute("SELECT id, run_at, period, total_headlines, score_distribution, weighted_sentiment, net_sentiment_label FROM news_runs ORDER BY id").fetchall()
print(f"Migrating {len(rows)} news runs...")
news_run_id_map = {}
for r in rows:
    cur.execute("""
        INSERT INTO news_runs (run_at, period, total_headlines, score_distribution, weighted_sentiment, net_sentiment_label)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    """, (r["run_at"], r["period"], r["total_headlines"], r["score_distribution"],
          r["weighted_sentiment"], r["net_sentiment_label"]))
    news_run_id_map[r["id"]] = cur.fetchone()[0]
pg.commit()

# ── news_articles ─────────────────────────────────────────────────────────────
rows = sqlite.execute("SELECT run_id, headline, source, url, url_verified, stocks_mentioned, sentiment_score, sentiment_label, summary, published_date FROM news_articles ORDER BY id").fetchall()
print(f"Migrating {len(rows)} news articles...")
batch = []
for r in rows:
    pg_run_id = news_run_id_map.get(r["run_id"])
    if pg_run_id is None:
        continue
    batch.append((pg_run_id, r["headline"], r["source"], r["url"], bool(r["url_verified"]),
                  r["stocks_mentioned"], r["sentiment_score"], r["sentiment_label"],
                  r["summary"], r["published_date"]))
psycopg2.extras.execute_values(cur, """
    INSERT INTO news_articles (run_id, headline, source, url, url_verified, stocks_mentioned,
                               sentiment_score, sentiment_label, summary, published_date)
    VALUES %s
""", batch)
pg.commit()

sqlite.close()
pg.close()
print("Migration complete.")
