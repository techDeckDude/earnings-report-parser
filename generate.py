from __future__ import annotations
import json, os, sys
from pathlib import Path

os.environ["STATIC_BUILD"] = "true"  # must be set before importing app
from app import app

OUT = Path("static")


def write_json(path: str, data) -> None:
    dest = OUT / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2))
    print(f"  wrote {dest}")


def write_html(path: str, route: str, client) -> None:
    dest = OUT / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(client.get(route).data)
    print(f"  wrote {dest}")


def main() -> None:
    print("Building static site...")
    with app.test_client() as client:
        write_json("api/revenue.json", client.get("/api/revenue").get_json())
        write_json("api/tickers.json", client.get("/api/tickers").get_json())

        tickers = client.get("/api/tickers").get_json()
        for t in tickers:
            ticker = t["ticker"]
            write_json(
                f"api/metrics/{ticker}.json",
                client.get(f"/api/metrics/{ticker}").get_json(),
            )

        # Render HTML with STATIC_BUILD=true active so Jinja injects API_EXT
        write_html("index.html", "/", client)
        write_html("stock/index.html", "/", client)  # clean URL on Cloudflare

    print("Static site written to ./static/")


if __name__ == "__main__":
    main()
