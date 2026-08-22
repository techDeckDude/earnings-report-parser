from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from pydantic import ValidationError

from extractors import get_extractor
from db import init_db, upsert_report
from models import EarningsReport


def fmt(value: float, prefix: str = "$") -> str:
    billions = value / 1_000_000
    millions = value / 1_000
    if abs(billions) >= 1:
        return f"{prefix}{billions:.3f}B"
    return f"{prefix}{millions:.1f}M"


def print_summary(report: EarningsReport) -> None:
    is_ = report.income_statement
    bs = report.balance_sheet
    cf = report.cash_flow

    print(f"\n{'='*60}")
    print(f"  {report.company_name} ({report.ticker})")
    print(f"  {report.filing_type} — {report.period} (ended {report.period_end_date})")
    print(f"  All figures in thousands USD unless noted")
    print(f"{'='*60}")

    print(f"\n[ Income Statement — {report.period} ]")
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

    print(f"\n[ Balance Sheet — as of {report.period_end_date} ]")
    print(f"  Cash & Equivalents:       {fmt(bs.cash_and_equivalents)}")
    print(f"  Marketable Securities:    {fmt(bs.marketable_securities)}")
    print(f"  Accounts Receivable:      {fmt(bs.accounts_receivable_net)}")
    print(f"  Total Assets:             {fmt(bs.total_assets)}")
    print(f"  Total Liabilities:        {fmt(bs.total_liabilities)}")
    print(f"  Total Equity:             {fmt(bs.total_equity)}")

    print(f"\n[ Cash Flow — period ending {report.period_end_date} ]")
    print(f"  Operating Cash Flow:      {fmt(cf.net_cash_from_operations)}")
    print(f"  CapEx:                   ({fmt(cf.capex)})")
    print(f"  Free Cash Flow:           {fmt(cf.net_cash_from_operations - cf.capex)}")
    print(f"  Investing Cash Flow:     ({fmt(abs(cf.net_cash_from_investing))})")
    print(f"  Stock-Based Comp:         {fmt(cf.stock_based_compensation)}")
    print(f"{'='*60}\n")


def _s3_key(report: EarningsReport) -> str:
    """Convert period string to S3 key. 'Q2 2026' → 'PLTR/10-Q/FY2026Q2.json'"""
    q, year = report.period.split()
    return f"{report.ticker}/{report.filing_type}/FY{year}{q}.json"


def upload_contract(report: EarningsReport, bucket: str) -> str:
    """Upload the normalized contract JSON to S3. Returns the s3:// URI."""
    import boto3
    key = _s3_key(report)
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(report.model_dump(mode="json"), indent=2),
        ContentType="application/json",
    )
    return f"s3://{bucket}/{key}"


def run(pdf_path: str, db_path: str = "earnings.db") -> None:
    print(f"[1/4] Extracting data from: {pdf_path}")
    try:
        report = get_extractor(pdf_path).extract(pdf_path)
    except Exception as e:
        print(f"ERROR during extraction: {e}", file=sys.stderr)
        sys.exit(1)
    print("      Extraction complete.")

    print("[2/4] Validating with Pydantic models...")
    try:
        report.model_validate(report.model_dump())
    except ValidationError as e:
        print(f"ERROR: Validation failed:\n{e}", file=sys.stderr)
        sys.exit(1)
    print("      Validation passed.")

    # Upload contract to S3 if bucket is configured
    bucket = os.environ.get("S3_BUCKET")
    if bucket:
        print(f"[2b]  Uploading contract to S3 bucket: {bucket}")
        try:
            s3_uri = upload_contract(report, bucket)
            print(f"      Uploaded → {s3_uri}")
        except Exception as e:
            print(f"      WARNING: S3 upload failed ({e}). Continuing with DB write.")

    print(f"[3/4] Saving to database...")
    conn = init_db(db_path)
    report_id = upsert_report(conn, report)
    print(f"      Saved as report_id={report_id}.")

    print("[4/4] Summary:")
    print_summary(report)

    out_path = Path(pdf_path).stem + "_extracted.json"
    Path(out_path).write_text(json.dumps(report.model_dump(mode="json"), indent=2))
    print(f"Full JSON written to: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <path/to/10-Q.pdf> [earnings.db]")
        sys.exit(1)
    pdf = sys.argv[1]
    db = sys.argv[2] if len(sys.argv) > 2 else "earnings.db"
    run(pdf, db)
