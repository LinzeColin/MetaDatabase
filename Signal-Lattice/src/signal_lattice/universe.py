"""候选池：美国上市中小市值普通股（本土申报人）。硬门写成常量，由 tests/test_universe.py 钉住。

流程：Nasdaq Trader 符号目录（剔除 ETF/测试股/优先股/权证/单位/ADS/SPAC）
→ 与 SEC company_tickers_exchange 取交集 → 新浪 gb_ 报价（价格）
→ 市值 = SEC 申报流通股 × 最新价；SEC 口径或新浪口径任一超过上限即剔除（宁可少，不混进大盘）
→ 只收美国本土申报人：近 18 个月内在 SEC 有 10-K 或 10-Q（submissions 核对），
  只报 20-F / 40-F / 6-K 的外国发行人剔除
→ 腾讯日线算近 20 日成交额中位数
→ 输出不可变快照 universe-<日期>-<内容hash>.json。
新浪市值不再只是交叉校验：超过上限直接剔除；与 SEC 口径差 >20% 仍标记。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from .evidence.sec_client import SecClient, SecFetchError, SecNotFound
from .marketdata.base import DiskCache, HttpClient, MarketDataError, decode_text
from .marketdata.models import Bar, Instrument
from .marketdata.sina import SINA_REFERER, _ASSIGNMENT, _parse_source_time
from .marketdata.tencent import TencentKlineProvider

# ---- 硬门（改这里必须同时改测试，测试会钉死这些数）-------------------------
MIN_MARKET_CAP_USD = 300_000_000
MAX_MARKET_CAP_USD = 5_000_000_000
MIN_PRICE_USD = 3.0
MIN_MEDIAN_DOLLAR_VOLUME_USD = 3_000_000
DOLLAR_VOLUME_WINDOW_DAYS = 20
CAP_CROSSCHECK_TOLERANCE = 0.20
# 输入有效性：SEC 流通股数的披露日不能太旧；日线最后一根不能太旧。
MAX_SHARES_AGE_DAYS = 400
MAX_BAR_AGE_DAYS = 7
# 只收美国本土申报人：近 18 个月内必须有 10-K / 10-Q（含过渡期报告）；只报下列外国发行人表格的剔除。
DOMESTIC_FILER_LOOKBACK_MONTHS = 18
DOMESTIC_PERIODIC_FORMS = ("10-K", "10-KT", "10-Q", "10-QT")
FOREIGN_ISSUER_FORMS = ("20-F", "40-F", "6-K")

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_QUOTE_BATCH = 300
TENCENT_KLINE_ENDPOINT = (
    "https://web.ifzq.gtimg.cn/appstock/app/{kind}/get?param={symbol},day,,,%d,qfq" % 30
)
SHARES_CONCEPT = ("dei", "EntityCommonStockSharesOutstanding", "shares")
# 多类别股票（Class A/B）的封面流通股按类别分开申报，frames 里没有无维度总数。
# 这类公司退而用资产负债表的 us-gaap 流通股，且必须被新浪市值在 20% 内印证才入选。
FALLBACK_SHARES_CONCEPT = ("us-gaap", "CommonStockSharesOutstanding", "shares")
NEW_YORK = ZoneInfo("America/New_York")

EXCHANGE_FROM_OTHER_CODE = {"N": "NYSE", "A": "NYSE American"}
TENCENT_SUFFIX = {"Nasdaq": "OQ", "NYSE": "N", "NYSE American": "AM"}
SEC_EXCHANGE_LABELS = {"Nasdaq", "NYSE"}  # SEC 把 NYSE American 也标成 NYSE 或 None，交集只看代码，不看这列

CAP_BUCKETS = (
    (300_000_000, 500_000_000, "$0.3-0.5B"),
    (500_000_000, 1_000_000_000, "$0.5-1B"),
    (1_000_000_000, 2_000_000_000, "$1-2B"),
    (2_000_000_000, 5_000_000_000, "$2-5B"),
)

# 证券名称里出现这些词的不是普通股（优先股/权证/权利/单位/存托凭证/票据/基金/SPAC）。
_NAME_EXCLUSIONS = (
    ("PREFERRED", re.compile(r"\bpreferred\b|\bpreference\b", re.I)),
    ("UNIT", re.compile(r"\bunits?\b", re.I)),
    ("WARRANT", re.compile(r"\bwarrants?\b", re.I)),
    ("RIGHT", re.compile(r"\brights?\b", re.I)),
    ("DEPOSITARY", re.compile(r"depositary|\bADS\b|\bADR\b", re.I)),
    ("DEBT", re.compile(r"\bnotes?\b|debentures?|subordinated|\bbonds?\b|\bdue \d{4}\b", re.I)),
    ("FUND", re.compile(r"\bfund\b|\betf\b|\bportfolio\b|closed.end", re.I)),
    ("SPAC", re.compile(r"\bacquisition\b(\s+[IVX\d]+)?\s+(corp|corporation|co|holdings|company|ltd|limited|inc)\b|blank check", re.I)),
)
_BAD_SYMBOL_CHARS = re.compile(r"[$.\-+=^/ ]")


@dataclass(frozen=True)
class Listing:
    symbol: str
    name: str
    exchange: str  # Nasdaq | NYSE | NYSE American


@dataclass(frozen=True)
class DirectoryResult:
    listings: List[Listing]
    etf_symbols: frozenset
    excluded: Counter
    file_times: Dict[str, str]


@dataclass(frozen=True)
class SharesRecord:
    cik: int
    shares: float
    end: str
    accession: str
    concept: str = "dei:EntityCommonStockSharesOutstanding"

    @property
    def is_primary(self) -> bool:
        return self.concept.startswith("dei:")


@dataclass(frozen=True)
class SinaQuote:
    symbol: str
    price: float
    market_cap: Optional[float]
    shares: Optional[float]
    source_time: Optional[datetime]


@dataclass(frozen=True)
class FilingProfile:
    """来自 SEC submissions：本土申报人判定所需的最少事实，以及登记地与行业码。"""
    domestic_form: Optional[str]        # 回看期内最近一份 10-K/10-KT/10-Q/10-QT 的表格类型
    domestic_filed: Optional[str]
    domestic_accession: Optional[str]
    foreign_form_latest: Optional[str]  # 回看期内最近一份 20-F/40-F/6-K
    foreign_form_filed: Optional[str]
    state_of_business: Optional[str]    # 主要营业地址的州/国家代码（如 CA、TX、F4=中国）
    sic: Optional[str]
    sic_description: Optional[str]


def months_before(day: date, months: int) -> date:
    year, month = day.year, day.month - months
    while month <= 0:
        month += 12
        year -= 1
    last_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(day.day, last_day))


def filing_profile(payload: Mapping, today: date) -> FilingProfile:
    """submissions 的 recent 列表 → 本土申报人证据。只看 filed <= today 且在回看期内的申报。"""
    recent = (payload.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    filed_dates = recent.get("filingDate") or []
    accessions = recent.get("accessionNumber") or []
    cutoff = months_before(today, DOMESTIC_FILER_LOOKBACK_MONTHS).isoformat()
    today_iso = today.isoformat()
    best_domestic = None
    best_foreign = None
    for index, form in enumerate(forms):
        filed = filed_dates[index] if index < len(filed_dates) else None
        if not filed or not (cutoff <= filed <= today_iso):
            continue
        accession = accessions[index] if index < len(accessions) else None
        if form in DOMESTIC_PERIODIC_FORMS and (best_domestic is None or filed > best_domestic[1]):
            best_domestic = (form, filed, accession)
        if form in FOREIGN_ISSUER_FORMS and (best_foreign is None or filed > best_foreign[1]):
            best_foreign = (form, filed)
    business = ((payload.get("addresses") or {}).get("business") or {})
    return FilingProfile(
        domestic_form=best_domestic[0] if best_domestic else None,
        domestic_filed=best_domestic[1] if best_domestic else None,
        domestic_accession=best_domestic[2] if best_domestic else None,
        foreign_form_latest=best_foreign[0] if best_foreign else None,
        foreign_form_filed=best_foreign[1] if best_foreign else None,
        state_of_business=business.get("stateOrCountry") or None,
        sic=str(payload.get("sic")) if payload.get("sic") else None,
        sic_description=payload.get("sicDescription") or None,
    )


def domestic_filer_reason(profile: Optional[FilingProfile]) -> Optional[str]:
    """None 表示是本土申报人；否则返回剔除原因。宁可少：查不到 submissions 也剔除。"""
    if profile is None:
        return "NO_SUBMISSIONS"
    if profile.domestic_form is None:
        return "FOREIGN_ISSUER_FORMS_ONLY" if profile.foreign_form_latest else "NO_10K_10Q_IN_18_MONTHS"
    if profile.foreign_form_filed and profile.foreign_form_filed > (profile.domestic_filed or ""):
        return "SWITCHED_TO_FOREIGN_FORMS"  # 最近一份定期报告已是 20-F/40-F/6-K，不再按本土申报人处理
    return None


# ---- 符号目录 ---------------------------------------------------------------
def name_exclusion_reason(name: str) -> Optional[str]:
    for reason, pattern in _NAME_EXCLUSIONS:
        if pattern.search(name):
            return reason
    return None


def parse_symbol_directories(nasdaq_text: str, other_text: str) -> DirectoryResult:
    excluded: Counter = Counter()
    etfs: set = set()
    listings: List[Listing] = []
    file_times: Dict[str, str] = {}

    def rows(text: str, label: str):
        lines = [line for line in text.splitlines() if line.strip()]
        header = lines[0].split("|")
        for line in lines[1:]:
            if line.startswith("File Creation Time"):
                file_times[label] = line.split(":", 1)[1].split("|")[0].strip()
                continue
            values = line.split("|")
            if len(values) >= len(header):
                yield dict(zip(header, values))

    def consider(symbol: str, name: str, exchange: Optional[str], is_etf: bool, is_test: bool) -> None:
        if is_etf:
            etfs.add(symbol)
            excluded["ETF"] += 1
        elif is_test:
            excluded["TEST_ISSUE"] += 1
        elif exchange is None:
            excluded["EXCHANGE_NOT_NYSE_NASDAQ_AMEX"] += 1
        elif _BAD_SYMBOL_CHARS.search(symbol):
            excluded["SYMBOL_SUFFIX"] += 1  # 优先股/权证/单位/类别股后缀（新浪 gb_ 也不覆盖这类代码）
        else:
            reason = name_exclusion_reason(name)
            if reason:
                excluded[reason] += 1
            else:
                listings.append(Listing(symbol.upper(), name.strip(), exchange))

    for row in rows(nasdaq_text, "nasdaqlisted"):
        consider(row["Symbol"], row["Security Name"], "Nasdaq", row.get("ETF") == "Y" or row.get("NextShares") == "Y",
                 row.get("Test Issue") == "Y")
    for row in rows(other_text, "otherlisted"):
        consider(row["ACT Symbol"], row["Security Name"], EXCHANGE_FROM_OTHER_CODE.get(row.get("Exchange")),
                 row.get("ETF") == "Y", row.get("Test Issue") == "Y")
    return DirectoryResult(listings, frozenset(etfs), excluded, file_times)


def fetch_directories(client: HttpClient) -> DirectoryResult:
    nasdaq = decode_text(client.get(NASDAQ_LISTED_URL, provider="nasdaqtrader"), "utf-8", "NASDAQ_DIRECTORY")
    other = decode_text(client.get(OTHER_LISTED_URL, provider="nasdaqtrader"), "utf-8", "NASDAQ_DIRECTORY")
    return parse_symbol_directories(nasdaq, other)


# ---- SEC 流通股 -------------------------------------------------------------
def recent_instant_periods(today: date, quarters: int = 5) -> List[str]:
    year, quarter = today.year, (today.month - 1) // 3 + 1
    periods = []
    for _ in range(quarters):
        periods.append("CY%dQ%dI" % (year, quarter))
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
    return periods


def _latest_by_cik(client: SecClient, today: date, spec: tuple, used: List[str]) -> Dict[int, SharesRecord]:
    taxonomy, concept, unit = spec
    best: Dict[int, SharesRecord] = {}
    for period in recent_instant_periods(today):
        try:
            frame = client.frames(taxonomy, concept, unit, period)
        except SecNotFound:
            continue
        used.append("%s:%s:%s" % (taxonomy, concept, period))
        for item in frame.get("data", []):
            try:
                record = SharesRecord(int(item["cik"]), float(item["val"]), item["end"], item["accn"],
                                      "%s:%s" % (taxonomy, concept))
            except (KeyError, TypeError, ValueError):
                continue
            if record.shares > 0 and (record.cik not in best or record.end > best[record.cik].end):
                best[record.cik] = record
    return best


def fetch_sec_shares(client: SecClient, today: date) -> tuple[Dict[int, SharesRecord], List[str]]:
    """frames 一次取全市场流通股；每家取披露日最新的一条。封面数缺失的才用资产负债表数兜底。"""
    used: List[str] = []
    merged = _latest_by_cik(client, today, FALLBACK_SHARES_CONCEPT, used)
    merged.update(_latest_by_cik(client, today, SHARES_CONCEPT, used))  # 封面数优先
    return merged, used


# ---- 新浪报价 ---------------------------------------------------------------
def parse_sina_quotes(payload: bytes) -> Dict[str, SinaQuote]:
    """gb_ 字段：1 现价，10 成交量，12 市值，19 总股本。只取用得上的，缺失写 None。"""
    text = decode_text(payload, "gbk", "SINA_GBK")
    result: Dict[str, SinaQuote] = {}

    def number(parts: List[str], index: int) -> Optional[float]:
        try:
            value = float(parts[index])
        except (IndexError, ValueError):
            return None
        return value if math.isfinite(value) and value > 0 else None

    for source_symbol, raw in _ASSIGNMENT.findall(text):
        if not source_symbol.startswith("gb_") or not raw.strip():
            continue
        parts = [part.strip() for part in raw.split(",")]
        price = number(parts, 1)
        if price is None:
            continue
        symbol = source_symbol[3:].upper()
        result[symbol] = SinaQuote(symbol, price, number(parts, 12), number(parts, 19), _parse_source_time(raw))
    return result


def fetch_sina_quotes(client: HttpClient, symbols: Sequence[str]) -> Dict[str, SinaQuote]:
    quotes: Dict[str, SinaQuote] = {}
    for start in range(0, len(symbols), SINA_QUOTE_BATCH):
        batch = symbols[start:start + SINA_QUOTE_BATCH]
        url = SINA_QUOTE_URL + ",".join("gb_" + symbol.lower() for symbol in batch)
        quotes.update(parse_sina_quotes(client.get(url, {"Referer": SINA_REFERER}, provider="sina_quote")))
    return quotes


# ---- 日线 -------------------------------------------------------------------
def completed_bars(bars: Sequence[Bar], now: datetime) -> List[Bar]:
    """去掉还没收完的当日 Bar：纽约时间 16:00 前，当天那根是盘中残量。"""
    local = now.astimezone(NEW_YORK)
    if local.hour < 16:
        return [bar for bar in bars if bar.day < local.date()]
    return list(bars)


def median_dollar_volume(bars: Sequence[Bar], window: int = DOLLAR_VOLUME_WINDOW_DAYS) -> Optional[float]:
    tail = list(bars)[-window:]
    if len(tail) < window or any(bar.volume is None for bar in tail):
        return None
    return statistics.median(bar.close * bar.volume for bar in tail)


def make_bar_fetcher(cache_dir: Path, client: Optional[HttpClient] = None) -> Callable[[Listing], List[Bar]]:
    provider = TencentKlineProvider(client or HttpClient(timeout_seconds=15.0, attempts=3),
                                    DiskCache(Path(cache_dir)), endpoint=TENCENT_KLINE_ENDPOINT)

    def fetch(listing: Listing) -> List[Bar]:
        instrument = Instrument(
            symbol="us" + listing.symbol, name=listing.name, market="US", asset_type="STOCK",
            timezone="America/New_York", sina_symbol="gb_" + listing.symbol.lower(), tencent_symbol=None,
            tencent_kline_symbol="us%s.%s" % (listing.symbol, TENCENT_SUFFIX[listing.exchange]),
            eastmoney_fund_code=None, benchmark=None,
        )
        return provider.fetch(instrument)

    return fetch


# ---- 选股 -------------------------------------------------------------------
def market_cap_usd(shares: float, price: float) -> float:
    return shares * price


def cap_bucket(cap: float) -> str:
    for low, high, label in CAP_BUCKETS:
        if low <= cap <= high:
            return label
    return "OUT_OF_RANGE"


def select_universe(
    listings: Sequence[Listing],
    sec_ciks: Mapping[str, dict],
    shares_by_cik: Mapping[int, SharesRecord],
    quotes: Mapping[str, SinaQuote],
    fetch_bars: Callable[[Listing], Sequence[Bar]],
    now: datetime,
    profile_for: Callable[[int], Optional[FilingProfile]],
    workers: int = 8,
) -> tuple[List[dict], Counter]:
    """纯逻辑：输入都由调用方给，便于测试。返回 (入选条目, 各关淘汰计数)。

    profile_for(cik) 给出 SEC submissions 派生的申报画像（查不到返回 None，按剔除处理）；
    它是必填项，没有任何路径可以绕过「只收本土申报人」这一关。"""
    funnel: Counter = Counter()
    today = now.astimezone(NEW_YORK).date()
    pre_stage: List[tuple] = []
    stage: List[tuple] = []
    for listing in listings:
        sec = sec_ciks.get(listing.symbol)
        if sec is None:
            funnel["NOT_IN_SEC_TICKERS"] += 1
            continue
        funnel["in_sec"] += 1
        quote = quotes.get(listing.symbol)
        if quote is None:
            funnel["NO_SINA_QUOTE"] += 1
            continue
        if quote.price < MIN_PRICE_USD:
            funnel["PRICE_BELOW_MIN"] += 1
            continue
        shares = shares_by_cik.get(int(sec["cik"]))
        if shares is None:
            funnel["NO_SEC_SHARES"] += 1
            continue
        if (today - date.fromisoformat(shares.end)).days > MAX_SHARES_AGE_DAYS:
            funnel["SEC_SHARES_STALE"] += 1
            continue
        cap = market_cap_usd(shares.shares, quote.price)
        if not shares.is_primary and (
            quote.market_cap is None or abs(quote.market_cap - cap) / cap > CAP_CROSSCHECK_TOLERANCE
        ):
            funnel["SHARES_FALLBACK_UNCONFIRMED"] += 1
            continue
        if cap < MIN_MARKET_CAP_USD:
            funnel["CAP_BELOW_MIN"] += 1
            continue
        if cap > MAX_MARKET_CAP_USD:
            funnel["CAP_ABOVE_MAX"] += 1
            continue
        if quote.market_cap is not None and quote.market_cap > MAX_MARKET_CAP_USD:
            funnel["SINA_CAP_ABOVE_MAX"] += 1  # 两个口径任一超上限就剔除，宁可少
            continue
        pre_stage.append((listing, sec, quote, shares, cap))
    funnel["need_filing_profile"] = len(pre_stage)

    # submissions 每家一次请求：并发取（SecClient 内有进程级限速，总速率仍 ≤5 次/秒）。
    with ThreadPoolExecutor(max_workers=workers) as pool:
        profiles = list(pool.map(lambda item: profile_for(int(item[1]["cik"])), pre_stage))
    for item, profile in zip(pre_stage, profiles):
        reason = domestic_filer_reason(profile)
        if reason:
            funnel["NOT_DOMESTIC_FILER"] += 1
            funnel["not_domestic_" + reason] += 1
            continue
        stage.append(item + (profile,))
    funnel["need_bars"] = len(stage)

    def load(item):
        try:
            return list(fetch_bars(item[0]))
        except MarketDataError:
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        all_bars = list(pool.map(load, stage))

    entries: List[dict] = []
    for (listing, sec, quote, shares, cap, profile), bars in zip(stage, all_bars):
        if bars is None:
            funnel["NO_BARS"] += 1
            continue
        bars = completed_bars(bars, now)
        median = median_dollar_volume(bars)
        if median is None:
            funnel["BARS_INSUFFICIENT"] += 1
            continue
        if (today - bars[-1].day).days > MAX_BAR_AGE_DAYS:
            funnel["BARS_STALE"] += 1
            continue
        if median < MIN_MEDIAN_DOLLAR_VOLUME_USD:
            funnel["DOLLAR_VOLUME_BELOW_MIN"] += 1
            continue
        flags: List[str] = []
        if quote.market_cap is not None and abs(quote.market_cap - cap) / cap > CAP_CROSSCHECK_TOLERANCE:
            flags.append("SINA_CAP_MISMATCH")
        if abs(quote.price - bars[-1].close) / bars[-1].close > CAP_CROSSCHECK_TOLERANCE:
            flags.append("PRICE_VS_LAST_CLOSE_MISMATCH")
        entries.append({
            "symbol": listing.symbol,
            "cik": int(sec["cik"]),
            "name": sec["name"],
            "exchange": listing.exchange,
            "price_usd": quote.price,
            "price_source": "sina_gb",
            "price_source_time": quote.source_time.isoformat() if quote.source_time else None,
            "shares_outstanding": shares.shares,
            "shares_as_of": shares.end,
            "shares_accession": shares.accession,
            "shares_concept": shares.concept,
            "market_cap_usd": round(cap, 2),
            "sina_market_cap_usd": quote.market_cap,
            "median_dollar_volume_20d_usd": round(median, 2),
            "last_bar_day": bars[-1].day.isoformat(),
            "last_bar_close_usd": bars[-1].close,
            "bars_source": "tencent_fqkline",
            "domestic_form": profile.domestic_form,
            "domestic_filed": profile.domestic_filed,
            "domestic_accession": profile.domestic_accession,
            "state_of_business": profile.state_of_business,
            "sic": profile.sic,
            "sic_description": profile.sic_description,
            "flags": flags,
        })
    entries.sort(key=lambda entry: entry["symbol"])
    funnel["final"] = len(entries)
    return entries, funnel


# ---- 快照与验收 -------------------------------------------------------------
RULES = {
    "min_market_cap_usd": MIN_MARKET_CAP_USD,
    "max_market_cap_usd": MAX_MARKET_CAP_USD,
    "min_price_usd": MIN_PRICE_USD,
    "min_median_dollar_volume_20d_usd": MIN_MEDIAN_DOLLAR_VOLUME_USD,
    "dollar_volume_window_days": DOLLAR_VOLUME_WINDOW_DAYS,
    "cap_crosscheck_tolerance": CAP_CROSSCHECK_TOLERANCE,
    "domestic_filer_lookback_months": DOMESTIC_FILER_LOOKBACK_MONTHS,
    "domestic_periodic_forms": list(DOMESTIC_PERIODIC_FORMS),
    "foreign_issuer_forms": list(FOREIGN_ISSUER_FORMS),
}


def canonical_hash(body: dict) -> str:
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_snapshot(entries: List[dict], funnel: Counter, meta: dict, generated_at: datetime) -> dict:
    as_of = max((entry["last_bar_day"] for entry in entries), default=generated_at.date().isoformat())
    body = {
        "schema": "signal-lattice-universe/1",
        "as_of_date": as_of,
        "rules": RULES,
        "sources": meta,
        "funnel": dict(sorted(funnel.items())),
        "count": len(entries),
        "entries": entries,
    }
    digest = canonical_hash(body)
    return {**body, "content_sha256": digest, "generated_at": generated_at.isoformat()}


def write_snapshot(snapshot: dict, out_dir: Path) -> Path:
    """不可变：文件名含内容 hash，已存在则校验内容一致，绝不覆盖。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("universe-%s-%s.json" % (snapshot["as_of_date"], snapshot["content_sha256"][:12]))
    text = json.dumps(snapshot, ensure_ascii=False, indent=1, sort_keys=True)
    try:
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        existing = json.loads(path.read_text("utf-8"))
        if existing.get("content_sha256") != snapshot["content_sha256"]:
            raise
    return path


