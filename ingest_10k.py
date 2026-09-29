#!/usr/bin/env python3
"""
Ingest 10-K annual filings for a ticker and derive Q4 data.

For income statement and cash flow (flow metrics), Q4 is computed as:
    Q4 = Annual (10-K) - Q1 - Q2 - Q3   (values already in DB)

Balance sheet Q4 is the year-end 10-K snapshot taken directly.
EPS Q4 = Q4 net income / annual weighted average shares.

Usage:
    python ingest_10k.py AMD                  # all available fiscal years
    python ingest_10k.py AMD --since 2020-01-01
    python ingest_10k.py AMD --dry-run
"""
from __future__ import annotations

import argparse
from datetime import date
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db import init_db, upsert_report, _execute, _ph, _is_pg
from edgar import get_cik
from extractors.xbrl import XBRLExtractor
from models import EarningsReport, IncomeStatement, BalanceSheet, CashFlow


# Flow metrics: Q4 = Annual - (Q1 + Q2 + Q3)
_INCOME_FLOW_REQUIRED = {"revenue", "cost_of_revenue", "gross_profit",
                         "income_from_operations", "net_income"}
_CASHFLOW_FLOW_REQUIRED = {"net_cash_from_operations", "net_cash_from_investing",
                           "net_cash_from_financing"}
_INCOME_FLOW_OPTIONAL = {"research_and_development", "selling_general_and_administrative"}
_CASHFLOW_FLOW_OPTIONAL = {"capex", "stock_based_compensation", "depreciation_and_amortization"}


def _get_quarterly_sums(conn, ticker: str, fy: int) -> dict[tuple[str, str], dict]:
    """Return {(statement, metric_name): {"sum": float, "cnt": int}} for Q1+Q2+Q3."""
    ph = _ph(conn)
    rows = _execute(conn, f"""
        SELECT fm.statement, fm.metric_name, COUNT(*) AS cnt, SUM(fm.value) AS total
        FROM financial_metrics fm
        JOIN earnings_reports er ON er.id = fm.report_id
        JOIN companies c ON c.id = er.company_id
        WHERE c.ticker = {ph} AND er.period IN ({ph}, {ph}, {ph})
        GROUP BY fm.statement, fm.metric_name
    """, (ticker, f"Q1 {fy}", f"Q2 {fy}", f"Q3 {fy}")).fetchall()
    return {
        (r["statement"], r["metric_name"]): {"sum": r["total"], "cnt": r["cnt"]}
        for r in rows
    }


