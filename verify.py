from __future__ import annotations
import json, sys
from pathlib import Path

from app import app  # live mode — no STATIC_BUILD env var


def main() -> None:
    with app.test_client() as client:
        tickers = client.get("/api/tickers").get_json()
        checks = [
            ("/api/revenue",  "static/api/revenue.json"),
            ("/api/tickers",  "static/api/tickers.json"),
        ]
        for t in tickers:
            ticker = t["ticker"]
            checks.append((
                f"/api/metrics/{ticker}",
                f"static/api/metrics/{ticker}.json",
            ))

        ok = True
        for route, path in checks:
            static_path = Path(path)
            if not static_path.exists():
                print(f"  MISSING  {path}  ← run generate.py first")
                ok = False
                continue

            live   = client.get(route).get_json()
            static = json.loads(static_path.read_text())

            if live == static:
                print(f"  ✓  {route}")
            else:
                print(f"  ✗  {route}  ← MISMATCH")
                ok = False

    print()
    if ok:
        print("All in sync.")
    else:
        print("Out of sync — run generate.py to rebuild.")
        sys.exit(1)


if __name__ == "__main__":
    main()
