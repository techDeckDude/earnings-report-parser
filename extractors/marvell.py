from __future__ import annotations
import re
import zipfile
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from models import BalanceSheet, CashFlow, EarningsReport, IncomeStatement
from .base import BaseExtractor


def _to_thousands(raw: str, scale: int, unit: str) -> float:
    """
    Convert an iXBRL display value to thousands USD (or raw float for EPS).

    scale comes from the ix:nonFraction scale attribute (e.g. 6 = millions).
    unit is the unitRef (usd, shares, usdPerShare).
    EPS values (usdPerShare) are returned as-is; all others are converted to thousands.
    """
    clean = (
        raw.strip()
        .replace(",", "")
        .replace("&#8212;", "0")
        .replace("—", "0")
        .replace("–", "0")
    )
    if not clean:
        raise ValueError("empty value")
    actual = float(clean) * (10 ** scale)
    if unit == "usdPerShare":
        return actual
    return actual / 1000  # USD and shares → thousands


class _IXBRLDoc:
    """
    Parses all ix:nonFraction tags and xbrli:context definitions from an iXBRL HTML file.
    Provides typed lookups by (us-gaap tag name, contextRef).
    """

    def __init__(self, html: str):
        self._values: dict[tuple[str, str], float] = {}
        self._contexts: dict[str, dict] = {}
        self._parse_contexts(html)
        self._parse_tags(html)

    def _parse_contexts(self, html: str) -> None:
        for ctx_id, body in re.findall(
            r'<xbrli:context\s+id="([^"]+)">(.*?)</xbrli:context>', html, re.DOTALL
        ):
            # Skip dimensional (segmented) contexts — they contain member elements
            if "<xbrli:segment>" in body or "<xbrli:scenario>" in body:
                continue
            instant = re.search(r"<xbrli:instant>([^<]+)</xbrli:instant>", body)
            start = re.search(r"<xbrli:startDate>([^<]+)</xbrli:startDate>", body)
            end = re.search(r"<xbrli:endDate>([^<]+)</xbrli:endDate>", body)
            if instant:
                self._contexts[ctx_id] = {"type": "instant", "date": instant.group(1).strip()}
            elif start and end:
                self._contexts[ctx_id] = {
                    "type": "period",
                    "start": start.group(1).strip(),
                    "end": end.group(1).strip(),
                }

    def _parse_tags(self, html: str) -> None:
        for attrs, val in re.findall(
            r"<ix:nonFraction\s+([^>]+?)>([^<]*)</ix:nonFraction>", html
        ):
            name_m = re.search(r'name="([^"]+)"', attrs)
            ctx_m = re.search(r'contextRef="([^"]+)"', attrs)
            scale_m = re.search(r'scale="([^"]+)"', attrs)
            unit_m = re.search(r'unitRef="([^"]+)"', attrs)
            if not (name_m and ctx_m):
                continue
            key = (name_m.group(1), ctx_m.group(1))
            if key in self._values:
                continue  # keep first occurrence
            try:
                self._values[key] = _to_thousands(
                    val,
                    int(scale_m.group(1)) if scale_m else 0,
                    unit_m.group(1) if unit_m else "usd",
                )
            except (ValueError, TypeError):
                pass

    def _period_candidates(self, period_end: date) -> list[tuple[str, dict]]:
        target = period_end.isoformat()
        candidates = [
            (ctx_id, info)
            for ctx_id, info in self._contexts.items()
            if info["type"] == "period" and info["end"] == target
        ]
        if not candidates:
            raise ValueError(f"No period context found ending on {target}")
        return candidates

    def period_ctx(self, period_end: date) -> str:
        """
        Current-quarter context: latest startDate among all non-dimensional period
        contexts ending on period_end. For Q1 this equals ytd_ctx.
        """
        candidates = self._period_candidates(period_end)
        candidates.sort(key=lambda x: x[1]["start"], reverse=True)
        return candidates[0][0]

    def ytd_ctx(self, period_end: date) -> str:
        """
        YTD context: earliest startDate among all non-dimensional period contexts
        ending on period_end. Used for cash flow statements, which MRVL files YTD.
        """
        candidates = self._period_candidates(period_end)
        candidates.sort(key=lambda x: x[1]["start"])
        return candidates[0][0]

    def instant_ctx(self, instant_date: date) -> str:
        """Return the non-dimensional instant context whose date = instant_date."""
        target = instant_date.isoformat()
        for ctx_id, info in self._contexts.items():
            if info["type"] == "instant" and info["date"] == target:
                return ctx_id
        raise ValueError(f"No instant context found for date {target}")

    def get(self, name: str, ctx: str) -> float:
        key = (name, ctx)
        if key not in self._values:
            raise ValueError(f"iXBRL tag not found: {name!r} in context {ctx!r}")
        return self._values[key]

    def opt(self, name: str, ctx: str) -> Optional[float]:
        return self._values.get((name, ctx))


