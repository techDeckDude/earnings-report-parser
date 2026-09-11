#!/usr/bin/env python3
"""
Fetch AI stock market news via Claude and store in the database.

Usage:
    python ingest_news.py           # ingest and store
    python ingest_news.py --dry-run # print JSON without storing
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import anthropic
except ImportError:
    sys.exit("anthropic package not found — run: pip install anthropic")

from db import init_db, upsert_news_run

_SKILL_PATH = Path(__file__).parent / ".claude/agents/news-aggregator.md"

_SYSTEM = f"""You are the news-aggregator skill. Follow all execution steps in the skill document below exactly.
After completing all steps, output ONLY valid JSON matching the output format — no explanation, no markdown fences.

{_SKILL_PATH.read_text()}"""


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
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": "run news-aggregator prompt"}]

    print("Fetching AI stock market news…", flush=True)

    response = client.beta.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=_SYSTEM,
        messages=messages,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        betas=["web-search-2025-03-05"],
    )

    # Collect text from all content blocks (model may interleave searches with text)
    text = "".join(
        b.text for b in response.content if hasattr(b, "text") and b.text
    )

    data = _extract_json(text)

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
    args = p.parse_args()
    run(dry_run=args.dry_run)
