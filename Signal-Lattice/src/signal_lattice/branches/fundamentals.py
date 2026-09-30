"""从时点事实库（FactStore）派生打分所需的基本面与估值指标。

铁律：这里读的每一个事实都只经过 FactStore.facts_as_of(cik, concept, as_of)，
即只用 as_of 当天收盘前已申报的数；as_of 之后才申报的数（含重述）看不到。
每个指标都带 EvidenceRef（accession + SEC 原文链接），供收据逐条列出。
"""

from __future__ import annotations

import statistics
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..evidence.factstore import Fact, FactStore, filing_index_url
from .scoring_support import KIND_ESTIMATE, KIND_MARKET, KIND_XBRL, EvidenceRef, dedupe_refs

# ---- 概念表（us-gaap 前缀省略处均为 us-gaap；dei 显式写出）-------------------------
REVENUE_CONCEPTS = (
    "us-gaap:Revenues",
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
    "us-gaap:SalesRevenueNet",
    "us-gaap:SalesRevenueGoodsNet",
    "us-gaap:SalesRevenueServicesNet",
)
GROSS_PROFIT_CONCEPTS = ("us-gaap:GrossProfit",)
COST_OF_REVENUE_CONCEPTS = ("us-gaap:CostOfRevenue", "us-gaap:CostOfGoodsAndServicesSold",
                            "us-gaap:CostOfGoodsSold")
OPERATING_INCOME_CONCEPTS = ("us-gaap:OperatingIncomeLoss",)
OCF_CONCEPTS = ("us-gaap:NetCashProvidedByUsedInOperatingActivities",)
CAPEX_CONCEPTS = ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap:PaymentsToAcquireProductiveAssets")
SBC_CONCEPTS = ("us-gaap:ShareBasedCompensation",)
BUYBACK_CONCEPTS = ("us-gaap:PaymentsForRepurchaseOfCommonStock",)
ISSUANCE_CONCEPTS = ("us-gaap:ProceedsFromIssuanceOfCommonStock", "us-gaap:ProceedsFromIssuanceOrSaleOfEquity")
INTEREST_CONCEPTS = ("us-gaap:InterestExpense", "us-gaap:InterestPaidNet", "us-gaap:InterestPaid")
TAX_CONCEPTS = ("us-gaap:IncomeTaxesPaidNet", "us-gaap:IncomeTaxesPaid", "us-gaap:IncomeTaxExpenseBenefit")
WORKING_CAPITAL_CONCEPTS = ("us-gaap:IncreaseDecreaseInAccountsReceivable", "us-gaap:IncreaseDecreaseInInventories",
                            "us-gaap:IncreaseDecreaseInAccountsPayable")
RPO_CONCEPTS = ("us-gaap:RevenueRemainingPerformanceObligation",)
DEFERRED_REV_CONCEPTS = ("us-gaap:ContractWithCustomerLiability", "us-gaap:ContractWithCustomerLiabilityCurrent")
CASH_CONCEPTS = ("us-gaap:CashAndCashEquivalentsAtCarryingValue",
                 "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents")
STI_CONCEPTS = ("us-gaap:ShortTermInvestments", "us-gaap:MarketableSecuritiesCurrent",
                "us-gaap:AvailableForSaleSecuritiesDebtSecuritiesCurrent")
DEBT_TOTAL_CONCEPTS = ("us-gaap:LongTermDebt", "us-gaap:DebtInstrumentCarryingAmount")
DEBT_NONCURRENT_CONCEPTS = ("us-gaap:LongTermDebtNoncurrent",)
DEBT_CURRENT_CONCEPTS = ("us-gaap:LongTermDebtCurrent", "us-gaap:DebtCurrent")
EQUITY_CONCEPTS = ("us-gaap:StockholdersEquity",)
CURRENT_ASSETS_CONCEPTS = ("us-gaap:AssetsCurrent",)
CURRENT_LIABILITIES_CONCEPTS = ("us-gaap:LiabilitiesCurrent",)
PPE_CONCEPTS = ("us-gaap:PropertyPlantAndEquipmentNet",)
INVENTORY_CONCEPTS = ("us-gaap:InventoryNet",)
COVER_SHARES_CONCEPTS = ("dei:EntityCommonStockSharesOutstanding",)
BS_SHARES_CONCEPTS = ("us-gaap:CommonStockSharesOutstanding",)
DILUTED_SHARES_CONCEPTS = ("us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",)
BASIC_SHARES_CONCEPTS = ("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic",)
ANTIDILUTIVE_CONCEPTS = ("us-gaap:AntidilutiveSecuritiesExcludedFromComputationOfEarningsPerShareAmount",)

