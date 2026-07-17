"""免费日线数据源:Yahoo v8(主)+ Nasdaq 官方 API(交叉)+ FRED 指数(抽查)。

纪律:
- 不绕过任何反爬/验证码墙(stooq/WSJ 因此弃用,如实记录);
- 缓存落 data/backtest_cache/(gitignore),报告只存内容哈希与聚合;
- 交叉核验用未复权收盘价对比(复权口径差异不算数据错误);
- 完整性检查:日期严格递增、无非正价、无超长缺口;疑似拆分跳变仅标记不擅改。
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from backend.app.strategies.bars import Bar

CACHE_DIR = Path("data/backtest_cache")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


@dataclass(frozen=True)
class RawDay:
    day: date
    open: float
    high: float
    low: float
    close: float          # 未复权
    adj_close: Optional[float] = None


def _http_json(url: str, *, timeout: int = 30, retries: int = 3) -> dict:
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:  # 网络抖动重试;最终失败如实抛出
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise ConnectionError(f"抓取失败 {url}: {last}")


class YahooDailySource:
    name = "yahoo_v8"

    def fetch(self, symbol: str, start: date, end: date) -> list[RawDay]:
        p1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
        p2 = int(datetime(end.year, end.month, end.day, 23, 59, tzinfo=timezone.utc).timestamp())
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
               f"?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit")
        data = _http_json(url)
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        quote = result["indicators"]["quote"][0]
        adj = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
        out: list[RawDay] = []
        for i, t in enumerate(ts):
            o, h, l, c = quote["open"][i], quote["high"][i], quote["low"][i], quote["close"][i]
            if None in (o, h, l, c):
                continue  # 停牌/空洞跳过,完整性检查兜底
            out.append(RawDay(
                day=datetime.fromtimestamp(t, tz=timezone.utc).date(),
                open=float(o), high=float(h), low=float(l), close=float(c),
                adj_close=float(adj[i]) if adj and adj[i] is not None else None,
            ))
        return out


class NasdaqDailySource:
    name = "nasdaq_api"

    def fetch(self, symbol: str, start: date, end: date) -> list[RawDay]:
        url = (f"https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass=etf"
               f"&fromdate={start.isoformat()}&todate={end.isoformat()}&limit=9999")
        data = _http_json(url)
        rows = (data.get("data") or {}).get("tradesTable", {}).get("rows") or []
        out: list[RawDay] = []
        for r in rows:
            def num(s: str) -> float:
                return float(str(s).replace("$", "").replace(",", ""))
            m, d_, y = str(r["date"]).split("/")
            out.append(RawDay(
                day=date(int(y), int(m), int(d_)),
                open=num(r["open"]), high=num(r["high"]), low=num(r["low"]), close=num(r["close"]),
            ))
        out.sort(key=lambda x: x.day)
        return out


# ---------- 缓存 ----------

def cache_path(symbol: str, source: str) -> Path:
    return CACHE_DIR / f"{symbol}_{source}.json"


def save_cache(symbol: str, source: str, rows: Sequence[RawDay]) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = [
        {"day": r.day.isoformat(), "open": r.open, "high": r.high, "low": r.low,
         "close": r.close, "adj_close": r.adj_close}
        for r in rows
    ]
    text = json.dumps(payload, ensure_ascii=False)
    cache_path(symbol, source).write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def load_cache(symbol: str, source: str) -> Optional[list[RawDay]]:
    p = cache_path(symbol, source)
    if not p.exists():
        return None
    return [
        RawDay(day=date.fromisoformat(r["day"]), open=r["open"], high=r["high"],
               low=r["low"], close=r["close"], adj_close=r.get("adj_close"))
        for r in json.loads(p.read_text())
    ]


# ---------- 校验 ----------

class DataIntegrityError(Exception):
    pass


def integrity_check(symbol: str, rows: Sequence[RawDay], *, max_gap_days: int = 7) -> list[str]:
    """硬错误抛异常;疑似拆分跳变只标记(返回警告列表)。"""
    if len(rows) < 2:
        raise DataIntegrityError(f"{symbol}: 数据不足 ({len(rows)} 行)")
    warnings: list[str] = []
    prev = rows[0]
    for r in rows[1:]:
        if r.day <= prev.day:
            raise DataIntegrityError(f"{symbol}: 日期未严格递增 {prev.day} -> {r.day}")
        if (r.day - prev.day).days > max_gap_days:
            raise DataIntegrityError(f"{symbol}: 缺口过大 {prev.day} -> {r.day}")
        for v in (r.open, r.high, r.low, r.close):
            if v <= 0:
                raise DataIntegrityError(f"{symbol}: 非正价格 {r.day}")
        if r.low > r.high + 1e-9:
            raise DataIntegrityError(f"{symbol}: low>high {r.day}")
        move = abs(r.close / prev.close - 1.0)
        if move > 0.25:
            warnings.append(f"{symbol} {r.day}: 单日 |Δ|={move:.1%} 疑似拆分/极端行情,仅标记")
        prev = r
    return warnings


def cross_check(
    symbol: str,
    primary: Sequence[RawDay],
    secondary: Sequence[RawDay],
    *,
    tolerance: float = 0.002,
    sample_every: int = 21,
) -> dict:
    """未复权收盘价抽样比对:重叠区间每 21 个交易日抽一天 + 首尾必查。"""
    sec_by_day = {r.day: r for r in secondary}
    overlap = [r for r in primary if r.day in sec_by_day]
    if len(overlap) < 100:
        raise DataIntegrityError(f"{symbol}: 双源重叠不足 ({len(overlap)} 天),交叉核验不可信")
    picks = overlap[::sample_every]
    if overlap[0] not in picks:
        picks.insert(0, overlap[0])
    if overlap[-1] not in picks:
        picks.append(overlap[-1])
    mismatches = []
    for r in picks:
        other = sec_by_day[r.day]
        rel = abs(r.close - other.close) / other.close
        if rel > tolerance:
            mismatches.append({"day": r.day.isoformat(), "primary": r.close,
                               "secondary": other.close, "rel_diff": round(rel, 6)})
    if mismatches:
        raise DataIntegrityError(f"{symbol}: 双源收盘价超容差 {tolerance:.2%}: {mismatches[:5]}")
    return {"symbol": symbol, "overlap_days": len(overlap), "sampled": len(picks),
            "tolerance": tolerance, "all_within_tolerance": True}


def to_adjusted_bars(rows: Sequence[RawDay]) -> list[Bar]:
    """复权 OHLC:各日 O/H/L/C 乘 adj_close/close 系数(处理分红与拆分)。
    缺 adj_close 的行按 1.0 系数(如实=未复权),调用方在报告声明口径。"""
    bars: list[Bar] = []
    for r in rows:
        k = (r.adj_close / r.close) if r.adj_close else 1.0
        bars.append(Bar(day=r.day, open=r.open * k, high=r.high * k,
                        low=r.low * k, close=(r.adj_close if r.adj_close else r.close)))
    return bars


def fetch_verified(
    symbol: str,
    start: date,
    end: date,
    *,
    use_cache: bool = True,
    primary: Optional[YahooDailySource] = None,
    secondary: Optional[NasdaqDailySource] = None,
) -> tuple[list[Bar], dict]:
    """主源+交叉源验证后输出复权 Bar 序列与证据(哈希+核验结论)。"""
    p_src = primary or YahooDailySource()
    s_src = secondary or NasdaqDailySource()
    p_rows = load_cache(symbol, p_src.name) if use_cache else None
    s_rows = load_cache(symbol, s_src.name) if use_cache else None
    if p_rows is None:
        p_rows = p_src.fetch(symbol, start, end)
        p_hash = save_cache(symbol, p_src.name, p_rows)
    else:
        p_hash = hashlib.sha256(cache_path(symbol, p_src.name).read_bytes()).hexdigest()
    if s_rows is None:
        s_rows = s_src.fetch(symbol, start, end)
        s_hash = save_cache(symbol, s_src.name, s_rows)
    else:
        s_hash = hashlib.sha256(cache_path(symbol, s_src.name).read_bytes()).hexdigest()

    warnings = integrity_check(symbol, p_rows)
    check = cross_check(symbol, p_rows, s_rows)
    evidence = {
        "symbol": symbol,
        "primary": {"source": p_src.name, "rows": len(p_rows), "sha256": p_hash},
        "secondary": {"source": s_src.name, "rows": len(s_rows), "sha256": s_hash},
        "cross_check": check,
        "integrity_warnings": warnings,
    }
    return to_adjusted_bars(p_rows), evidence