class MarvellExtractor(BaseExtractor):
    def can_handle(self, file_path: str) -> bool:
        return file_path.lower().endswith(".zip")

    def extract(self, file_path: str) -> EarningsReport:
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(file_path) as zf:
                zf.extractall(tmp)
            # Main filing is the HTM file named like mrvl-YYYYMMDD.htm (not exhibit files)
            htm_files = sorted(
                p for p in Path(tmp).glob("*.htm")
                if "exhibit" not in p.name.lower()
            )
            if not htm_files:
                raise ValueError(f"No main HTM file found in {file_path}")
            html = htm_files[0].read_text(encoding="utf-8", errors="replace")

        return self._parse(html)

    def _parse(self, html: str) -> EarningsReport:
        doc = _IXBRLDoc(html)
        meta = self._extract_metadata(html)
        period_end = meta["period_end_date"]

        p_ctx = doc.period_ctx(period_end)    # current quarter (income statement)
        ytd_ctx = doc.ytd_ctx(period_end)     # YTD (cash flow — MRVL files CF as YTD)
        bs_ctx = doc.instant_ctx(period_end)  # balance sheet

        return EarningsReport(
            company_name=meta["company_name"],
            ticker=meta["ticker"],
            period=meta["period"],
            period_end_date=period_end,
            filing_type="10-Q",
            income_statement=self._income_statement(doc, p_ctx),
            balance_sheet=self._balance_sheet(doc, bs_ctx),
            cash_flow=self._cash_flow(doc, ytd_ctx),
        )

    # ------------------------------------------------------------------
    # Metadata from DEI tags
    # ------------------------------------------------------------------

    def _extract_metadata(self, html: str) -> dict:
        def _dei(name: str) -> str:
            m = re.search(
                rf'<ix:nonNumeric[^>]+name="{re.escape(name)}"[^>]*>([^<]+)</ix:nonNumeric>',
                html,
            )
            return m.group(1).strip() if m else ""

        company_name = _dei("dei:EntityRegistrantName") or "Marvell Technology, Inc."
        ticker = _dei("dei:TradingSymbol") or "MRVL"
        fiscal_year = _dei("dei:DocumentFiscalYearFocus")
        fiscal_period = _dei("dei:DocumentFiscalPeriodFocus")   # "Q1", "Q2", …
        period_end_str = _dei("dei:DocumentPeriodEndDate")

        period_end_date = datetime.strptime(period_end_str, "%B %d, %Y").date()
        period = f"{fiscal_period} {fiscal_year}"

        return {
            "company_name": company_name,
            "ticker": ticker,
            "period": period,
            "period_end_date": period_end_date,
        }

    # ------------------------------------------------------------------
    # Financial statements
    # ------------------------------------------------------------------

    def _income_statement(self, doc: _IXBRLDoc, ctx: str) -> IncomeStatement:
        return IncomeStatement(
            revenue=doc.get("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", ctx),
            cost_of_revenue=doc.get("us-gaap:CostOfGoodsAndServicesSold", ctx),
            gross_profit=doc.get("us-gaap:GrossProfit", ctx),
            research_and_development=doc.get("us-gaap:ResearchAndDevelopmentExpense", ctx),
            selling_general_and_administrative=doc.get("us-gaap:SellingGeneralAndAdministrativeExpense", ctx),
            income_from_operations=doc.get("us-gaap:OperatingIncomeLoss", ctx),
            interest_expense=doc.opt("us-gaap:InterestExpenseNonoperating", ctx),
            income_tax_expense=doc.opt("us-gaap:IncomeTaxExpenseBenefit", ctx),
            net_income=doc.get("us-gaap:NetIncomeLoss", ctx),
            eps_basic=doc.get("us-gaap:EarningsPerShareBasic", ctx),
            eps_diluted=doc.get("us-gaap:EarningsPerShareDiluted", ctx),
            shares_outstanding_basic=doc.get("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", ctx),
            shares_outstanding_diluted=doc.get("us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding", ctx),
        )

    def _balance_sheet(self, doc: _IXBRLDoc, ctx: str) -> BalanceSheet:
        ap = doc.opt("us-gaap:AccountsPayableCurrent", ctx) or 0.0
        accrued = doc.opt("us-gaap:AccruedLiabilitiesCurrent", ctx) or 0.0

        return BalanceSheet(
            cash_and_equivalents=doc.get("us-gaap:CashAndCashEquivalentsAtCarryingValue", ctx),
            accounts_receivable_net=doc.get("us-gaap:AccountsReceivableNetCurrent", ctx),
            inventory=doc.opt("us-gaap:InventoryNet", ctx),
            prepaid_and_other_current=doc.opt("us-gaap:PrepaidExpenseAndOtherAssetsCurrent", ctx),
            total_current_assets=doc.get("us-gaap:AssetsCurrent", ctx),
            property_and_equipment_net=doc.get("us-gaap:PropertyPlantAndEquipmentNet", ctx),
            goodwill=doc.opt("us-gaap:Goodwill", ctx),
            intangible_assets=doc.opt("us-gaap:IntangibleAssetsNetExcludingGoodwill", ctx),
            deferred_tax_assets=doc.opt("us-gaap:DeferredIncomeTaxAssetsNet", ctx),
            other_assets=doc.opt("us-gaap:OtherAssetsNoncurrent", ctx),
            total_assets=doc.get("us-gaap:Assets", ctx),
            accounts_payable_and_accrued=ap + accrued,
            total_current_liabilities=doc.get("us-gaap:LiabilitiesCurrent", ctx),
            total_liabilities=doc.get("us-gaap:Liabilities", ctx),
            total_equity=doc.get("us-gaap:StockholdersEquity", ctx),
        )

    def _cash_flow(self, doc: _IXBRLDoc, ctx: str) -> CashFlow:
        return CashFlow(
            net_income=doc.get("us-gaap:NetIncomeLoss", ctx),
            stock_based_compensation=doc.opt("us-gaap:ShareBasedCompensation", ctx),
            capex=doc.opt("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", ctx),
            net_cash_from_operations=doc.get("us-gaap:NetCashProvidedByUsedInOperatingActivities", ctx),
            net_cash_from_investing=doc.get("us-gaap:NetCashProvidedByUsedInInvestingActivities", ctx),
            net_cash_from_financing=doc.get("us-gaap:NetCashProvidedByUsedInFinancingActivities", ctx),
        )
