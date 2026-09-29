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
         "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
         "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost"],
        "USD",
    ),
    "selling_general_and_administrative": (
        ["SellingGeneralAndAdministrativeExpense",
         "GeneralAndAdministrativeExpense"],
        "USD",
    ),
    "income_from_operations": (
        ["OperatingIncomeLoss",
         "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
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
        ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
         "AccountsAndOtherReceivablesNetCurrent"],
        "USD",
    ),
    "total_current_assets": (
        ["AssetsCurrent"],
        "USD",
    ),
    "property_and_equipment_net": (
        ["PropertyPlantAndEquipmentNet",
         "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization"],
        "USD",
    ),
    "total_assets": (
        ["Assets"],
        "USD",
    ),
    "accounts_payable_and_accrued": (
        ["AccountsPayableAndAccruedLiabilitiesCurrent",
         "AccountsPayableAndOtherAccruedLiabilitiesCurrent",
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
        ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
         "StockholdersEquity"],
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


def _pick_annual_entry(entries: list[dict], period_end: str) -> Optional[dict]:
    """Return the 10-K annual entry for a given fiscal year end date."""
    candidates = [
        e for e in entries
        if e.get("end") == period_end and e.get("form") == "10-K"
    ]
    if not candidates:
        return None
    # Prefer fp=FY (duration entry) over instant balance-sheet entries where both exist
    fy_tagged = [e for e in candidates if e.get("fp") == "FY"]
    return fy_tagged[0] if fy_tagged else candidates[0]


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

    def get_fiscal_years(self, company_facts: dict) -> list[tuple[str, str, int]]:
        """
        Return sorted list of (fy_end_date, period_label, fy_number) for all 10-K filings.
        Example: [("2022-01-30", "Q4 2022", 2022), ...]

        Only includes entries whose duration is >= 340 days (full-year, not quarterly
        comparatives that EDGAR sometimes tags with form=10-K and fp=FY).
        """
        gaap = company_facts["facts"].get("us-gaap", {})
        # Keyed by fy_label; keeps the LATEST fy_end for each label.
        # EDGAR sometimes includes comparative-year data from a single 10-K filing,
        # all tagged with the same fy — the most recent end date is the actual year end.
        seen: dict[str, tuple[str, str, int]] = {}

        # Scan ALL revenue concepts to handle companies that changed their GAAP tag
        # across years (e.g. NVDA used ContractWithCustomer through FY2022, Revenues after).
        for concept in _CONCEPT_MAP["revenue"][0]:
            if concept not in gaap:
                continue
            for e in gaap[concept]["units"].get("USD", []):
                if e.get("form") != "10-K" or e.get("fp") != "FY":
                    continue
                # Filter out short comparative periods (< 340 days)
                start = e.get("start")
                if start:
                    days = (date.fromisoformat(e["end"]) - date.fromisoformat(start)).days
                    if days < 340:
                        continue
                fy_end = e["end"]
                fy = e.get("fy")
                if not fy:
                    continue
                fy_label = f"Q4 {fy}"
                existing = seen.get(fy_label)
                if existing is None or fy_end > existing[0]:
                    seen[fy_label] = (fy_end, fy_label, int(fy))

        return sorted(seen.values())

    def extract_annual(self, ticker: str, fy_end: str, company_facts: dict) -> dict[str, float]:
        """
        Extract annual 10-K values for all concepts at fiscal year end fy_end.
        Returns {field_name: value} with same units as extract(): USD→thousands,
        shares→thousands, USD/shares (EPS) as-is.
        """
        gaap = company_facts["facts"].get("us-gaap", {})
        raw: dict[str, float] = {}

        for field_name, (concepts, unit) in _CONCEPT_MAP.items():
            for concept in concepts:
                if concept not in gaap:
                    continue
                entries = gaap[concept]["units"].get(unit, [])
                entry = _pick_annual_entry(entries, fy_end)
                if entry is not None:
                    val = entry["val"]
                    if unit == "USD":
                        val = val / 1000
                    elif unit == "shares":
                        val = val / 1000
                    raw[field_name] = val
                    break

        if "gross_profit" not in raw and "revenue" in raw and "cost_of_revenue" in raw:
            raw["gross_profit"] = raw["revenue"] - raw["cost_of_revenue"]

        if "total_liabilities" not in raw and "total_assets" in raw and "total_equity" in raw:
            raw["total_liabilities"] = raw["total_assets"] - raw["total_equity"]

        if all(k in raw for k in ("total_assets", "total_liabilities", "total_equity")):
            implied = raw["total_assets"] - raw["total_liabilities"]
            if abs(implied - raw["total_equity"]) > 500:
                raw["total_equity"] = implied

        return raw

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

        # ── Compute derived fields when not tagged directly ──────────────────
        if "gross_profit" in missing and "revenue" in raw and "cost_of_revenue" in raw:
            raw["gross_profit"] = raw["revenue"] - raw["cost_of_revenue"]
            missing.remove("gross_profit")

        if "total_liabilities" in missing and "total_assets" in raw and "total_equity" in raw:
            raw["total_liabilities"] = raw["total_assets"] - raw["total_equity"]
            missing.remove("total_liabilities")

        # Fix mezzanine-equity gap (e.g. redeemable NCI makes total_equity > assets - liabilities)
        if all(k in raw for k in ("total_assets", "total_liabilities", "total_equity")):
            implied_equity = raw["total_assets"] - raw["total_liabilities"]
            if abs(implied_equity - raw["total_equity"]) > 500:
                raw["total_equity"] = implied_equity

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
                research_and_development=g("research_and_development"),
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
