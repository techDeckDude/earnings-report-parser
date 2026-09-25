"""
Tier 1 EDGAR XBRL extractor.

Fetches structured financial data from the EDGAR Company Facts API
(no file download required) and maps US-GAAP concepts to EarningsReport.

Usage:
    from extractors.xbrl import XBRLExtractor
    extractor = XBRLExtractor()
    facts = extractor.fetch_company_facts("0000002488")
    report = extractor.extract("AMD", "0000002488", "2026-06-27", facts)
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from typing import Optional

from models import (
    EarningsReport,
    IncomeStatement,
    BalanceSheet,
    CashFlow,
)

_USER_AGENT = "earnings-report-parser/1.0 justinbullock025@gmail.com"
_RATE_INTERVAL = 1.0 / 10
_last_request: float = 0.0


def _get(url: str) -> dict:
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < _RATE_INTERVAL:
        time.sleep(_RATE_INTERVAL - elapsed)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read())
    _last_request = time.monotonic()
    return data


# ── Concept map ────────────────────────────────────────────────────────────────
# (field_name): ([alias_list_in_priority_order], unit)
# unit: "USD" → converted to thousands; "USD/shares" → raw; "shares" → converted to thousands

_CONCEPT_MAP: dict[str, tuple[list[str], str]] = {
    # Income statement
    "revenue": (
        ["RevenueFromContractWithCustomerExcludingAssessedTax",
         "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax",
         "SalesRevenueNet"],
        "USD",
    ),
    "cost_of_revenue": (
        ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
        "USD",
    ),
    "gross_profit": (
        ["GrossProfit"],
        "USD",
    ),
    "research_and_development": (
        ["ResearchAndDevelopmentExpense",
         "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"],
        "USD",
    ),
    "selling_general_and_administrative": (
        ["SellingGeneralAndAdministrativeExpense",
         "GeneralAndAdministrativeExpense"],
        "USD",
    ),
    "income_from_operations": (
        ["OperatingIncomeLoss"],
        "USD",
    ),
    "net_income": (
        ["NetIncomeLoss",
         "NetIncomeLossAvailableToCommonStockholdersBasic",
         "ProfitLoss"],
        "USD",
    ),
    "eps_basic": (
        ["EarningsPerShareBasic"],
        "USD/shares",
    ),
    "eps_diluted": (
        ["EarningsPerShareDiluted"],
        "USD/shares",
    ),
    "shares_outstanding_basic": (
        ["WeightedAverageNumberOfSharesOutstandingBasic",
         "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"],
        "shares",
    ),
    "shares_outstanding_diluted": (
        ["WeightedAverageNumberOfDilutedSharesOutstanding",
         "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"],
        "shares",
    ),
    # Balance sheet
    "cash_and_equivalents": (
        ["CashAndCashEquivalentsAtCarryingValue",
         "CashCashEquivalentsAndShortTermInvestments"],
        "USD",
    ),
    "accounts_receivable_net": (
        ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"],
        "USD",
    ),
    "total_current_assets": (
        ["AssetsCurrent"],
        "USD",
    ),
    "property_and_equipment_net": (
        ["PropertyPlantAndEquipmentNet"],
        "USD",
    ),
    "total_assets": (
        ["Assets"],
        "USD",
    ),
    "accounts_payable_and_accrued": (
        ["AccountsPayableAndAccruedLiabilitiesCurrent",
         "AccountsPayableCurrent",
         "AccruedLiabilitiesCurrent"],
        "USD",
    ),
    "total_current_liabilities": (
        ["LiabilitiesCurrent"],
        "USD",
    ),
    "total_liabilities": (
        ["Liabilities"],
        "USD",
    ),
    "total_equity": (
        ["StockholdersEquity",
         "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
        "USD",
    ),
    # Cash flow
    "net_cash_from_operations": (
        ["NetCashProvidedByUsedInOperatingActivities"],
        "USD",
    ),
    "net_cash_from_investing": (
        ["NetCashProvidedByUsedInInvestingActivities"],
        "USD",
    ),
    "net_cash_from_financing": (
        ["NetCashProvidedByUsedInFinancingActivities"],
        "USD",
    ),
    "capex": (
        ["PaymentsToAcquirePropertyPlantAndEquipment",
         "PaymentsToAcquireProductiveAssets"],
        "USD",
    ),
    "stock_based_compensation": (
        ["ShareBasedCompensation",
         "AllocatedShareBasedCompensationExpense"],
        "USD",
    ),
    "depreciation_and_amortization": (
        ["DepreciationDepletionAndAmortization",
         "DepreciationAndAmortization"],
        "USD",
    ),
}


def _pick_entry(entries: list[dict], period_end: str) -> Optional[dict]:
    """
    Return the quarterly entry for period_end from a list of XBRL entries.

    Entries for a 10-Q period_end often include both a YTD slice (no frame,
    longer duration) and the single-quarter slice (frame = CY{year}Q{n},
    ~90 day duration). We always want the quarterly slice.
    """
    candidates = [
        e for e in entries
        if e.get("end") == period_end and e.get("form") == "10-Q"
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Prefer entry with a CY frame — that's the quarterly slice
    framed = [e for e in candidates if e.get("frame", "").startswith("CY")]
    if framed:
        return framed[0]
    # Fallback: shortest duration
    def _days(e: dict) -> int:
        if "start" not in e:
            return 9999
        return (date.fromisoformat(e["end"]) - date.fromisoformat(e["start"])).days
    return min(candidates, key=_days)


def _period_label(gaap: dict, period_end: str) -> str:
    """Derive 'Q2 2026' from the fp/fy fields on any matching XBRL entry."""
    for concept_data in gaap.values():
        for unit_entries in concept_data["units"].values():
            for e in unit_entries:
                if e.get("end") == period_end and e.get("form") == "10-Q":
                    fp = e.get("fp", "")
                    fy = e.get("fy")
                    if fp.startswith("Q") and fy:
                        return f"{fp} {fy}"
    # Fallback: derive from the date
    d = date.fromisoformat(period_end)
    q = (d.month - 1) // 3 + 1
    return f"Q{q} {d.year}"


class XBRLExtractor:
    """
    Extracts EarningsReport data from the EDGAR Company Facts API.
    Not a file-path extractor — call fetch_company_facts() once per company,
    then extract() for each period.
    """

    def fetch_company_facts(self, cik: str) -> dict:
        """Fetch the full XBRL company facts payload for a CIK."""
        return _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")

    def extract(
        self,
        ticker: str,
        cik: str,
        period_end: str,
        company_facts: dict,
    ) -> EarningsReport:
        """
        Map one quarter's XBRL data to an EarningsReport.

        Raises ValueError if any required field cannot be populated.
        """
        entity_name = company_facts.get("entityName", ticker)
        gaap = company_facts["facts"].get("us-gaap", {})

        # ── Extract all mapped fields ────────────────────────────────────────
        raw: dict[str, float] = {}
        missing: list[str] = []

        for field_name, (concepts, unit) in _CONCEPT_MAP.items():
            found = None
            for concept in concepts:
                if concept not in gaap:
                    continue
                entries = gaap[concept]["units"].get(unit, [])
                entry = _pick_entry(entries, period_end)
                if entry is not None:
                    val = entry["val"]
                    if unit == "USD":
                        val = val / 1000          # raw USD → thousands
                    elif unit == "shares":
                        val = val / 1000          # raw shares → thousands
                    # USD/shares (EPS) stays as-is
                    found = val
                    break
            if found is not None:
                raw[field_name] = found
            else:
                missing.append(field_name)

        # ── Compute total_liabilities if EDGAR doesn't tag it ────────────────
        if "total_liabilities" in missing and "total_assets" in raw and "total_equity" in raw:
            raw["total_liabilities"] = raw["total_assets"] - raw["total_equity"]
            missing.remove("total_liabilities")

        # ── Validate required fields are present ─────────────────────────────
        required = {
            "income_statement": ["revenue", "cost_of_revenue", "gross_profit",
                                  "income_from_operations", "net_income",
                                  "eps_basic", "eps_diluted",
                                  "shares_outstanding_basic", "shares_outstanding_diluted"],
            "balance_sheet":    ["cash_and_equivalents", "accounts_receivable_net",
                                  "total_current_assets", "property_and_equipment_net",
                                  "total_assets", "accounts_payable_and_accrued",
                                  "total_current_liabilities", "total_liabilities",
                                  "total_equity"],
            "cash_flow":        ["net_cash_from_operations", "net_cash_from_investing",
                                  "net_cash_from_financing"],
        }
        still_missing = [f for grp in required.values() for f in grp if f not in raw]
        if still_missing:
            raise ValueError(
                f"{ticker} {period_end}: required fields missing from EDGAR XBRL: "
                + ", ".join(still_missing)
            )

        # ── Assemble EarningsReport ───────────────────────────────────────────
        def g(key: str) -> Optional[float]:
            return raw.get(key)

        return EarningsReport(
            company_name=entity_name,
            ticker=ticker,
            period=_period_label(gaap, period_end),
            period_end_date=date.fromisoformat(period_end),
            filing_type="10-Q",
            units="thousands",
            extraction_source="edgar_xbrl_api",
            income_statement=IncomeStatement(
                revenue=raw["revenue"],
                cost_of_revenue=raw["cost_of_revenue"],
                gross_profit=raw["gross_profit"],
                research_and_development=raw["research_and_development"],
                selling_general_and_administrative=g("selling_general_and_administrative"),
                income_from_operations=raw["income_from_operations"],
                net_income=raw["net_income"],
                eps_basic=raw["eps_basic"],
                eps_diluted=raw["eps_diluted"],
                shares_outstanding_basic=raw["shares_outstanding_basic"],
                shares_outstanding_diluted=raw["shares_outstanding_diluted"],
            ),
            balance_sheet=BalanceSheet(
                cash_and_equivalents=raw["cash_and_equivalents"],
                accounts_receivable_net=raw["accounts_receivable_net"],
                total_current_assets=raw["total_current_assets"],
                property_and_equipment_net=raw["property_and_equipment_net"],
                total_assets=raw["total_assets"],
                accounts_payable_and_accrued=raw["accounts_payable_and_accrued"],
                total_current_liabilities=raw["total_current_liabilities"],
                total_liabilities=raw["total_liabilities"],
                total_equity=raw["total_equity"],
            ),
            cash_flow=CashFlow(
                net_income=raw["net_income"],
                net_cash_from_operations=raw["net_cash_from_operations"],
                net_cash_from_investing=raw["net_cash_from_investing"],
                net_cash_from_financing=raw["net_cash_from_financing"],
                capex=g("capex"),
                stock_based_compensation=g("stock_based_compensation"),
                depreciation_and_amortization=g("depreciation_and_amortization"),
            ),
        )
