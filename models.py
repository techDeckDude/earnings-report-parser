from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from datetime import date


class IncomeStatement(BaseModel):
    # --- Required: universal across all supported companies ---
    revenue: float = Field(description="Total revenue in thousands USD")
    cost_of_revenue: float
    gross_profit: float
    research_and_development: float
    income_from_operations: float
    net_income: float
    eps_basic: float
    eps_diluted: float
    shares_outstanding_basic: float = Field(description="Weighted average shares, in thousands")
    shares_outstanding_diluted: float = Field(description="Weighted average shares, in thousands")

    # --- Optional: PLTR-specific (separate S&M and G&A lines) ---
    sales_and_marketing: Optional[float] = None
    general_and_administrative: Optional[float] = None
    total_operating_expenses: Optional[float] = None
    interest_income: Optional[float] = None
    other_income_expense: Optional[float] = None
    income_before_tax: Optional[float] = None
    provision_for_income_taxes: Optional[float] = None
    net_income_attributable_to_common: Optional[float] = None

    # --- Optional: MRVL-specific (combined SG&A, interest expense line) ---
    selling_general_and_administrative: Optional[float] = None
    interest_expense: Optional[float] = None
    income_tax_expense: Optional[float] = None

    @model_validator(mode="after")
    def check_gross_profit(self) -> IncomeStatement:
        expected = round(self.revenue - self.cost_of_revenue)
        actual = round(self.gross_profit)
        if abs(expected - actual) > 5:
            raise ValueError(
                f"gross_profit {actual} does not match revenue - cost_of_revenue = {expected}"
            )
        return self


class BalanceSheet(BaseModel):
    # --- Required: universal ---
    cash_and_equivalents: float
    accounts_receivable_net: float
    total_current_assets: float
    property_and_equipment_net: float
    total_assets: float
    accounts_payable_and_accrued: float
    total_current_liabilities: float
    total_liabilities: float
    total_equity: float

    # --- Optional: common but not universal ---
    prepaid_and_other_current: Optional[float] = None
    operating_lease_rou_assets: Optional[float] = None
    other_assets: Optional[float] = None

    # --- Optional: PLTR-specific ---
    marketable_securities: Optional[float] = None
    deferred_revenue_current: Optional[float] = None
    customer_deposits_current: Optional[float] = None
    deferred_revenue_noncurrent: Optional[float] = None
    operating_lease_liabilities_noncurrent: Optional[float] = None

    # --- Optional: MRVL-specific ---
    inventory: Optional[float] = None
    goodwill: Optional[float] = None
    intangible_assets: Optional[float] = None
    deferred_tax_assets: Optional[float] = None

    @model_validator(mode="after")
    def check_balance(self) -> BalanceSheet:
        expected = round(self.total_assets)
        actual = round(self.total_liabilities + self.total_equity)
        if abs(expected - actual) > 500:
            raise ValueError(
                f"Balance sheet does not balance: assets={expected}, liabilities+equity={actual}"
            )
        return self


class CashFlow(BaseModel):
    # --- Required: universal ---
    net_income: float
    net_cash_from_operations: float
    net_cash_from_investing: float
    net_cash_from_financing: float

    # --- Optional: common but not universal ---
    depreciation_and_amortization: Optional[float] = None
    stock_based_compensation: Optional[float] = None
    capex: Optional[float] = None

    # --- Optional: PLTR-specific ---
    purchases_of_marketable_securities: Optional[float] = None
    proceeds_from_marketable_securities: Optional[float] = None


class EarningsReport(BaseModel):
    schema_version: str = "1.0"
    company_name: str
    ticker: str
    period: str
    period_end_date: date
    filing_type: str
    units: str = "thousands"
    income_statement: IncomeStatement
    balance_sheet: BalanceSheet
    cash_flow: CashFlow
