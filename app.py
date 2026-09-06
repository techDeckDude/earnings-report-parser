from __future__ import annotations
import os
from flask import Flask, jsonify, render_template, request

from db import init_db, _execute

app = Flask(__name__)
_conn = None


@app.context_processor
def inject_build_mode():
    return {"static_build": os.getenv("STATIC_BUILD") == "true"}


def get_db():
    global _conn
    if _conn is None:
        _conn = init_db()
    return _conn


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/stock")
def stock():
    return render_template("stock.html")


@app.route("/api/revenue")
def revenue():
    conn = get_db()
    rows = _execute(conn, """
        SELECT c.ticker, c.name, er.period, er.period_end_date, fm.value AS revenue
        FROM financial_metrics fm
        JOIN earnings_reports er ON fm.report_id = er.id
        JOIN companies c ON er.company_id = c.id
        WHERE fm.statement = 'income_statement' AND fm.metric_name = 'revenue'
        ORDER BY er.period_end_date, c.ticker
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/tickers")
def tickers():
    conn = get_db()
    rows = _execute(conn, "SELECT ticker, name FROM companies ORDER BY ticker").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/metrics/<ticker>")
def metrics(ticker):
    conn = get_db()
    periods = _execute(conn, """
        SELECT er.id, er.period, er.period_end_date
        FROM earnings_reports er
        JOIN companies c ON er.company_id = c.id
        WHERE c.ticker = ?
        ORDER BY er.period_end_date
    """, (ticker.upper(),)).fetchall()

    if not periods:
        return jsonify({"error": "Ticker not found"}), 404

    report_ids = [p["id"] for p in periods]
    placeholders = ",".join("?" * len(report_ids))
    rows = _execute(conn, f"""
        SELECT report_id, statement, metric_name, value
        FROM financial_metrics
        WHERE report_id IN ({placeholders})
    """, report_ids).fetchall()

    # Pivot: {statement: {metric_name: [value_per_period]}}
    pivot: dict[str, dict[str, dict]] = {}
    for r in rows:
        s, m = r["statement"], r["metric_name"]
        if s not in pivot:
            pivot[s] = {}
        if m not in pivot[s]:
            pivot[s][m] = {}
        pivot[s][m][r["report_id"]] = r["value"]

    company = _execute(conn, "SELECT name FROM companies WHERE ticker = ?",
                       (ticker.upper(),)).fetchone()

    return jsonify({
        "ticker": ticker.upper(),
        "name": company["name"] if company else ticker.upper(),
        "periods": [dict(p) for p in periods],
        "data": {
            s: {
                m: [pivot[s][m].get(p["id"]) for p in periods]
                for m in pivot[s]
            }
            for s in pivot
        },
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
