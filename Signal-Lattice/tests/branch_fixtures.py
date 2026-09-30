"""B3a 测试夹具：用合成的 SEC companyfacts / submissions 造一个内存事实库。

时间线（财年 12 月 31 日结束）：
  FY2024 10-K 2025-03-03 申报；H1'24 10-Q 2024-08-05；H1'25 10-Q 2025-08-05；
  FY2025 10-K 2026-03-02 申报；H1'26 10-Q 2026-08-04 申报（as_of 之后才出现的「未来申报」）。
TTM@2026-06-30 = FY2025 + H1'26 − H1'25；TTM@2025-06-30 = FY2024 + H1'25 − H1'24。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from signal_lattice.branches.fundamentals import MarketInput
from signal_lattice.evidence.factstore import FactStore

CIK = 1234567

# 申报：period_end, form, filed, accession
FILINGS = [
    ("2024-06-30", "10-Q", "2024-08-05", "0001234567-24-000010"),
    ("2024-09-30", "10-Q", "2024-11-05", "0001234567-24-000015"),
    ("2024-12-31", "10-K", "2025-03-03", "0001234567-25-000003"),
    ("2025-03-31", "10-Q", "2025-05-06", "0001234567-25-000009"),
    ("2025-06-30", "10-Q", "2025-08-05", "0001234567-25-000020"),
    ("2025-09-30", "10-Q", "2025-11-04", "0001234567-25-000030"),
    ("2025-12-31", "10-K", "2026-03-02", "0001234567-26-000004"),
    ("2026-03-31", "10-Q", "2026-05-05", "0001234567-26-000012"),
    ("2026-06-30", "10-Q", "2026-08-04", "0001234567-26-000021"),   # 未来申报（相对 2026-07-15）
]
ACC = {(end, form): acc for end, form, filed, acc in FILINGS}
FILED = {acc: filed for _, _, filed, acc in FILINGS}


def _flow(tag: str, values: Dict[str, float], unit: str = "USD") -> Tuple[str, dict]:
    """values: FY24, H124, FY25, H125, H126 → companyfacts 条目。"""
    spec = {
        "FY24": ("2024-01-01", "2024-12-31", "10-K", ACC[("2024-12-31", "10-K")]),
        "H124": ("2024-01-01", "2024-06-30", "10-Q", ACC[("2024-06-30", "10-Q")]),
        "FY25": ("2025-01-01", "2025-12-31", "10-K", ACC[("2025-12-31", "10-K")]),
        "H125": ("2025-01-01", "2025-06-30", "10-Q", ACC[("2025-06-30", "10-Q")]),
        "H126": ("2026-01-01", "2026-06-30", "10-Q", ACC[("2026-06-30", "10-Q")]),
    }
    entries = []
    for key, value in values.items():
        start, end, form, acc = spec[key]
        entries.append({"start": start, "end": end, "val": value, "accn": acc, "form": form, "filed": FILED[acc],
                        "fy": int(end[:4]), "fp": "FY" if form == "10-K" else "Q2"})
    return tag, {"units": {unit: entries}}


def _instant(tag: str, values: Dict[str, float], unit: str = "USD") -> Tuple[str, dict]:
    spec = {
        "2024-06-30": ("10-Q", ACC[("2024-06-30", "10-Q")]),
        "2024-12-31": ("10-K", ACC[("2024-12-31", "10-K")]),
        "2025-06-30": ("10-Q", ACC[("2025-06-30", "10-Q")]),
        "2025-12-31": ("10-K", ACC[("2025-12-31", "10-K")]),
        "2026-06-30": ("10-Q", ACC[("2026-06-30", "10-Q")]),
    }
    entries = []
    for end, value in values.items():
        form, acc = spec[end]
        entries.append({"end": end, "val": value, "accn": acc, "form": form, "filed": FILED[acc], "fy": int(end[:4]), "fp": "Q2"})
    return tag, {"units": {unit: entries}}


def strong_company_facts() -> dict:
    """一家「什么都好」的公司：营收翻倍、毛利率扩张、RPO 大增、净现金、回购、股数下降。"""
    us: Dict[str, dict] = dict([
        _flow("Revenues", {"FY24": 400e6, "H124": 180e6, "FY25": 600e6, "H125": 280e6, "H126": 420e6}),
        _flow("GrossProfit", {"FY24": 160e6, "H124": 72e6, "FY25": 270e6, "H125": 126e6, "H126": 231e6}),      # 毛利率 40%→45%→55%
        _flow("OperatingIncomeLoss", {"FY24": 60e6, "H124": 25e6, "FY25": 130e6, "H125": 58e6, "H126": 120e6}),
        _flow("NetCashProvidedByUsedInOperatingActivities", {"FY24": 70e6, "H124": 30e6, "FY25": 140e6, "H125": 65e6, "H126": 125e6}),
        _flow("PaymentsToAcquirePropertyPlantAndEquipment", {"FY24": 15e6, "H124": 7e6, "FY25": 30e6, "H125": 13e6, "H126": 25e6}),
        _flow("PaymentsForRepurchaseOfCommonStock", {"FY24": 10e6, "H124": 5e6, "FY25": 30e6, "H125": 12e6, "H126": 25e6}),
        _flow("ShareBasedCompensation", {"FY24": 8e6, "H124": 4e6, "FY25": 10e6, "H125": 5e6, "H126": 7e6}),
        _flow("WeightedAverageNumberOfDilutedSharesOutstanding", {"FY24": 51e6, "H124": 51e6, "FY25": 50e6, "H125": 50.5e6, "H126": 49e6}, "shares"),
        _instant("RevenueRemainingPerformanceObligation", {"2025-06-30": 300e6, "2025-12-31": 420e6, "2026-06-30": 640e6}),
        _instant("CashAndCashEquivalentsAtCarryingValue", {"2025-06-30": 200e6, "2025-12-31": 260e6, "2026-06-30": 330e6}),
        _instant("LongTermDebt", {"2025-06-30": 40e6, "2025-12-31": 40e6, "2026-06-30": 30e6}),
        _instant("PropertyPlantAndEquipmentNet", {"2025-06-30": 90e6, "2025-12-31": 110e6, "2026-06-30": 130e6}),
        _instant("StockholdersEquity", {"2025-12-31": 500e6, "2026-06-30": 560e6}),
        _instant("AssetsCurrent", {"2026-06-30": 500e6}), _instant("LiabilitiesCurrent", {"2026-06-30": 150e6}),
    ])
    shares = dict([_instant("EntityCommonStockSharesOutstanding", {"2025-06-30": 50.5e6, "2026-06-30": 49e6}, "shares")])
    return {"facts": {"us-gaap": us, "dei": shares}}


def weak_company_facts(cash_burn: bool = True) -> dict:
    """营收下滑、毛利率下降、烧钱、稀释：捕获与融资门都过不了。"""
    us = dict([
        _flow("Revenues", {"FY24": 100e6, "H124": 50e6, "FY25": 90e6, "H125": 45e6, "H126": 35e6}),
        _flow("GrossProfit", {"FY24": 40e6, "H124": 20e6, "FY25": 30e6, "H125": 15e6, "H126": 9e6}),
        _flow("OperatingIncomeLoss", {"FY24": -20e6, "H124": -10e6, "FY25": -30e6, "H125": -14e6, "H126": -20e6}),
        _flow("NetCashProvidedByUsedInOperatingActivities", {"FY24": -20e6, "H124": -10e6, "FY25": -30e6, "H125": -14e6, "H126": -20e6}),
        _flow("PaymentsToAcquirePropertyPlantAndEquipment", {"FY24": 2e6, "H124": 1e6, "FY25": 2e6, "H125": 1e6, "H126": 1e6}),
        _flow("WeightedAverageNumberOfDilutedSharesOutstanding", {"FY24": 20e6, "H124": 20e6, "FY25": 25e6, "H125": 22e6, "H126": 30e6}, "shares"),
        _instant("CashAndCashEquivalentsAtCarryingValue", {"2025-06-30": 40e6, "2025-12-31": 30e6, "2026-06-30": 20e6}),
    ])
    shares = dict([_instant("EntityCommonStockSharesOutstanding", {"2025-06-30": 22e6, "2026-06-30": 30e6}, "shares")])
    return {"facts": {"us-gaap": us, "dei": shares}}


def submissions_payload(cik: int = CIK, state: str = "TX", extra: Optional[List[Tuple[str, str, str, str, str]]] = None) -> dict:
    rows = [(acc, form, filed, end, "doc%s.htm" % acc[-4:], "") for end, form, filed, acc in FILINGS]
    for item in extra or []:
        rows.append(item)
    return {
        "cik": str(cik), "name": "Synthetic Strong Corp", "sic": "3674", "sicDescription": "Semiconductors",
        "tickers": ["SYNS"], "exchanges": ["Nasdaq"], "addresses": {"business": {"stateOrCountry": state}},
        "filings": {"recent": {
            "accessionNumber": [r[0] for r in rows], "form": [r[1] for r in rows], "filingDate": [r[2] for r in rows],
            "reportDate": [r[3] for r in rows], "primaryDocument": [r[4] for r in rows], "items": [r[5] for r in rows]}},
    }


def build_store(facts: Optional[dict] = None, cik: int = CIK, drop_accessions: Tuple[str, ...] = (),
                submissions: Optional[dict] = None) -> FactStore:
    store = FactStore(":memory:")
    payload = facts or strong_company_facts()
    if drop_accessions:  # 模拟「这份申报当时还没发生」：从事实与申报清单里同时剔除
        payload = {"facts": {tax: {tag: {"units": {u: [e for e in entries if e["accn"] not in drop_accessions]
                                                     for u, entries in body["units"].items()}}
                                   for tag, body in tags.items()} for tax, tags in payload["facts"].items()}}
    store.ingest_companyfacts(cik, payload, "2026-09-15")
    sub = submissions or submissions_payload(cik)
    if drop_accessions:
        keep = [i for i, acc in enumerate(sub["filings"]["recent"]["accessionNumber"]) if acc not in drop_accessions]
        sub = {**sub, "filings": {"recent": {k: [v[i] for i in keep] for k, v in sub["filings"]["recent"].items()}}}
    store.ingest_submissions(cik, sub, "2026-09-15")
    return store


def flat_history(as_of: str, price: float = 20.0, days: int = 800) -> List[Tuple[str, float]]:
    end = date.fromisoformat(as_of)
    return [((end - timedelta(days=days - 1 - i)).isoformat(), price) for i in range(days)]


def market(as_of: str = "2026-09-15", cap: float = 1.0e9, price: float = 20.0, dollar_volume: float = 35e6,
           state: str = "TX", history: bool = True, cik: int = CIK, flags=()) -> MarketInput:
    shares = cap / price
    return MarketInput(
        symbol="SYNS", cik=cik, name="Synthetic Strong Corp", price=price, market_cap=cap, median_dollar_volume=dollar_volume,
        shares=shares, exchange="Nasdaq", state_of_business=state, sic="3674", flags=tuple(flags), sina_market_cap=cap,
        history=tuple(flat_history(as_of, price)) if history else (),
    )