def _snapshot_today(snapshot: dict) -> date:
    stamp = snapshot.get("generated_at")
    if stamp:
        return datetime.fromisoformat(stamp).astimezone(NEW_YORK).date()
    return date.fromisoformat(snapshot["as_of_date"])


def verify_snapshot(snapshot: dict, etf_symbols: Iterable[str] = ()) -> dict:
    """读取端重算：不信快照里的派生值，按 SEC 流通股 × 价格重新核门槛，并按存下的申报证据重核本土申报人。"""
    etfs = set(etf_symbols)
    etf_count = mega_count = below_count = low_price = low_liquidity = 0
    foreign_count = 0
    buckets: Counter = Counter()
    cutoff = months_before(_snapshot_today(snapshot), DOMESTIC_FILER_LOOKBACK_MONTHS).isoformat()
    for entry in snapshot["entries"]:
        cap = market_cap_usd(entry["shares_outstanding"], entry["price_usd"])
        etf_count += entry["symbol"] in etfs
        mega_count += cap > MAX_MARKET_CAP_USD
        below_count += cap < MIN_MARKET_CAP_USD
        low_price += entry["price_usd"] < MIN_PRICE_USD
        low_liquidity += entry["median_dollar_volume_20d_usd"] < MIN_MEDIAN_DOLLAR_VOLUME_USD
        # 本土申报人证据缺失、表格不是 10-K/10-Q、或申报日早于 18 个月回看线，都算外国发行人/不合格。
        foreign_count += not (
            entry.get("domestic_form") in DOMESTIC_PERIODIC_FORMS
            and entry.get("domestic_filed")
            and entry["domestic_filed"] >= cutoff
            and entry.get("domestic_accession")
        )
        buckets[cap_bucket(cap)] += 1
    return {
        "total": len(snapshot["entries"]),
        "etf_count": etf_count,
        "mega_cap_count": mega_count,
        "below_min_cap_count": below_count,
        "below_min_price_count": low_price,
        "below_min_liquidity_count": low_liquidity,
        "foreign_issuer_count": foreign_count,
        "buckets": {label: buckets.get(label, 0) for _, _, label in CAP_BUCKETS},
        "flagged_sina_cap_mismatch": sum("SINA_CAP_MISMATCH" in e["flags"] for e in snapshot["entries"]),
        "sina_cap_above_max": sum((e["sina_market_cap_usd"] or 0) > MAX_MARKET_CAP_USD for e in snapshot["entries"]),
    }


