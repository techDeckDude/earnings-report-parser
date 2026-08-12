from __future__ import annotations
import re
import pdfplumber
from datetime import date
from models import BalanceSheet, CashFlow, EarningsReport, IncomeStatement


def _parse_num(text: str) -> float:
    """Strip $, commas, whitespace and cast to float. Handles negatives in parens."""
    text = text.strip().replace("$", "").replace(",", "").replace(" ", "")
    if text.startswith("(") and text.endswith(")"):
        return -float(text[1:-1])
    return float(text)


def _find(pattern: str, text: str, group: int = 1) -> float:
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not m:
        raise ValueError(f"Pattern not found: {pattern!r}")
    return _parse_num(m.group(group))


def _extract_income_statement(text: str) -> IncomeStatement:
    return IncomeStatement(
        revenue=_find(r"Revenue\s+\$\s*([\d,]+)", text),
        cost_of_revenue=_find(r"Cost of revenue\s+([\d,]+)", text),
        gross_profit=_find(r"Gross profit\s+([\d,]+)", text),
        sales_and_marketing=_find(r"Sales and marketing\s+([\d,]+)", text),
        research_and_development=_find(r"Research and development\s+([\d,]+)", text),
        general_and_administrative=_find(r"General and administrative\s+([\d,]+)", text),
        total_operating_expenses=_find(r"Total operating expenses\s+([\d,]+)", text),
        income_from_operations=_find(r"Income from operations\s+([\d,]+)", text),
        interest_income=_find(r"Interest income\s+([\d,]+)", text),
        other_income_expense=_find(
            r"Other income \(expense\), net\s+([\d,]+)", text
        ),
        income_before_tax=_find(
            r"Income before provision for income taxes\s+([\d,]+)", text
        ),
        provision_for_income_taxes=_find(r"Provision for income taxes\s+([\d,]+)", text),
        net_income=_find(r"Net income\s+([\d,]+)", text),
        net_income_attributable_to_common=_find(
            r"Net income attributable to common stockholders\s+\$\s*([\d,]+)", text
        ),
        eps_basic=_find(
            r"Earnings per share attributable to common stockholders, basic\s+\$\s*([\d.]+)",
            text,
        ),
        eps_diluted=_find(
            r"Earnings per share attributable to common stockholders, diluted\s+\$\s*([\d.]+)",
            text,
        ),
        shares_outstanding_basic=_find(
            r"basic\s+(2,\d{3},\d{3})\s+2,\d{3},\d{3}\s+2,\d{3},\d{3}", text
        ),
        shares_outstanding_diluted=_find(
            r"diluted\s+(2,\d{3},\d{3})\s+2,\d{3},\d{3}\s+2,\d{3},\d{3}", text
        ),
    )


def _extract_balance_sheet(text: str) -> BalanceSheet:
    return BalanceSheet(
        cash_and_equivalents=_find(r"Cash and cash equivalents\s+\$\s*([\d,]+)", text),
        marketable_securities=_find(r"Marketable securities\s+([\d,]+)", text),
        accounts_receivable_net=_find(r"Accounts receivable, net\s+([\d,]+)", text),
        prepaid_and_other_current=_find(
            r"Prepaid expenses and other current assets\s+([\d,]+)", text
        ),
        total_current_assets=_find(r"Total current assets\s+([\d,]+)", text),
        property_and_equipment_net=_find(
            r"Property and equipment, net\s+([\d,]+)", text
        ),
        operating_lease_rou_assets=_find(
            r"Operating lease right-of-use assets\s+([\d,]+)", text
        ),
        other_assets=_find(r"Other assets\s+([\d,]+)", text),
        total_assets=_find(r"Total assets\s+\$\s*([\d,]+)", text),
        accounts_payable_and_accrued=_find(
            r"Accounts payable, accrued liabilities, and other\s+\$\s*([\d,]+)", text
        ),
        deferred_revenue_current=_find(r"Deferred revenue\s+([\d,]+)", text),
        customer_deposits_current=_find(r"Customer deposits\s+([\d,]+)", text),
        total_current_liabilities=_find(r"Total current liabilities\s+([\d,]+)", text),
        deferred_revenue_noncurrent=_find(r"Deferred revenue, noncurrent\s+([\d,]+)", text),
        operating_lease_liabilities_noncurrent=_find(
            r"Operating lease liabilities, noncurrent\s+([\d,]+)", text
        ),
        total_liabilities=_find(r"Total liabilities\s+([\d,]+)", text),
        total_equity=_find(r"Total equity\s+([\d,]+)", text),
    )


def _extract_cash_flow(text: str) -> CashFlow:
    return CashFlow(
        net_income=_find(r"Net income\s+\$\s*([\d,]+)", text),
        depreciation_and_amortization=_find(
            r"Depreciation and amortization\s+([\d,]+)", text
        ),
        stock_based_compensation=_find(r"Stock-based compensation\s+([\d,]+)", text),
        net_cash_from_operations=_find(
            r"Net cash provided by operating activities\s+([\d,]+)", text
        ),
        capex=_find(r"Purchases of property and equipment\s+\(?([\d,]+)\)?", text),
        purchases_of_marketable_securities=_find(
            r"Purchases of marketable securities\s+\(?([\d,]+)\)?", text
        ),
        proceeds_from_marketable_securities=_find(
            r"Proceeds from sales and redemption of marketable securities\s+([\d,]+)",
            text,
        ),
        net_cash_from_investing=_find(
            r"Net cash used in investing activities\s+\(?([\d,]+)\)?", text
        ),
        net_cash_from_financing=_find(
            r"Net cash (?:provided by \(used in\)|provided by|used in) financing activities\s+(\([\d,]+\)|[\d,]+)",
            text,
        ),
    )


def _extract_metadata(full_text: str) -> tuple[str, str, date]:
    """Return (company_name, period, period_end_date)."""
    name_m = re.search(r"(Palantir Technologies Inc\.)", full_text)
    company_name = name_m.group(1) if name_m else "Unknown"

    period_m = re.search(
        r"quarterly period ended ([A-Z][a-z]+ \d{1,2}, \d{4})", full_text, re.IGNORECASE
    )
    if period_m:
        from datetime import datetime
        end_date = datetime.strptime(period_m.group(1), "%B %d, %Y").date()
        quarter = f"Q{(end_date.month - 1) // 3 + 1} {end_date.year}"
    else:
        end_date = date(2026, 6, 30)
        quarter = "Q2 2026"

    return company_name, quarter, end_date


def extract_report(pdf_path: str) -> EarningsReport:
    with pdfplumber.open(pdf_path) as pdf:
        # Pages 3-4: balance sheet + income statement (0-indexed: 2, 3)
        # Pages 8-9: cash flow (0-indexed: 7, 8)
        cover_text = pdf.pages[0].extract_text() or ""
        bs_text = pdf.pages[2].extract_text() or ""
        is_text = pdf.pages[3].extract_text() or ""
        cf_text = "\n".join(
            p.extract_text() or "" for p in pdf.pages[7:9]
        )

    company_name, period, period_end_date = _extract_metadata(cover_text)

    return EarningsReport(
        company_name=company_name,
        ticker="PLTR",
        period=period,
        period_end_date=period_end_date,
        filing_type="10-Q",
        income_statement=_extract_income_statement(is_text),
        balance_sheet=_extract_balance_sheet(bs_text),
        cash_flow=_extract_cash_flow(cf_text),
    )
