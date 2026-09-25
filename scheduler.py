#!/usr/bin/env python3
"""
Runs ingest_news.py on a configurable interval.

Usage:
    python scheduler.py                       # every 24 hours (default)
    INGEST_INTERVAL_HOURS=12 python scheduler.py
    INGEST_INTERVAL_HOURS=0.5 python scheduler.py  # every 30 minutes

To run in the background:
    nohup python scheduler.py > logs/scheduler.log 2>&1 &
"""
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

try:
    from setproctitle import setproctitle
    setproctitle("earnings-news-scheduler")
except ImportError:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

INTERVAL_HOURS = float(os.getenv("INGEST_INTERVAL_HOURS", "24"))
INTERVAL_SECONDS = INTERVAL_HOURS * 3600


def run_once() -> int:
    log.info("Starting ingestion run")
    result = subprocess.run(
        [sys.executable, "ingest_news.py"],
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        log.info(result.stdout.strip())
    if result.returncode != 0:
        log.error("Ingestion failed (exit %d):\n%s", result.returncode, result.stderr.strip())
    else:
        log.info("Ingestion completed successfully")
    return result.returncode


if __name__ == "__main__":
    log.info("Scheduler started — interval: %.4g hours", INTERVAL_HOURS)
    while True:
        run_once()
        next_run = datetime.now() + timedelta(seconds=INTERVAL_SECONDS)
        log.info("Next run: %s", next_run.strftime("%Y-%m-%d %H:%M:%S"))
        time.sleep(INTERVAL_SECONDS)