def build(out_dir: Path, cache_dir: Path, now: Optional[datetime] = None, limit: Optional[int] = None,
          log: Callable[[str], None] = print, store=None) -> tuple[Path, dict, dict]:
    now = now or datetime.now(timezone.utc)
    http = HttpClient(timeout_seconds=20.0, attempts=3)
    sec = SecClient(Path(cache_dir) / "sec")
    directory = fetch_directories(http)
    if limit:
        directory = DirectoryResult(directory.listings[:limit], directory.etf_symbols, directory.excluded, directory.file_times)
    log("symbol directory: %d common-stock candidates, %d ETFs excluded" % (
        len(directory.listings), directory.excluded["ETF"]))
    sec_ciks: Dict[str, dict] = {}
    for row in sec.company_tickers_exchange():
        sec_ciks.setdefault((row["ticker"] or "").upper(), row)
    shares, periods = fetch_sec_shares(sec, now.astimezone(NEW_YORK).date())
    log("SEC tickers %d, shares records %d (frames %s), SEC requests so far %d" % (
        len(sec_ciks), len(shares), ",".join(periods), sec.requests_sent))
    quotes = fetch_sina_quotes(http, [listing.symbol for listing in directory.listings if listing.symbol in sec_ciks])
    log("sina quotes: %d" % len(quotes))
    today = now.astimezone(NEW_YORK).date()
    submissions_payloads: Dict[int, dict] = {}

    def profile_for(cik: int) -> Optional[FilingProfile]:
        try:
            payload = sec.submissions(cik)
        except SecFetchError:
            return None
        submissions_payloads[cik] = payload
        return filing_profile(payload, today)

    entries, funnel = select_universe(
        directory.listings, sec_ciks, shares, quotes, make_bar_fetcher(Path(cache_dir) / "bars"), now, profile_for)
    if store is not None:  # 候选池核对过的 submissions 顺手入事实库，分支打分不必再请求一遍
        for entry in entries:
            payload = submissions_payloads.get(entry["cik"])
            if payload is not None:
                store.ingest_submissions(entry["cik"], payload, today)
        log("submissions ingested into fact store: %d" % len(entries))
    for reason, count in directory.excluded.items():
        funnel["directory_excluded_" + reason] = count
    meta = {
        "symbol_directory": {"urls": [NASDAQ_LISTED_URL, OTHER_LISTED_URL], "file_creation_time": directory.file_times},
        "sec_tickers": "https://www.sec.gov/files/company_tickers_exchange.json",
        "sec_shares": {"concepts": ["dei:EntityCommonStockSharesOutstanding", "us-gaap:CommonStockSharesOutstanding(兜底，须新浪市值印证)"], "frames": periods},
        "quotes": SINA_QUOTE_URL,
        "daily_bars": "https://web.ifzq.gtimg.cn/appstock/app/usfqkline/get",
        "run_at_utc": now.isoformat(),
        "sec_requests": sec.requests_sent,
    }
    snapshot = build_snapshot(entries, funnel, meta, now)
    path = write_snapshot(snapshot, out_dir)
    return path, snapshot, verify_snapshot(snapshot, directory.etf_symbols)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="生成美股中小盘（本土申报人）候选池快照")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=None, help="只处理目录前 N 只（调试用）")
    parser.add_argument("--fact-store", type=Path, default=None, help="把核对过的 submissions 入这个 SQLite 事实库")
    args = parser.parse_args(argv)
    store = None
    if args.fact_store is not None:
        from .evidence.factstore import FactStore
        store = FactStore(args.fact_store)
    path, snapshot, report = build(args.out_dir, args.cache_dir, limit=args.limit, store=store)
    print("snapshot:", path)
    print("funnel:", json.dumps(snapshot["funnel"], ensure_ascii=False, sort_keys=True))
    print("market-cap buckets:", json.dumps(report["buckets"], ensure_ascii=False))
    print("total:", report["total"])
    print("ETF count:", report["etf_count"])
    print("above $5B (SEC-basis) count:", report["mega_cap_count"],
          "| sina-basis above $5B:", report["sina_cap_above_max"])
    print("foreign-issuer / non-domestic-filer count:", report["foreign_issuer_count"])
    print("below $0.3B / below $3 / below $3M-liquidity:", report["below_min_cap_count"],
          report["below_min_price_count"], report["below_min_liquidity_count"])
    print("flagged SINA_CAP_MISMATCH:", report["flagged_sina_cap_mismatch"])
    hard = report["etf_count"] + report["mega_cap_count"] + report["sina_cap_above_max"] \
        + report["foreign_issuer_count"] + report["below_min_cap_count"] \
        + report["below_min_price_count"] + report["below_min_liquidity_count"]
    return 0 if hard == 0 and report["total"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
