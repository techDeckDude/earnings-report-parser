#!/usr/bin/env python3
"""
Fetch AI stock market news via Claude and store in the database.

Usage:
    python ingest_news.py                       # ingest current week
    python ingest_news.py --week-of 2026-09-04  # ingest 7-day window ending Sep 4
    python ingest_news.py --dry-run             # print JSON without storing
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

try:
    import anthropic
except ImportError:
    sys.exit("anthropic package not found — run: pip install anthropic")

from db import init_db, upsert_news_run

_SKILL_PATH = Path(__file__).parent / ".claude/agents/news-aggregator.md"

_SYSTEM_TMPL = """\
You are the news-aggregator skill. Follow all execution steps in the skill document below exactly.
After completing all steps, output ONLY valid JSON matching the output format — no explanation, no markdown fences.
{override}
{skill}"""


def _extract_json(text: str) -> dict:
    """Find the outermost JSON object containing a 'headlines' key."""
    depth = 0
    start = -1
    for i, c in enumerate(text):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start : i + 1]
                try:
                    obj = json.loads(candidate)
                    if "headlines" in obj:
                        return obj
                except json.JSONDecodeError:
                    pass
                start = -1
    raise ValueError("No JSON object with 'headlines' key found in model response")


def run(dry_run: bool = False, week_of: Optional[str] = None) -> None:
    override = ""
    period_label = "past 7 days"
    week_end_iso = None

    if week_of:
        end = date.fromisoformat(week_of)
        start = end - timedelta(days=6)
        period_label = f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
        week_end_iso = end.isoformat()
        override = (
            f"\n\nDATE RANGE OVERRIDE: Search for news from the 7-day period "
            f"{start.strftime('%B %d, %Y')} through {end.strftime('%B %d, %Y')}. "
            f"Use this specific date range instead of 'past 7 days'. "
            f"In the JSON output, set the 'period' field to '{period_label}'.\n"
        )

    system = _SYSTEM_TMPL.format(override=override, skill=_SKILL_PATH.read_text())
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": "run news-aggregator prompt"}]

    label = period_label if week_of else "current week"
    print(f"Fetching AI stock market news ({label})…", flush=True)

    response = client.beta.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=system,
        messages=messages,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        betas=["web-search-2025-03-05"],
    )

    text = "".join(
        b.text for b in response.content if hasattr(b, "text") and b.text
    )

    data = _extract_json(text)

    if week_end_iso:
        # Fix run_at and period so historical weeks are sorted correctly in the DB
        data["timestamp"] = f"{week_end_iso}T23:59:59+00:00"
        data["period"] = period_label

    if dry_run:
        print(json.dumps(data, indent=2))
        return

    conn = init_db()
    run_id = upsert_news_run(conn, data)
    n = len(data.get("headlines", []))
    print(f"Stored {n} headline{'s' if n != 1 else ''} (run_id={run_id})")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ingest AI stock market news into the database")
    p.add_argument("--dry-run", action="store_true", help="Print JSON without storing")
    p.add_argument(
        "--week-of",
        metavar="DATE",
        help="ISO date (YYYY-MM-DD) of the last day of the target 7-day window",
    )
    args = p.parse_args()
    run(dry_run=args.dry_run, week_of=args.week_of)
