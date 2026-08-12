from __future__ import annotations
import sqlite3
from flask import Flask, jsonify, render_template

app = Flask(__name__)
DB_PATH = "earnings.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/revenue")
def revenue():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT c.ticker, c.name, er.period, er.period_end_date, fm.value AS revenue
        FROM financial_metrics fm
        JOIN earnings_reports er ON fm.report_id = er.id
        JOIN companies c ON er.company_id = c.id
        WHERE fm.statement = 'income_statement' AND fm.metric_name = 'revenue'
        ORDER BY er.period_end_date, c.ticker
        """
    ).fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(debug=True, port=5001)
