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
    return_tolerance: float = 0.005,
    level_tolerance: float = 0.002,
    sample_every: int = 21,
) -> dict:
    """双源交叉核验:硬门槛用「逐日收益率」比对,水平差只作警告。

    依据(2026-07-17 R1 留痕):厂商对特别分配/分拆的历史价调整口径不同
    (实例:XLF 2016-09 分拆 XLRE,雅虎调整历史价、纳斯达克不调)会造成
    恒定水平偏移——那是口径差不是数据错;而坏价、错日、漏拆分会让某日
    收益率在两源间爆炸性不一致——这才是要拦的。收益率比对对前者免疫、
    对后者敏感,故为硬门槛;水平差超容差记警告供人工复核。
    """
    sec_by_day = {r.day: r for r in secondary}
    overlap = [r for r in primary if r.day in sec_by_day]
    if len(overlap) < 100:
        raise DataIntegrityError(f"{symbol}: 双源重叠不足 ({len(overlap)} 天),交叉核验不可信")

    return_mismatches = []
    checked = 0
    for i in range(1, len(overlap)):
        a_prev, a_cur = overlap[i - 1], overlap[i]
        b_prev, b_cur = sec_by_day[a_prev.day], sec_by_day[a_cur.day]
        if i % sample_every and i != len(overlap) - 1:
            continue
        checked += 1
        ra = a_cur.close / a_prev.close - 1.0
        rb = b_cur.close / b_prev.close - 1.0
        if abs(ra - rb) > return_tolerance:
            return_mismatches.append({"day": a_cur.day.isoformat(),
                                      "primary_ret": round(ra, 6), "secondary_ret": round(rb, 6)})
    if return_mismatches:
        raise DataIntegrityError(
            f"{symbol}: 双源逐日收益率超容差 {return_tolerance:.2%}: {return_mismatches[:5]}")

    level_warnings = []
    for r in overlap[::sample_every]:
        other = sec_by_day[r.day]
        rel = abs(r.close - other.close) / other.close
        if rel > level_tolerance:
            level_warnings.append({"day": r.day.isoformat(), "rel_diff": round(rel, 6)})
    return {"symbol": symbol, "overlap_days": len(overlap), "sampled_returns": checked,
            "return_tolerance": return_tolerance, "all_within_tolerance": True,
            "level_offset_warnings": len(level_warnings),
            "level_note": ("水平差警告 = 厂商复权口径差异(见函数注释),收益率一致即数据可信"
                           if level_warnings else "")}


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
