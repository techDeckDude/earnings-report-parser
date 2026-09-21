#!/usr/bin/env python3
"""
Fetch AI stock market news via Claude and store in the database.

Usage:
    python ingest_news.py           # ingest from last article date to today
    python ingest_news.py --dry-run # print JSON without storing
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("anthropic package not found — run: pip install anthropic")

from db import init_db, upsert_news_run, get_latest_news_date

_SKILL_PATH = Path(__file__).parent / ".claude/agents/news-aggregator.md"

_SYSTEM_TMPL = """\
You are the news-aggregator skill. Follow all execution steps in the skill document below exactly.
After completing all steps, output ONLY valid JSON matching the output format — no explanation, no markdown fences.

DATE RANGE: Search for news published between {start_date} and {end_date}.
Each article's published_date must fall within this range and must be >= {start_date}.
Do not include articles published before {start_date} or after {end_date}.
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


def run(dry_run: bool = False) -> None:
    conn = init_db()
    latest = get_latest_news_date(conn)

    start = (latest + timedelta(days=1)) if latest else (date.today() - timedelta(days=6))
    end = date.today()

    period_label = (
        f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
        if start != end
        else start.strftime("%b %d, %Y")
    )

    system = _SYSTEM_TMPL.format(
        start_date=start.strftime("%B %d, %Y"),
        end_date=end.strftime("%B %d, %Y"),
        skill=_SKILL_PATH.read_text(),
    )
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": "run news-aggregator prompt"}]

    print(f"Fetching AI stock market news ({period_label})…", flush=True)

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

    # Overwrite timestamp and period with computed values so DB sorting is correct
    data["timestamp"] = f"{end.isoformat()}T23:59:59+00:00"
    data["period"] = period_label

    if dry_run:
        print(json.dumps(data, indent=2))
        return

    run_id = upsert_news_run(conn, data)
    n = len(data.get("headlines", []))
    print(f"Stored {n} headline{'s' if n != 1 else ''} (run_id={run_id})")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Ingest AI stock market news into the database")
    p.add_argument("--dry-run", action="store_true", help="Print JSON without storing")
    args = p.parse_args()
    run(dry_run=args.dry_run)