# 事实库里只入这些概念（sec_inputs 用它裁剪 companyfacts，避免把每家上万行都存下来）
NEEDED_CONCEPTS: Tuple[str, ...] = tuple(sorted(set(
    REVENUE_CONCEPTS + GROSS_PROFIT_CONCEPTS + COST_OF_REVENUE_CONCEPTS + OPERATING_INCOME_CONCEPTS
    + OCF_CONCEPTS + CAPEX_CONCEPTS + SBC_CONCEPTS + BUYBACK_CONCEPTS + ISSUANCE_CONCEPTS + INTEREST_CONCEPTS
    + TAX_CONCEPTS + WORKING_CAPITAL_CONCEPTS + RPO_CONCEPTS + DEFERRED_REV_CONCEPTS + CASH_CONCEPTS + STI_CONCEPTS
    + DEBT_TOTAL_CONCEPTS + DEBT_NONCURRENT_CONCEPTS + DEBT_CURRENT_CONCEPTS + EQUITY_CONCEPTS
    + CURRENT_ASSETS_CONCEPTS + CURRENT_LIABILITIES_CONCEPTS + PPE_CONCEPTS + INVENTORY_CONCEPTS
    + COVER_SHARES_CONCEPTS + BS_SHARES_CONCEPTS + DILUTED_SHARES_CONCEPTS + BASIC_SHARES_CONCEPTS
    + ANTIDILUTIVE_CONCEPTS + ("dei:EntityPublicFloat",)
)))

PERIODIC_FORMS = ("10-K", "10-KT", "10-Q", "10-QT")
ANNUAL_FORMS = ("10-K", "10-KT")
US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK "
    "OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR".split())
CHINA_HK_CODES = frozenset({"F4", "K3"})  # SEC 登记地代码：中国大陆、香港


def _d(text: str) -> date:
    return date.fromisoformat(text)


