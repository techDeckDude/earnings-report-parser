from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from datetime import date


class IncomeStatement(BaseModel):
    revenue: float = Field(description="Total revenue in thousands USD")
    cost_of_revenue: float
    gross_profit: float
    sales_and_marketing: float
    research_and_development: float
    general_and_administrative: float
    total_operating_expenses: float
    income_from_operations: float
    interest_income: float
    other_income_expense: float
    income_before_tax: float
    provision_for_income_taxes: float
    net_income: float
    net_income_attributable_to_common: float
    eps_basic: float
    eps_diluted: float
    shares_outstanding_basic: float = Field(description="In thousands")
    shares_outstanding_diluted: float = Field(description="In thousands")

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
    cash_and_equivalents: float
    marketable_securities: float
    accounts_receivable_net: float
    prepaid_and_other_current: float
    total_current_assets: float
    property_and_equipment_net: float
    operating_lease_rou_assets: float
    other_assets: float
    total_assets: float
    accounts_payable_and_accrued: float
    deferred_revenue_current: float
    customer_deposits_current: float
    total_current_liabilities: float
    deferred_revenue_noncurrent: float
    operating_lease_liabilities_noncurrent: float
    total_liabilities: float
    total_equity: float

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
    net_income: float
    depreciation_and_amortization: float
    stock_based_compensation: float
    net_cash_from_operations: float
    capex: float
    purchases_of_marketable_securities: float
    proceeds_from_marketable_securities: float
    net_cash_from_investing: float
    net_cash_from_financing: float


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
