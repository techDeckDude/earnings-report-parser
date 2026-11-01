from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

# Load .env before core-data reads the DB_* settings
load_dotenv(Path(__file__).parent / ".env")

from core_data.db import DbSettings
from core_data.flask import init_app, request_connection
from core_data.repositories import earnings, news

app = Flask(__name__)
# One pooled connection per request, always returned (core-data owns connections;
# this replaces a single global connection shared by every request thread).
init_app(app)


@app.context_processor
def inject_build_mode():
    return {
        "static_build": os.getenv("STATIC_BUILD") == "true",
        "experimental": os.getenv("EXPERIMENTAL", "1") != "0",
    }


# ── Experimental Blueprint ──────────────────────────────────────────────────
# Mounted unconditionally so routes are reachable during development.
# Set EXPERIMENTAL=0 to disable in production.
if os.getenv("EXPERIMENTAL", "1") != "0":
    from experimental import bp as experimental_bp
    app.register_blueprint(experimental_bp)
# ───────────────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    return render_template("earnings.html")


@app.route("/news")
def news_page():
    return render_template("news.html")


@app.route("/api/revenue")
def revenue():
    rows = request_connection().execute("""
        SELECT c.ticker, c.name, er.period, er.period_end_date, fm.value AS revenue
        FROM financial_metrics fm
        JOIN earnings_reports er ON fm.report_id = er.id
        JOIN companies c ON er.company_id = c.id
        WHERE fm.statement = 'income_statement' AND fm.metric_name = 'revenue'
        ORDER BY er.period_end_date, c.ticker
    """).fetchall()
    return jsonify(rows)


@app.route("/api/tickers")
def tickers():
    rows = request_connection().execute("SELECT ticker, name FROM companies ORDER BY ticker").fetchall()
    return jsonify(rows)


@app.route("/api/metrics/<ticker>")
def metrics(ticker):
    """{ticker, name, periods: [...], data: {statement: {metric: [value per period]}}}."""
    table = earnings.quarterly_table(request_connection(), ticker)
    if table is None:
        return jsonify({"error": "Ticker not found"}), 404
    return jsonify(table)


@app.route("/api/news")
def news_by_week():
    return jsonify(news.get_by_week(request_connection()))


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    # debug=True runs a reloader parent plus the serving child; print once, from the child.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        print(f" * Database: {DbSettings.from_env().redacted_url()}", flush=True)
    app.run(debug=True, host="0.0.0.0", port=port)
