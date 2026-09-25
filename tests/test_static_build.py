from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATIC = ROOT / "static"


def _run(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_generate_creates_revenue_json():
    _run("generate.py")
    assert (STATIC / "api" / "revenue.json").exists()


def test_generate_creates_tickers_json():
    _run("generate.py")
    assert (STATIC / "api" / "tickers.json").exists()


def test_generate_creates_metrics_per_ticker():
    _run("generate.py")
    assert (STATIC / "api" / "metrics" / "PLTR.json").exists()
    assert (STATIC / "api" / "metrics" / "MRVL.json").exists()


def test_generate_creates_news_json():
    _run("generate.py")
    assert (STATIC / "api" / "news.json").exists()


def test_generate_creates_html_pages():
    _run("generate.py")
    assert (STATIC / "index.html").exists()
    assert (STATIC / "news" / "index.html").exists()
    assert (STATIC / "earnings" / "index.html").exists()


def test_verify_passes_after_generate():
    _run("generate.py")
    result = _run("verify.py")
    assert result.returncode == 0, f"verify.py failed:\n{result.stdout}\n{result.stderr}"
