"""
Tests run against a throwaway Postgres (the same one core-data's tests use),
never the database in .env:

    docker run -d --rm --name core-data-test-pg -p 55432:5432 \
        -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=earningsdb postgres:16

Database tests are skipped if it isn't reachable.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

# Must happen before anything imports app: app.py loads .env, and load_dotenv
# never overrides variables that are already set — so these win.
TEST_DB = dict(DB_HOST="localhost", DB_PORT="55432", DB_USER="test", DB_PASSWORD="test",
               DB_NAME="earningsdb", DB_POOL_MAX="4", DB_POOL_TIMEOUT="5", DB_CONNECT_TIMEOUT="3")
os.environ.update(TEST_DB)

import psycopg
import pytest

from core_data.db import close_pool, migrate
from core_data.ingestion import store_report
from core_data.models import EarningsReport

FIXTURES = Path(__file__).parent / "fixtures"
_CONNINFO = "postgresql://test:test@localhost:55432/earningsdb"

SAMPLE_NEWS = {
    "timestamp": "2026-09-30T23:59:59+00:00",
    "period": "Sep 24 – Sep 30, 2026",
    "summary_stats": {"total_headlines": 1, "score_distribution": {"1": 1},
                      "weighted_sentiment": 1.0, "net_sentiment_label": "Positive"},
    "headlines": [{"headline": "Chips rally", "source": "Wire", "sentiment_score": 1,
                   "sentiment_label": "Positive", "published_date": "2026-09-29",
                   "stocks_mentioned": ["NVDA"]}],
}


def _load_fixture(name: str) -> EarningsReport:
    return EarningsReport.model_validate(json.loads((FIXTURES / name).read_text()))


@pytest.fixture(scope="session")
def sample_pltr_report() -> EarningsReport:
    return _load_fixture("pltr_q2_2026.json")


@pytest.fixture(scope="session")
def sample_mrvl_report() -> EarningsReport:
    return _load_fixture("mrvl_q3_2024.json")


@pytest.fixture
def test_db(sample_pltr_report, sample_mrvl_report):
    """A freshly migrated test database holding the PLTR and MRVL fixture reports and one news run."""
    try:
        conn = psycopg.connect(_CONNINFO, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError as e:
        pytest.skip(f"test Postgres not reachable: {e}")
    with conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    close_pool()
    migrate()
    store_report(sample_pltr_report)
    store_report(sample_mrvl_report)

    from core_data.db import transaction
    from core_data.repositories import news
    with transaction() as c:
        news.insert_run(c, SAMPLE_NEWS)
    yield
    close_pool()


@pytest.fixture
def flask_client(test_db):
    from app import app as flask_app
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