def _derive_q4(
    ticker: str,
    fy_end: str,
    fy_label: str,
    annual: dict[str, float],
    q_sums: dict[tuple[str, str], dict],
    entity_name: str,
) -> EarningsReport:
    """
    Build an EarningsReport for Q4 derived from 10-K annual values and DB quarterly sums.
    Raises ValueError if required fields are missing.
    """
    def flow(stmt: str, field: str) -> Optional[float]:
        """Q4 = Annual - sum(Q1+Q2+Q3). Returns None if any input is unavailable."""
        annual_val = annual.get(field)
        if annual_val is None:
            return None
        q_data = q_sums.get((stmt, field))
        if q_data is None or q_data["cnt"] < 3:
            return None
        return annual_val - q_data["sum"]

    def bs(field: str) -> Optional[float]:
        return annual.get(field)

    # Validate required flow metrics
    for field in _INCOME_FLOW_REQUIRED:
        if field not in annual:
            raise ValueError(f"Annual 10-K missing required income field: {field}")
        cnt = q_sums.get(("income_statement", field), {}).get("cnt", 0)
        if cnt < 3:
            raise ValueError(
                f"Cannot derive Q4 {field}: only {cnt}/3 quarters in DB for {fy_label}"
            )

    for field in _CASHFLOW_FLOW_REQUIRED:
        if field not in annual:
            raise ValueError(f"Annual 10-K missing required cash flow field: {field}")
        cnt = q_sums.get(("cash_flow", field), {}).get("cnt", 0)
        if cnt < 3:
            raise ValueError(
                f"Cannot derive Q4 {field}: only {cnt}/3 quarters in DB for {fy_label}"
            )

    # Validate required balance sheet fields
    for field in ("cash_and_equivalents", "accounts_receivable_net", "total_current_assets",
                  "property_and_equipment_net", "total_assets", "accounts_payable_and_accrued",
                  "total_current_liabilities", "total_liabilities", "total_equity"):
        if field not in annual:
            raise ValueError(f"Annual 10-K missing required balance sheet field: {field}")

    q4_ni = flow("income_statement", "net_income")

    # EPS: Q4 net income / annual weighted average shares
    shares_basic = annual.get("shares_outstanding_basic")
    shares_diluted = annual.get("shares_outstanding_diluted")

    if shares_basic and shares_basic != 0 and q4_ni is not None:
        q4_eps_basic = q4_ni / shares_basic
    elif "eps_basic" in annual:
        # Fallback: use annual EPS (less precise but better than failing)
        q4_eps_basic = annual["eps_basic"]
        shares_basic = shares_basic or annual.get("shares_outstanding_basic")
    else:
        raise ValueError(f"Cannot compute Q4 EPS basic for {fy_label}: no shares in 10-K")

    if shares_diluted and shares_diluted != 0 and q4_ni is not None:
        q4_eps_diluted = q4_ni / shares_diluted
    elif "eps_diluted" in annual:
        q4_eps_diluted = annual["eps_diluted"]
        shares_diluted = shares_diluted or annual.get("shares_outstanding_diluted")
    else:
        raise ValueError(f"Cannot compute Q4 EPS diluted for {fy_label}: no shares in 10-K")

    if shares_basic is None:
        raise ValueError(f"No shares_outstanding_basic for {fy_label}")
    if shares_diluted is None:
        raise ValueError(f"No shares_outstanding_diluted for {fy_label}")

    return EarningsReport(
        company_name=entity_name,
        ticker=ticker,
        period=fy_label,
        period_end_date=date.fromisoformat(fy_end),
        filing_type="10-K",
        units="thousands",
        extraction_source="edgar_xbrl_api_10k",
        income_statement=IncomeStatement(
            revenue=flow("income_statement", "revenue"),
            cost_of_revenue=flow("income_statement", "cost_of_revenue"),
            gross_profit=flow("income_statement", "gross_profit"),
            research_and_development=flow("income_statement", "research_and_development"),
            selling_general_and_administrative=flow("income_statement", "selling_general_and_administrative"),
            income_from_operations=flow("income_statement", "income_from_operations"),
            net_income=q4_ni,
            eps_basic=q4_eps_basic,
            eps_diluted=q4_eps_diluted,
            shares_outstanding_basic=shares_basic,
            shares_outstanding_diluted=shares_diluted,
        ),
        balance_sheet=BalanceSheet(
            cash_and_equivalents=bs("cash_and_equivalents"),
            accounts_receivable_net=bs("accounts_receivable_net"),
            total_current_assets=bs("total_current_assets"),
            property_and_equipment_net=bs("property_and_equipment_net"),
            total_assets=bs("total_assets"),
            accounts_payable_and_accrued=bs("accounts_payable_and_accrued"),
            total_current_liabilities=bs("total_current_liabilities"),
            total_liabilities=bs("total_liabilities"),
            total_equity=bs("total_equity"),
        ),
        cash_flow=CashFlow(
            net_income=q4_ni,
            net_cash_from_operations=flow("cash_flow", "net_cash_from_operations"),
            net_cash_from_investing=flow("cash_flow", "net_cash_from_investing"),
            net_cash_from_financing=flow("cash_flow", "net_cash_from_financing"),
            capex=flow("cash_flow", "capex"),
            stock_based_compensation=flow("cash_flow", "stock_based_compensation"),
            depreciation_and_amortization=flow("cash_flow", "depreciation_and_amortization"),
        ),
    )


def run(ticker: str, since_date: str | None = None, dry_run: bool = False) -> None:
    conn = init_db()

    print(f"Resolving CIK for {ticker}...")
    cik = get_cik(ticker, conn)
    print(f"  CIK: {cik}")

    extractor = XBRLExtractor()
    print(f"Fetching XBRL company facts...")
    facts = extractor.fetch_company_facts(cik)
    entity_name = facts.get("entityName", ticker)
    print(f"  Entity: {entity_name}")

    fiscal_years = extractor.get_fiscal_years(facts)
    if since_date:
        fiscal_years = [(e, l, fy) for e, l, fy in fiscal_years if e >= since_date]

    if not fiscal_years:
        print(f"  No 10-K fiscal years found (since_date={since_date})")
        return

    print(f"  Found {len(fiscal_years)} 10-K fiscal year(s)")

    success, failed = 0, 0
    for fy_end, fy_label, fy_number in fiscal_years:
        try:
            annual = extractor.extract_annual(ticker, fy_end, facts)
            q_sums = _get_quarterly_sums(conn, ticker.upper(), fy_number)
            report = _derive_q4(ticker.upper(), fy_end, fy_label, annual, q_sums, entity_name)
            if dry_run:
                print(f"  [dry-run] {fy_label} ({fy_end}) — "
                      f"revenue={report.income_statement.revenue:,.0f}K  "
                      f"net_income={report.income_statement.net_income:,.0f}K")
            else:
                upsert_report(conn, report)
                print(f"  ✓ {fy_label} ({fy_end}) — "
                      f"revenue={report.income_statement.revenue:,.0f}K  "
                      f"net_income={report.income_statement.net_income:,.0f}K")
            success += 1
        except Exception as e:
            print(f"  ✗ {fy_label} ({fy_end}): {e}")
            failed += 1

    action = "Would derive" if dry_run else "Derived"
    print(f"\n{action} {success}/{len(fiscal_years)} Q4 periods for {ticker}"
          + (f" ({failed} failed)" if failed else ""))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Derive Q4 data from 10-K annual filings")
    p.add_argument("ticker", help="Ticker symbol, e.g. AMD")
    p.add_argument("--since", metavar="YYYY-MM-DD",
                   help="Only process fiscal years ending after this date")
    p.add_argument("--dry-run", action="store_true",
                   help="Extract and validate without writing to DB")
    args = p.parse_args()
    run(args.ticker, since_date=args.since, dry_run=args.dry_run)
