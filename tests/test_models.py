from __future__ import annotations
import pytest
from datetime import date
from pydantic import ValidationError

from models import EarningsReport, IncomeStatement, BalanceSheet, CashFlow


def _make_income(**overrides) -> dict:
    base = dict(
        revenue=1_000_000, cost_of_revenue=200_000, gross_profit=800_000,
        research_and_development=150_000, income_from_operations=100_000,
        net_income=80_000, eps_basic=0.03, eps_diluted=0.03,
        shares_outstanding_basic=2_100_000, shares_outstanding_diluted=2_200_000,
    )
    return {**base, **overrides}


def _make_balance(**overrides) -> dict:
    base = dict(
        cash_and_equivalents=500_000, accounts_receivable_net=300_000,
        total_current_assets=900_000, property_and_equipment_net=100_000,
        total_assets=1_100_000, accounts_payable_and_accrued=50_000,
        total_current_liabilities=150_000, total_liabilities=200_000,
        total_equity=900_000,
    )
    return {**base, **overrides}


def _make_cash(**overrides) -> dict:
    base = dict(
        net_income=80_000, net_cash_from_operations=120_000,
        net_cash_from_investing=-30_000, net_cash_from_financing=-10_000,
    )
    return {**base, **overrides}


def _make_report(**income_overrides) -> EarningsReport:
    return EarningsReport(
        company_name="Test Corp", ticker="TEST",
        period="Q1 2026", period_end_date=date(2026, 3, 31),
        filing_type="10-Q",
        income_statement=IncomeStatement(**_make_income(**income_overrides)),
        balance_sheet=BalanceSheet(**_make_balance()),
        cash_flow=CashFlow(**_make_cash()),
    )


# ── IncomeStatement validator ─────────────────────────────────────────────────

def test_gross_profit_valid():
    stmt = IncomeStatement(**_make_income())
    assert stmt.gross_profit == 800_000


def test_gross_profit_rounding_tolerance():
    # $3k gap — within the $5k tolerance
    IncomeStatement(**_make_income(gross_profit=800_003))


def test_gross_profit_invalid():
    with pytest.raises(ValidationError, match="gross_profit"):
        IncomeStatement(**_make_income(gross_profit=750_000))


# ── BalanceSheet validator ────────────────────────────────────────────────────

def test_balance_sheet_balances():
    bs = BalanceSheet(**_make_balance())
    assert bs.total_assets == bs.total_liabilities + bs.total_equity


def test_balance_sheet_near_tolerance():
    # $400k gap — within the $500k tolerance
    BalanceSheet(**_make_balance(total_equity=900_400))


def test_balance_sheet_doesnt_balance():
    with pytest.raises(ValidationError, match="[Bb]alance"):
        BalanceSheet(**_make_balance(total_equity=200_000))


# ── EarningsReport construction ───────────────────────────────────────────────

def test_full_report_construction():
    report = _make_report()
    assert report.ticker == "TEST"
    assert report.schema_version == "1.0"


def test_schema_version_default():
    report = _make_report()
    assert report.schema_version == "1.0"


def test_optional_fields_default_none():
    report = _make_report()
    assert report.income_statement.sales_and_marketing is None
    assert report.income_statement.selling_general_and_administrative is None
    assert report.balance_sheet.inventory is None
    assert report.cash_flow.capex is None


# ── Real fixture contracts ────────────────────────────────────────────────────

def test_full_pltr_report_valid(sample_pltr_report):
    assert sample_pltr_report.ticker == "PLTR"
    assert sample_pltr_report.income_statement.revenue > 0
    assert sample_pltr_report.balance_sheet.total_assets > 0


def test_full_mrvl_report_valid(sample_mrvl_report):
    assert sample_mrvl_report.ticker == "MRVL"
    assert sample_mrvl_report.income_statement.revenue > 0
    assert sample_mrvl_report.balance_sheet.total_assets > 0
