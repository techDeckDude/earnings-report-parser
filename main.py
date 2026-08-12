from __future__ import annotations
import sys
import json
from pathlib import Path
from pydantic import ValidationError

from extractor import extract_report
from db import init_db, upsert_report, query_report


def fmt(value: float, prefix: str = "$") -> str:
    """Format a value in thousands to a readable millions/billions string."""
    billions = value / 1_000_000
    millions = value / 1_000
    if abs(billions) >= 1:
        return f"{prefix}{billions:.3f}B"
    return f"{prefix}{millions:.1f}M"


def print_summary(report) -> None:
    is_ = report.income_statement
    bs = report.balance_sheet
    cf = report.cash_flow

    print(f"\n{'='*60}")
    print(f"  {report.company_name} ({report.ticker})")
    print(f"  {report.filing_type} — {report.period} (ended {report.period_end_date})")
    print(f"  All figures in thousands USD unless noted")
    print(f"{'='*60}")

    print("\n[ Income Statement — Q2 2026 ]")
    print(f"  Revenue:                  {fmt(is_.revenue)}")
    print(f"  Cost of Revenue:          {fmt(is_.cost_of_revenue)}")
    print(f"  Gross Profit:             {fmt(is_.gross_profit)}  ({is_.gross_profit/is_.revenue*100:.1f}% margin)")
    print(f"  Operating Expenses:")
    print(f"    Sales & Marketing:      {fmt(is_.sales_and_marketing)}")
    print(f"    R&D:                    {fmt(is_.research_and_development)}")
    print(f"    G&A:                    {fmt(is_.general_and_administrative)}")
    print(f"  Income from Operations:   {fmt(is_.income_from_operations)}  ({is_.income_from_operations/is_.revenue*100:.1f}% margin)")
    print(f"  Net Income:               {fmt(is_.net_income)}")
    print(f"  EPS (basic / diluted):    ${is_.eps_basic:.2f} / ${is_.eps_diluted:.2f}")
    print(f"  Shares Outstanding:       {is_.shares_outstanding_basic/1_000_000:.2f}B (basic)")

    print("\n[ Balance Sheet — as of June 30, 2026 ]")
    print(f"  Cash & Equivalents:       {fmt(bs.cash_and_equivalents)}")
    print(f"  Marketable Securities:    {fmt(bs.marketable_securities)}")
    print(f"  Accounts Receivable:      {fmt(bs.accounts_receivable_net)}")
    print(f"  Total Assets:             {fmt(bs.total_assets)}")
    print(f"  Total Liabilities:        {fmt(bs.total_liabilities)}")
    print(f"  Total Equity:             {fmt(bs.total_equity)}")

    print("\n[ Cash Flow — Six Months Ended June 30, 2026 ]")
    print(f"  Operating Cash Flow:      {fmt(cf.net_cash_from_operations)}")
    print(f"  CapEx:                   ({fmt(cf.capex)})")
    print(f"  Free Cash Flow:           {fmt(cf.net_cash_from_operations - cf.capex)}")
    print(f"  Investing Cash Flow:     ({fmt(abs(cf.net_cash_from_investing))})")
    print(f"  Stock-Based Comp:         {fmt(cf.stock_based_compensation)}")
    print(f"{'='*60}\n")


def run(pdf_path: str, db_path: str = "earnings.db") -> None:
    print(f"[1/4] Extracting data from: {pdf_path}")
    try:
        report = extract_report(pdf_path)
    except Exception as e:
        print(f"ERROR during extraction: {e}", file=sys.stderr)
        sys.exit(1)
    print("      Extraction complete.")

    print("[2/4] Validating with Pydantic models...")
    try:
        # Re-parse to trigger all validators (already done in extract_report,
        # but explicit here for clarity)
        report.model_validate(report.model_dump())
    except ValidationError as e:
        print(f"ERROR: Validation failed:\n{e}", file=sys.stderr)
        sys.exit(1)
    print("      Validation passed.")

    print(f"[3/4] Saving to database: {db_path}")
    conn = init_db(db_path)
    report_id = upsert_report(conn, report)
    print(f"      Saved as report_id={report_id}.")

    print("[4/4] Summary:")
    print_summary(report)

    # Also dump full JSON for inspection
    out_path = Path(pdf_path).stem + "_extracted.json"
    Path(out_path).write_text(
        json.dumps(report.model_dump(mode="json"), indent=2)
    )
    print(f"Full JSON written to: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python main.py <path/to/10-Q.pdf> [earnings.db]")
        sys.exit(1)
    pdf = sys.argv[1]
    db = sys.argv[2] if len(sys.argv) > 2 else "earnings.db"
    run(pdf, db)