def _shift_year(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 2 月 29 日
        return day.replace(year=day.year + years, day=28)


def _span(fact: Fact) -> Optional[int]:
    return (_d(fact.period_end) - _d(fact.period_start)).days if fact.period_start else None


@dataclass(frozen=True)
class M:
    """一个带证据的数值指标；value=None 表示拿不到（不是 0）。"""
    value: Optional[float]
    refs: Tuple[EvidenceRef, ...] = ()
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.value is not None


MISSING = M(None)


class FactView:
    """把 FactStore 绑定到 (cik, as_of)：所有读取都是 facts_as_of，且带原文链接。"""

    def __init__(self, store: FactStore, cik: int, as_of: str) -> None:
        self.store = store
        self.cik = int(cik)
        self.as_of = as_of
        self._series: Dict[Tuple[Tuple[str, ...], str], List[Fact]] = {}
        self._filings: Optional[Dict[str, dict]] = None

    # ---- 链接 -------------------------------------------------------------
    def filing_rows(self) -> Dict[str, dict]:
        if self._filings is None:
            self._filings = {row["accession"]: row for row in self.store.filings_as_of(self.cik, self.as_of)}
        return self._filings

    def doc_url(self, accession: str) -> str:
        row = self.filing_rows().get(accession)
        primary = (row or {}).get("primary_document")
        if primary and "/" not in primary:
            return "https://www.sec.gov/Archives/edgar/data/%d/%s/%s" % (self.cik, accession.replace("-", ""), primary)
        return filing_index_url(self.cik, accession)

    def ref(self, fact: Fact, label: Optional[str] = None) -> EvidenceRef:
        return EvidenceRef(
            kind=KIND_XBRL,
            label=label or "%s %s" % (fact.concept, ("%s..%s" % (fact.period_start, fact.period_end))
                                      if fact.period_start else "@" + fact.period_end),
            value=fact.value, accession=fact.accession, form=fact.form, filed=fact.filed,
            period_end=fact.period_end, url=self.doc_url(fact.accession),
        )

    # ---- 序列 -------------------------------------------------------------
    def merged(self, concepts: Sequence[str], unit: str = "USD") -> List[Fact]:
        """按优先级合并同义概念：同一期（start,end）取排在前面的概念，跨年代换标签的公司也能接上。"""
        key = (tuple(concepts), unit)
        if key in self._series:
            return self._series[key]
        chosen: Dict[Tuple[Optional[str], str], Fact] = {}
        for concept in concepts:
            for fact in self.store.facts_as_of(self.cik, concept, self.as_of, unit):
                chosen.setdefault((fact.period_start, fact.period_end), fact)
        out = sorted(chosen.values(), key=lambda f: (f.period_end, f.period_start or ""))
        self._series[key] = out
        return out

    def durations(self, concepts: Sequence[str], unit: str = "USD") -> List[Fact]:
        return [f for f in self.merged(concepts, unit) if f.period_start]

    def instants(self, concepts: Sequence[str], unit: str = "USD") -> List[Fact]:
        return [f for f in self.merged(concepts, unit) if not f.period_start]

    # ---- 流量：TTM 与同比 ----------------------------------------------------
    @staticmethod
    def _ttm_at(dur: Sequence[Fact], end: str) -> Optional[Tuple[float, List[Fact]]]:
        at_end = [f for f in dur if f.period_end == end and 60 <= (_span(f) or 0) <= 380]
        if not at_end:
            return None
        cur = max(at_end, key=lambda f: _span(f) or 0)
        span = _span(cur) or 0
        if span >= 340:
            return cur.value, [cur]
        start = _d(cur.period_start)
        fy = [f for f in dur if 340 <= (_span(f) or 0) <= 380
              and abs((_d(f.period_end) - (start - timedelta(days=1))).days) <= 10]
        target = _shift_year(_d(cur.period_end), -1)
        prior = [f for f in dur if abs((_span(f) or 0) - span) <= 10 and abs((_d(f.period_end) - target).days) <= 10]
        if not fy or not prior:
            return None
        fy_fact = max(fy, key=lambda f: f.period_end)
        prior_fact = min(prior, key=lambda f: abs((_d(f.period_end) - target).days))
        return fy_fact.value + cur.value - prior_fact.value, [fy_fact, cur, prior_fact]

    def ttm(self, concepts: Sequence[str], unit: str = "USD") -> Tuple[M, M, Optional[str]]:
        """(最近 TTM, 一年前 TTM, TTM 截止日)。最近一期拼不成 TTM 时依次退到更早一期，最多退 3 期。"""
        dur = self.durations(concepts, unit)
        ends = sorted({f.period_end for f in dur if 60 <= (_span(f) or 0) <= 380}, reverse=True)
        for end in ends[:3]:
            cur = self._ttm_at(dur, end)
            if cur is None:
                continue
            target = _shift_year(_d(end), -1)
            prior_ends = [e for e in ends if abs((_d(e) - target).days) <= 10]
            prior = self._ttm_at(dur, prior_ends[0]) if prior_ends else None
            cur_m = M(cur[0], tuple(self.ref(f) for f in cur[1]), "TTM@" + end)
            prior_m = M(prior[0], tuple(self.ref(f) for f in prior[1]), "TTM@" + prior_ends[0]) if prior else MISSING
            return cur_m, prior_m, end
        return MISSING, MISSING, None

    def latest_quarter_yoy(self, concepts: Sequence[str]) -> M:
        """最近一个单季（约 90 天）对去年同期的同比。取不到不硬凑。"""
        dur = [f for f in self.durations(concepts) if 75 <= (_span(f) or 0) <= 105]
        if not dur:
            return MISSING
        cur = max(dur, key=lambda f: f.period_end)
        target = _shift_year(_d(cur.period_end), -1)
        prior = [f for f in dur if abs((_d(f.period_end) - target).days) <= 10]
        if not prior or prior[0].value <= 0:
            return MISSING
        prior_fact = prior[0]
        return M(cur.value / prior_fact.value - 1.0, (self.ref(cur), self.ref(prior_fact)), "quarter@" + cur.period_end)

    def annual_series(self, concepts: Sequence[str]) -> List[Fact]:
        return [f for f in self.durations(concepts) if 340 <= (_span(f) or 0) <= 380]

    # ---- 时点值 -------------------------------------------------------------
    def latest_instant(self, concepts: Sequence[str], unit: str = "USD") -> Optional[Fact]:
        inst = self.instants(concepts, unit)
        return max(inst, key=lambda f: (f.period_end, f.filed)) if inst else None

    def instant_near(self, concepts: Sequence[str], target: date, tolerance_days: int, unit: str = "USD") -> Optional[Fact]:
        inst = [f for f in self.instants(concepts, unit) if abs((_d(f.period_end) - target).days) <= tolerance_days]
        return min(inst, key=lambda f: abs((_d(f.period_end) - target).days)) if inst else None

    def instant_yoy(self, concepts: Sequence[str], unit: str = "USD", tolerance_days: int = 60) -> M:
        latest = self.latest_instant(concepts, unit)
        if latest is None:
            return MISSING
        prior = self.instant_near(concepts, _shift_year(_d(latest.period_end), -1), tolerance_days, unit)
        if prior is None or prior.value <= 0:
            return MISSING
        return M(latest.value / prior.value - 1.0, (self.ref(latest), self.ref(prior)),
                 "%s vs %s" % (latest.period_end, prior.period_end))


# ---- 行情输入 ------------------------------------------------------------------
@dataclass(frozen=True)
class MarketInput:
    symbol: str
    cik: int
    name: str
    price: float
    market_cap: float
    median_dollar_volume: float
    shares: float
    exchange: str
    state_of_business: Optional[str]
    sic: Optional[str]
    flags: Tuple[str, ...]
    sina_market_cap: Optional[float]
    price_source: str = "sina_gb"
    history: Tuple[Tuple[str, float], ...] = ()   # (YYYY-MM-DD, 前复权收盘)，升序，且不晚于 as_of

    @staticmethod
    def from_entry(entry: Mapping[str, Any], history: Sequence[Tuple[str, float]] = ()) -> "MarketInput":
        return MarketInput(
            symbol=entry["symbol"], cik=int(entry["cik"]), name=entry["name"], price=float(entry["price_usd"]),
            market_cap=float(entry["market_cap_usd"]), median_dollar_volume=float(entry["median_dollar_volume_20d_usd"]),
            shares=float(entry["shares_outstanding"]), exchange=entry.get("exchange", ""),
            state_of_business=entry.get("state_of_business"), sic=entry.get("sic"),
            flags=tuple(entry.get("flags") or ()), sina_market_cap=entry.get("sina_market_cap_usd"),
            history=tuple(history),
        )

    def history_upto(self, as_of: str) -> List[Tuple[str, float]]:
        return [(day, close) for day, close in self.history if day <= as_of]

    def market_ref(self, as_of: str) -> EvidenceRef:
        return EvidenceRef(kind=KIND_MARKET, label="quote %s price %.2f, cap %.0f (%s)" % (
            self.symbol, self.price, self.market_cap, self.price_source), value=self.price, period_end=as_of)


# ---- 下次财报预计日 --------------------------------------------------------------
@dataclass(frozen=True)
class ReportEstimate:
    est_date: str
    days_until: int
    basis: str
    refs: Tuple[EvidenceRef, ...]
    status: str = "ESTIMATED"   # 永远是推算，不是公司确认的日期


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    # 上月末的报告期截止日仍落在月末
    import calendar
    last = calendar.monthrange(year, month)[1]
    is_month_end = day.day == calendar.monthrange(day.year, day.month)[1]
    return date(year, month, last if is_month_end else min(day.day, last))


def estimate_next_report(view: FactView) -> Optional[ReportEstimate]:
    """按过去申报节奏推算下一份 10-Q/10-K 的申报日：下一报告期末 + 同类报告近几期的申报滞后中位数。"""
    rows = [r for r in view.store.filings_as_of(view.cik, view.as_of, PERIODIC_FORMS) if r.get("report_date")]
    if len(rows) < 2:
        return None
    rows.sort(key=lambda r: (r["report_date"], r["filed"]))
    last = rows[-1]
    last_end = _d(last["report_date"])
    annual_ends = [_d(r["report_date"]) for r in rows if r["form"] in ANNUAL_FORMS]
    next_end = _add_months(last_end, 3)
    is_annual = bool(annual_ends) and any(abs((next_end - _shift_year(a, k)).days) <= 20 for a in annual_ends for k in range(0, 4))
    same_kind = [r for r in rows if (r["form"] in ANNUAL_FORMS) == is_annual][-4:]
    if not same_kind:
        same_kind = rows[-4:]
    lags = [(_d(r["filed"]) - _d(r["report_date"])).days for r in same_kind]
    lags = [lag for lag in lags if 0 < lag < 150]
    if not lags:
        return None
    lag = int(statistics.median(lags))
    est = next_end + timedelta(days=lag)
    days_until = (est - _d(view.as_of)).days
    refs = tuple(EvidenceRef(kind=KIND_ESTIMATE, label="cadence %s report_date %s filed %s" % (r["form"], r["report_date"], r["filed"]),
                             accession=r["accession"], form=r["form"], filed=r["filed"], period_end=r["report_date"],
                             url=view.doc_url(r["accession"])) for r in same_kind[-3:])
    basis = "next %s period end %s + median filing lag %dd (%d filings)" % (
        "annual" if is_annual else "quarterly", next_end.isoformat(), lag, len(lags))
    return ReportEstimate(est.isoformat(), days_until, basis, refs)


# ---- 基本面汇总 ------------------------------------------------------------------
@dataclass
class Fundamentals:
    cik: int
    symbol: str
    name: str
    as_of: str
    market: MarketInput
    revenue_concept_used: Optional[str] = None
    revenue_ttm: M = MISSING
    revenue_ttm_prior: M = MISSING
    revenue_yoy: M = MISSING
    revenue_q_yoy: M = MISSING
    ttm_end: Optional[str] = None
    gross_profit_ttm: M = MISSING
    gross_margin: M = MISSING
    gross_margin_prior: M = MISSING
    gm_change_bps: M = MISSING
    op_income_ttm: M = MISSING
    op_margin: M = MISSING
    ocf_ttm: M = MISSING
    capex_ttm: M = MISSING
    capex_ttm_prior: M = MISSING
    fcf_ttm: M = MISSING
    fcf_margin: M = MISSING
    ocf_margin: M = MISSING
    capex_intensity: M = MISSING
    sbc_ttm: M = MISSING
    buyback_ttm: M = MISSING
    issuance_ttm: M = MISSING
    net_buyback_yield: M = MISSING
    rpo: M = MISSING
    rpo_yoy: M = MISSING
    rpo_months: M = MISSING
    deferred_rev_yoy: M = MISSING
    cash: M = MISSING
    sti: M = MISSING
    debt: M = MISSING
    net_cash: M = MISSING
    debt_assumed_zero: bool = False        # 申报里从未出现任何债务标签：按「无债务」估算净现金，标记为代理（评分封顶）
    net_cash_to_cap: M = MISSING
    equity: M = MISSING
    current_ratio: M = MISSING
    ppe_yoy: M = MISSING
    inventory_yoy: M = MISSING
    cash_runway_months: M = MISSING        # 仅经营现金流为负时有值
    share_change_yoy: M = MISSING
    diluted_shares: M = MISSING
    annual_revenue_growth: Tuple[float, ...] = ()
    annual_revenue_refs: Tuple[EvidenceRef, ...] = ()
    latest_periodic: Optional[dict] = None
    latest_period_end: Optional[str] = None
    latest_period_age_days: Optional[int] = None
    filings_seen: int = 0
    nt_filings_24m: int = 0
    nonreliance_8k_24m: int = 0
    auditor_change_8k_24m: int = 0
    restatement: M = MISSING               # value=最大相对重述幅度；None=无法核对
    bridge_checks: Dict[str, bool] = field(default_factory=dict)
    cap_sales: M = MISSING
    cap_gp: M = MISSING
    ev_sales: M = MISSING
    fcf_yield: M = MISSING
    hist_cap_sales: Tuple[float, ...] = ()
    hist_cap_sales_pct: M = MISSING        # 当前 市值/营收 在自身历史（季度采样）中的分位
    hist_cap_gp_pct: M = MISSING
    ret_63d: Optional[float] = None
    ret_252d: Optional[float] = None
    below_52w_high: Optional[float] = None
    next_report: Optional[ReportEstimate] = None
    notes: List[str] = field(default_factory=list)

    @property
    def sic2(self) -> Optional[str]:
        sic = self.market.sic
        return sic[:2] if sic else None


def _margin(num: M, den: M) -> M:
    if num.ok and den.ok and den.value and den.value > 0:
        return M(num.value / den.value, dedupe_refs(num.refs + den.refs))
    return MISSING


def _fraction_change(cur: M, prior: M) -> M:
    if cur.ok and prior.ok and prior.value and prior.value > 0:
        return M(cur.value / prior.value - 1.0, dedupe_refs(cur.refs + prior.refs), "%s vs %s" % (cur.note, prior.note))
    return MISSING


def _ttm_metric(view: FactView, concepts: Sequence[str]) -> Tuple[M, M, Optional[str]]:
    return view.ttm(concepts)


def _gross_profit(view: FactView, revenue_cur: M, revenue_prior: M, end: Optional[str]) -> Tuple[M, M]:
    gp_cur, gp_prior, gp_end = view.ttm(GROSS_PROFIT_CONCEPTS)
    if gp_cur.ok and (end is None or gp_end == end):
        return gp_cur, gp_prior
    cost_cur, cost_prior, cost_end = view.ttm(COST_OF_REVENUE_CONCEPTS)
    if cost_cur.ok and revenue_cur.ok and cost_end == end:
        cur = M(revenue_cur.value - cost_cur.value, dedupe_refs(revenue_cur.refs + cost_cur.refs), "revenue-cost@" + str(end))
        prior = (M(revenue_prior.value - cost_prior.value, dedupe_refs(revenue_prior.refs + cost_prior.refs), "revenue-cost prior")
                 if revenue_prior.ok and cost_prior.ok else MISSING)
        return cur, prior
    if gp_cur.ok:
        return gp_cur, gp_prior
    return MISSING, MISSING


def _restatement(view: FactView, concepts: Sequence[str]) -> M:
    """同一期的原值与重述值（都在 as_of 之前申报）相差多少。相差大 = 潜在矛盾。"""
    biggest = 0.0
    refs: List[EvidenceRef] = []
    checked = 0
    for concept in concepts:
        versions = [f for f in view.store.all_versions(view.cik, concept) if f.filed <= view.as_of and f.unit == "USD"]
        groups: Dict[Tuple[Optional[str], str], List[Fact]] = {}
        for fact in versions:
            groups.setdefault((fact.period_start, fact.period_end), []).append(fact)
        for facts in groups.values():
            if len(facts) < 2:
                continue
            checked += 1
            first, last = facts[0], facts[-1]
            if first.value:
                delta = abs(last.value - first.value) / abs(first.value)
                if delta > biggest:
                    biggest = delta
                    refs = [view.ref(first), view.ref(last)]
        if checked:
            break
    return M(biggest, tuple(refs), "%d restated periods checked" % checked) if checked else M(0.0, (), "no restated periods")


def _share_change(view: FactView, notes: List[str]) -> Tuple[M, M]:
    cover = view.instants(COVER_SHARES_CONCEPTS, "shares") or view.instants(BS_SHARES_CONCEPTS, "shares")
    cover_change = MISSING
    if cover:
        latest = max(cover, key=lambda f: (f.period_end, f.filed))
        prior = view.instant_near(COVER_SHARES_CONCEPTS + BS_SHARES_CONCEPTS, _shift_year(_d(latest.period_end), -1), 75, "shares")
        if prior and prior.value > 0:
            cover_change = M(latest.value / prior.value - 1.0, (view.ref(latest), view.ref(prior)),
                             "cover/bs shares %s vs %s" % (latest.period_end, prior.period_end))
    # 加权稀释股数是「平均值」而非流量，不能拼 TTM：直接比最近一期与一年前同期的同长度期间。
    dur = view.durations(DILUTED_SHARES_CONCEPTS, "shares")
    ws_change = MISSING
    diluted = MISSING
    if dur:
        latest = max(dur, key=lambda f: (f.period_end, _span(f) or 0))
        span = _span(latest) or 0
        target = _shift_year(_d(latest.period_end), -1)
        prior = [f for f in dur if abs((_span(f) or 0) - span) <= 10 and abs((_d(f.period_end) - target).days) <= 10]
        diluted = M(latest.value, (view.ref(latest),), "diluted weighted shares %s" % latest.period_end)
        if prior and prior[0].value > 0:
            ws_change = M(latest.value / prior[0].value - 1.0, (view.ref(latest), view.ref(prior[0])),
                          "diluted weighted %s vs %s" % (latest.period_end, prior[0].period_end))
    if cover_change.ok and ws_change.ok and abs(cover_change.value - ws_change.value) > 0.25:
        notes.append("SHARE_COUNT_SOURCES_DISAGREE:cover=%.3f,weighted=%.3f;using weighted" % (cover_change.value, ws_change.value))
        return ws_change, diluted
    if cover_change.ok:
        return cover_change, diluted
    return ws_change, diluted


def compute_fundamentals(store: FactStore, market: MarketInput, as_of: str) -> Fundamentals:
    view = FactView(store, market.cik, as_of)
    f = Fundamentals(cik=market.cik, symbol=market.symbol, name=market.name, as_of=as_of, market=market)

    # 营收：优先取能拼出最新 TTM 的概念序列
    f.revenue_ttm, f.revenue_ttm_prior, f.ttm_end = view.ttm(REVENUE_CONCEPTS)
    f.revenue_yoy = _fraction_change(f.revenue_ttm, f.revenue_ttm_prior)
    f.revenue_q_yoy = view.latest_quarter_yoy(REVENUE_CONCEPTS)
    f.gross_profit_ttm, gp_prior = _gross_profit(view, f.revenue_ttm, f.revenue_ttm_prior, f.ttm_end)
    f.gross_margin = _margin(f.gross_profit_ttm, f.revenue_ttm)
    f.gross_margin_prior = _margin(gp_prior, f.revenue_ttm_prior)
    if f.gross_margin.ok and f.gross_margin_prior.ok:
        f.gm_change_bps = M((f.gross_margin.value - f.gross_margin_prior.value) * 10000.0,
                            dedupe_refs(f.gross_margin.refs + f.gross_margin_prior.refs), "gross margin TTM change")
    op_cur, _, op_end = view.ttm(OPERATING_INCOME_CONCEPTS)
    f.op_income_ttm = op_cur if op_cur.ok and op_end == f.ttm_end else MISSING
    f.op_margin = _margin(f.op_income_ttm, f.revenue_ttm)

    ocf_cur, _, ocf_end = view.ttm(OCF_CONCEPTS)
    f.ocf_ttm = ocf_cur if ocf_cur.ok and ocf_end == f.ttm_end else MISSING
    capex_cur, capex_prior, capex_end = view.ttm(CAPEX_CONCEPTS)
    f.capex_ttm = capex_cur if capex_cur.ok and capex_end == f.ttm_end else MISSING
    f.capex_ttm_prior = capex_prior if f.capex_ttm.ok else MISSING
    if f.ocf_ttm.ok and f.capex_ttm.ok:
        f.fcf_ttm = M(f.ocf_ttm.value - abs(f.capex_ttm.value), dedupe_refs(f.ocf_ttm.refs + f.capex_ttm.refs), "OCF - capex")
    f.fcf_margin = _margin(f.fcf_ttm, f.revenue_ttm)
    f.ocf_margin = _margin(f.ocf_ttm, f.revenue_ttm)
    if f.capex_ttm.ok and f.revenue_ttm.ok and f.revenue_ttm.value > 0:
        f.capex_intensity = M(abs(f.capex_ttm.value) / f.revenue_ttm.value, dedupe_refs(f.capex_ttm.refs + f.revenue_ttm.refs))
    sbc, _, sbc_end = view.ttm(SBC_CONCEPTS)
    f.sbc_ttm = sbc if sbc.ok and sbc_end == f.ttm_end else MISSING
    buyback, _, bb_end = view.ttm(BUYBACK_CONCEPTS)
    f.buyback_ttm = buyback if buyback.ok and bb_end == f.ttm_end else MISSING
    issuance, _, is_end = view.ttm(ISSUANCE_CONCEPTS)
    f.issuance_ttm = issuance if issuance.ok and is_end == f.ttm_end else MISSING

    # 积压 / 递延收入
    rpo = view.latest_instant(RPO_CONCEPTS)
    if rpo is not None:
        f.rpo = M(rpo.value, (view.ref(rpo),), "RPO@" + rpo.period_end)
        f.rpo_yoy = view.instant_yoy(RPO_CONCEPTS)
        if f.revenue_ttm.ok and f.revenue_ttm.value > 0:
            f.rpo_months = M(rpo.value / (f.revenue_ttm.value / 12.0), dedupe_refs(f.rpo.refs + f.revenue_ttm.refs),
                             "RPO / monthly TTM revenue")
    f.deferred_rev_yoy = view.instant_yoy(DEFERRED_REV_CONCEPTS)

    # 资产负债表
    cash = view.latest_instant(CASH_CONCEPTS)
    if cash is not None:
        f.cash = M(cash.value, (view.ref(cash),), "cash@" + cash.period_end)
    sti = view.latest_instant(STI_CONCEPTS)
    if sti is not None and cash is not None and abs((_d(sti.period_end) - _d(cash.period_end)).days) <= 10:
        f.sti = M(sti.value, (view.ref(sti),), "short-term investments@" + sti.period_end)
    debt_total = view.latest_instant(DEBT_TOTAL_CONCEPTS)
    debt_nc = view.latest_instant(DEBT_NONCURRENT_CONCEPTS)
    debt_c = view.latest_instant(DEBT_CURRENT_CONCEPTS)
    if debt_total is not None and cash is not None and abs((_d(debt_total.period_end) - _d(cash.period_end)).days) <= 10:
        f.debt = M(debt_total.value, (view.ref(debt_total),), "total debt@" + debt_total.period_end)
    elif debt_nc is not None and cash is not None and abs((_d(debt_nc.period_end) - _d(cash.period_end)).days) <= 10:
        extra = debt_c.value if debt_c is not None and debt_c.period_end == debt_nc.period_end else 0.0
        f.debt = M(debt_nc.value + extra, tuple(view.ref(x) for x in (debt_nc, debt_c) if x is not None), "noncurrent+current debt")
    any_debt_tag = bool(view.instants(DEBT_TOTAL_CONCEPTS) or view.instants(DEBT_NONCURRENT_CONCEPTS)
                        or view.instants(DEBT_CURRENT_CONCEPTS))
    if cash is not None and f.debt.ok:
        liquid = cash.value + (f.sti.value if f.sti.ok else 0.0)
        f.net_cash = M(liquid - f.debt.value, dedupe_refs(f.cash.refs + f.sti.refs + f.debt.refs), "cash+STI-debt")
    elif cash is not None and not any_debt_tag:
        # 任何一期都没有债务标签：XBRL 要求披露的债务通常会被标注，所以按「无债务」估算，但这只是代理，评分封顶
        f.debt_assumed_zero = True
        f.debt = M(0.0, (), "DEBT_TAG_ABSENT_ASSUMED_ZERO")
        liquid = cash.value + (f.sti.value if f.sti.ok else 0.0)
        f.net_cash = M(liquid, dedupe_refs(f.cash.refs + f.sti.refs), "cash+STI (no debt tag in any period; assumed zero)")
        f.notes.append("DEBT_TAG_ABSENT_ASSUMED_ZERO")
    if f.net_cash.ok and market.market_cap > 0:
        f.net_cash_to_cap = M(f.net_cash.value / market.market_cap, f.net_cash.refs)
    equity = view.latest_instant(EQUITY_CONCEPTS)
    if equity is not None:
        f.equity = M(equity.value, (view.ref(equity),), "equity@" + equity.period_end)
    ca, cl = view.latest_instant(CURRENT_ASSETS_CONCEPTS), view.latest_instant(CURRENT_LIABILITIES_CONCEPTS)
    if ca is not None and cl is not None and ca.period_end == cl.period_end and cl.value > 0:
        f.current_ratio = M(ca.value / cl.value, (view.ref(ca), view.ref(cl)), "current ratio@" + ca.period_end)
    f.ppe_yoy = view.instant_yoy(PPE_CONCEPTS)
    f.inventory_yoy = view.instant_yoy(INVENTORY_CONCEPTS)
    if f.ocf_ttm.ok and f.ocf_ttm.value < 0 and cash is not None:
        liquid = cash.value + (f.sti.value if f.sti.ok else 0.0)
        f.cash_runway_months = M(liquid / (-f.ocf_ttm.value / 12.0), dedupe_refs(f.cash.refs + f.sti.refs + f.ocf_ttm.refs),
                                 "liquid cash / monthly operating burn")
    if f.buyback_ttm.ok or f.issuance_ttm.ok:
        net = (abs(f.buyback_ttm.value) if f.buyback_ttm.ok else 0.0) - (f.issuance_ttm.value if f.issuance_ttm.ok else 0.0)
        f.net_buyback_yield = M(net / market.market_cap if market.market_cap > 0 else None,
                                dedupe_refs(f.buyback_ttm.refs + f.issuance_ttm.refs), "(buyback - issuance proceeds)/cap")
    f.share_change_yoy, f.diluted_shares = _share_change(view, f.notes)

    # 年度营收增速序列（周期性）
    annual = view.annual_series(REVENUE_CONCEPTS)
    growth = []
    for prev, cur in zip(annual, annual[1:]):
        if prev.value > 0 and 300 <= (_d(cur.period_end) - _d(prev.period_end)).days <= 430:
            growth.append(cur.value / prev.value - 1.0)
    f.annual_revenue_growth = tuple(growth[-5:])
    f.annual_revenue_refs = tuple(view.ref(x) for x in annual[-6:])

    # 申报清单：新鲜度、治理红旗、下次财报
    periodic = view.store.filings_as_of(market.cik, as_of, PERIODIC_FORMS)
    periodic = [r for r in periodic if r.get("report_date")]
    if periodic:
        latest = max(periodic, key=lambda r: (r["filed"], r["accession"]))
        f.latest_periodic = latest
        f.latest_period_end = latest["report_date"]
        f.latest_period_age_days = (_d(as_of) - _d(latest["report_date"])).days
    all_filings = view.store.filings_as_of(market.cik, as_of)
    f.filings_seen = len(all_filings)
    cutoff = (_d(as_of) - timedelta(days=730)).isoformat()
    for row in all_filings:
        if row["filed"] < cutoff:
            continue
        items = (row.get("items") or "").split(",")
        if row["form"] in ("NT 10-K", "NT 10-Q", "NT 10-K/A", "NT 10-Q/A"):
            f.nt_filings_24m += 1
        if row["form"] == "8-K" and "4.02" in items:
            f.nonreliance_8k_24m += 1
        if row["form"] == "8-K" and "4.01" in items:
            f.auditor_change_8k_24m += 1
    f.restatement = _restatement(view, REVENUE_CONCEPTS)
    f.next_report = estimate_next_report(view)

    # 估值（现价 × 现有股数 / TTM 营收等）与自身历史分位
    cap = market.market_cap
    if f.revenue_ttm.ok and f.revenue_ttm.value > 0:
        f.cap_sales = M(cap / f.revenue_ttm.value, dedupe_refs((market.market_ref(as_of),) + f.revenue_ttm.refs), "cap / TTM revenue")
    if f.gross_profit_ttm.ok and f.gross_profit_ttm.value > 0:
        f.cap_gp = M(cap / f.gross_profit_ttm.value, dedupe_refs((market.market_ref(as_of),) + f.gross_profit_ttm.refs), "cap / TTM gross profit")
    if f.net_cash.ok and f.revenue_ttm.ok and f.revenue_ttm.value > 0:
        f.ev_sales = M((cap - f.net_cash.value) / f.revenue_ttm.value, dedupe_refs(f.cap_sales.refs + f.net_cash.refs), "EV / TTM revenue")
    if f.fcf_ttm.ok and cap > 0:
        f.fcf_yield = M(f.fcf_ttm.value / cap, dedupe_refs((market.market_ref(as_of),) + f.fcf_ttm.refs), "FCF / cap")
    _history_metrics(store, f, market, as_of)
    return f


def _percentile(value: float, sample: Sequence[float]) -> float:
    ordered = sorted(sample)
    return bisect_right(ordered, value) / len(ordered)


def _history_metrics(store: FactStore, f: Fundamentals, market: MarketInput, as_of: str, samples: int = 12,
                     min_samples: int = 6) -> None:
    """自身历史分位：过去 12 个季度末，用「当时的收盘价 × 现有股数 / 当时已申报的 TTM 营收」（恒定股数近似）。

    这里的每个采样点都用 as_of=采样日 重新读事实库，所以历史点也是时点正确的。
    近似的方向是保守的：股数被稀释过的公司，历史市值被低估，当前分位偏高。"""
    hist = market.history_upto(as_of)
    if not hist:
        return
    days = [d for d, _ in hist]
    closes = [c for _, c in hist]
    last = _d(days[-1])
    f.ret_63d = closes[-1] / closes[max(0, len(closes) - 64)] - 1.0 if len(closes) > 63 else None
    f.ret_252d = closes[-1] / closes[max(0, len(closes) - 253)] - 1.0 if len(closes) > 252 else None
    window = closes[-252:]
    if window:
        f.below_52w_high = closes[-1] / max(window) - 1.0
    if not f.cap_sales.ok:
        return
    samples_cs: List[float] = []
    samples_cgp: List[float] = []
    for k in range(1, samples + 1):
        sample_day = last - timedelta(days=int(91.3 * k))
        idx = bisect_right(days, sample_day.isoformat()) - 1
        if idx < 0:
            continue
        price = closes[idx]
        sub = FactView(store, market.cik, sample_day.isoformat())
        rev, _, _ = sub.ttm(REVENUE_CONCEPTS)
        if rev.ok and rev.value > 0:
            samples_cs.append(price * market.shares / rev.value)
            gp, _, _ = sub.ttm(GROSS_PROFIT_CONCEPTS)
            if gp.ok and gp.value > 0:
                samples_cgp.append(price * market.shares / gp.value)
    if len(samples_cs) >= min_samples:
        f.hist_cap_sales = tuple(samples_cs)
        pct = _percentile(f.cap_sales.value, samples_cs)
        f.hist_cap_sales_pct = M(pct, f.cap_sales.refs, "own-history percentile of cap/sales over %d quarter-ends (constant shares)" % len(samples_cs))
    if len(samples_cgp) >= min_samples and f.cap_gp.ok:
        f.hist_cap_gp_pct = M(_percentile(f.cap_gp.value, samples_cgp), f.cap_gp.refs,
                              "own-history percentile of cap/gross profit over %d quarter-ends" % len(samples_cgp))


# ---- 同业对照（同 SIC 两位码；组太小退到全池）-----------------------------------------
@dataclass
class PeerContext:
    members: Dict[int, Fundamentals]
    min_group: int = 8

    @staticmethod
    def build(funds: Iterable[Fundamentals], min_group: int = 8) -> "PeerContext":
        return PeerContext({f.cik: f for f in funds}, min_group)

    def group(self, fund: Fundamentals) -> Tuple[List[Fundamentals], str]:
        same = [m for m in self.members.values() if m.sic2 and m.sic2 == fund.sic2 and m.cik != fund.cik]
        if len(same) + 1 >= self.min_group:
            return same, "SIC%s" % fund.sic2
        return [m for m in self.members.values() if m.cik != fund.cik], "UNIVERSE"

    def values(self, fund: Fundamentals, attr: str) -> Tuple[List[float], str]:
        peers, label = self.group(fund)
        vals = []
        for peer in peers:
            metric = getattr(peer, attr)
            if metric.ok:
                vals.append(float(metric.value))
        return vals, label

    def percentile(self, fund: Fundamentals, attr: str) -> Tuple[Optional[float], str, int]:
        own = getattr(fund, attr)
        vals, label = self.values(fund, attr)
        if not own.ok or len(vals) < max(3, self.min_group - 1):
            return None, label, len(vals)
        return _percentile(float(own.value), vals), label, len(vals)

    def median(self, fund: Fundamentals, attr: str) -> Tuple[Optional[float], str, int]:
        vals, label = self.values(fund, attr)
        if len(vals) < max(3, self.min_group - 1):
            return None, label, len(vals)
        return statistics.median(vals), label, len(vals)
