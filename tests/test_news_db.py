from __future__ import annotations
import pytest
from db import upsert_news_run, get_all_news_runs, get_latest_news


SAMPLE_RUN = {
    "timestamp": "2026-09-11T23:59:59+00:00",
    "period": "Sep 05 – Sep 11, 2026",
    "headlines": [
        {
            "headline": "NVIDIA reports record revenue",
            "source": "Reuters",
            "url": "https://reuters.com/nvda",
            "url_verified": True,
            "stocks_mentioned": ["NVDA"],
            "sentiment_score": 2,
            "sentiment_label": "Very Positive",
            "summary": "NVIDIA beats estimates.",
        },
        {
            "headline": "AI chip demand slows in Q3",
            "source": "Bloomberg",
            "url": "https://bloomberg.com/ai-chips",
            "url_verified": False,
            "stocks_mentioned": ["NVDA", "AMD"],
            "sentiment_score": -1,
            "sentiment_label": "Negative",
            "summary": "Analysts warn of softening demand.",
        },
    ],
    "summary_stats": {
        "total_headlines": 2,
        "score_distribution": {"2": 1, "-1": 1},
        "weighted_sentiment": 0.5,
        "net_sentiment_label": "Slightly Positive",
    },
}

OLDER_RUN = {**SAMPLE_RUN, "timestamp": "2026-09-04T23:59:59+00:00", "period": "Aug 29 – Sep 04, 2026"}


def test_upsert_news_run_creates_run(mem_db):
    run_id = upsert_news_run(mem_db, SAMPLE_RUN)
    row = mem_db.execute("SELECT id FROM news_runs WHERE id=?", (run_id,)).fetchone()
    assert row is not None


def test_upsert_news_run_creates_articles(mem_db):
    run_id = upsert_news_run(mem_db, SAMPLE_RUN)
    count = mem_db.execute(
        "SELECT COUNT(*) FROM news_articles WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    assert count == 2


def test_get_all_news_runs_newest_first(mem_db):
    upsert_news_run(mem_db, OLDER_RUN)
    upsert_news_run(mem_db, SAMPLE_RUN)
    runs = get_all_news_runs(mem_db)
    assert runs[0]["run_at"] > runs[1]["run_at"]


def test_get_all_news_runs_includes_articles(mem_db):
    upsert_news_run(mem_db, SAMPLE_RUN)
    runs = get_all_news_runs(mem_db)
    assert len(runs[0]["headlines"]) == 2


def test_get_all_news_runs_empty_db(mem_db):
    assert get_all_news_runs(mem_db) == []


def test_get_latest_news_returns_most_recent(mem_db):
    upsert_news_run(mem_db, OLDER_RUN)
    upsert_news_run(mem_db, SAMPLE_RUN)
    latest = get_latest_news(mem_db)
    assert latest["period"] == SAMPLE_RUN["period"]


def test_get_latest_news_empty_db(mem_db):
    assert get_latest_news(mem_db) is None
