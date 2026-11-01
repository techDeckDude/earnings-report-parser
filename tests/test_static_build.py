"""
The static build, against the seeded test database, written to a temp folder
(STATIC_OUT) — never over the committed site in static/.
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture
def static_dir(test_db, tmp_path):
    return tmp_path / "static"


def _run(script: str, out: Path) -> subprocess.CompletedProcess:
    # The child inherits the test DB settings conftest put in os.environ.
    return subprocess.run(
        [sys.executable, script],
        cwd=ROOT,
        env={**os.environ, "STATIC_OUT": str(out)},
        capture_output=True,
        text=True,
    )


def test_generate_creates_revenue_json(static_dir):
    _run("generate.py", static_dir)
    assert (static_dir / "api" / "revenue.json").exists()


def test_generate_creates_tickers_json(static_dir):
    _run("generate.py", static_dir)
    assert (static_dir / "api" / "tickers.json").exists()


def test_generate_creates_metrics_per_ticker(static_dir):
    _run("generate.py", static_dir)
    assert (static_dir / "api" / "metrics" / "PLTR.json").exists()
    assert (static_dir / "api" / "metrics" / "MRVL.json").exists()


def test_generate_creates_news_json(static_dir):
    _run("generate.py", static_dir)
    assert (static_dir / "api" / "news.json").exists()


def test_generate_creates_html_pages(static_dir):
    _run("generate.py", static_dir)
    assert (static_dir / "index.html").exists()
    assert (static_dir / "news" / "index.html").exists()
    assert (static_dir / "earnings" / "index.html").exists()


def test_verify_passes_after_generate(static_dir):
    _run("generate.py", static_dir)
    result = _run("verify.py", static_dir)
    assert result.returncode == 0, f"verify.py failed:\n{result.stdout}\n{result.stderr}"
