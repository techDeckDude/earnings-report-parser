from __future__ import annotations
from flask import Flask, jsonify, render_template

from db import init_db, _execute

app = Flask(__name__)
_conn = None


def get_db():
    global _conn
    if _conn is None:
        _conn = init_db()
    return _conn


@app.route("/")
def index():
    return render_template("index.html")


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


if __name__ == "__main__":
    app.run(debug=True, port=5001)
