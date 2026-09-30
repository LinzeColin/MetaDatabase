"""免费、允许自动访问的公开数据源（只读、限速、带重试）。

来源与许可依据（2026-09-30 逐个核对过 robots.txt）：
- 基金净值：fund.eastmoney.com（robots 只禁 spm/aladin 参数）、api.fund.eastmoney.com（无 robots，无限制声明）。
- 上证综指：上交所官网行情接口 yunhq.sse.com.cn（官方源，无 robots 限制）。
- 标普 500：FRED（美联储圣路易斯分行）公开 CSV 下载；Yahoo / Stooq 的 robots 禁止自动访问，不用。
任何一个源失败都如实上报，绝不拿旧数据冒充当次抓取结果。
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

USER_AGENT = "Mozilla/5.0 (compatible; SerenityDailyAnalysis/1.0; research; +https://serenity.linzezhang.com)"
CST = ZoneInfo("Asia/Shanghai")

PINGZHONG_URL = "https://fund.eastmoney.com/pingzhongdata/{code}.js"
LSJZ_URL = "https://api.fund.eastmoney.com/f10/lsjz"
SSE_KLINE_URL = "https://yunhq.sse.com.cn:32042/v1/sh1/dayk/000001"
FRED_SP500_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

SOURCE_NAV_FULL = "Eastmoney/Tiantian Fund pingzhongdata NAV history"
SOURCE_NAV_INCREMENTAL = "Eastmoney/Tiantian Fund historical NAV API"
SOURCE_SSE = "SSE official index daily K (yunhq.sse.com.cn)"
SOURCE_FRED = "FRED SP500 (Federal Reserve Bank of St. Louis)"


class SourceError(RuntimeError):
    """数据源抓取或解析失败。"""


@dataclass(frozen=True)
class NavPoint:
    date: date
    close: float


@dataclass(frozen=True)
class FundStatus:
    latest_date: date | None
    subscription: str | None  # open / limited / closed / None(未识别)
    redemption: str | None
    subscription_text: str
    redemption_text: str


class HttpClient:
    """同步 HTTP 客户端：同主机最小间隔、指数退避重试。opener 可注入，便于离线测试。"""

    def __init__(
        self,
        *,
        timeout: float = 25.0,
        retries: int = 3,
        backoff: float = 2.0,
        min_interval: float = 0.4,
        opener=urlopen,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> None:
        self.timeout = timeout
        self.retries = max(1, retries)
        self.backoff = backoff
        self.min_interval = min_interval
        self._opener = opener
        self._sleep = sleep
        self._clock = clock
        self._last_hit: dict[str, float] = {}
        self.request_count = 0

    def get(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        host = urlparse(url).netloc
        merged = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        merged.update(headers or {})
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            wait = self.min_interval - (self._clock() - self._last_hit.get(host, -1e9))
            if wait > 0:
                self._sleep(wait)
            self._last_hit[host] = self._clock()
            self.request_count += 1
            try:
                with self._opener(Request(url, headers=merged), timeout=self.timeout) as response:  # noqa: S310 - 固定的公开只读端点
                    return response.read()
            except HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break  # 4xx（限流除外）重试没有意义
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
            if attempt < self.retries:
                self._sleep(self.backoff * attempt)
        raise SourceError(f"{host} 请求失败：{last_error.__class__.__name__}: {last_error}")


def _cst_date(epoch_ms: float) -> date:
    return datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc).astimezone(CST).date()


def parse_pingzhong(text: str) -> tuple[str, list[NavPoint]]:
    match = re.search(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\])\s*;", text, flags=re.S)
    if not match:
        raise SourceError("pingzhongdata 缺少 Data_netWorthTrend")
    try:
        raw = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SourceError(f"pingzhongdata 净值序列不是合法 JSON：{exc}") from exc
    by_date: dict[date, float] = {}
    for item in raw:
        y = item.get("y")
        x = item.get("x")
        if x is None or y in (None, ""):
            continue
        by_date[_cst_date(float(x))] = float(y)
    name_match = re.search(r'var\s+fS_name\s*=\s*"(.*?)"', text)
    points = [NavPoint(day, by_date[day]) for day in sorted(by_date)]
    if not points:
        raise SourceError("pingzhongdata 净值序列为空")
    return (name_match.group(1) if name_match else ""), points


def fetch_fund_nav_full(client: HttpClient, code: str, *, keep_days: int = 1100, today: date | None = None) -> list[NavPoint]:
    body = client.get(PINGZHONG_URL.format(code=code), {"Referer": "https://fund.eastmoney.com/"}).decode("utf-8", errors="ignore")
    _, points = parse_pingzhong(body)
    cutoff = (today or datetime.now(CST).date()) - timedelta(days=keep_days)
    return [point for point in points if point.date >= cutoff]


def _map_status(text: str, kind: str) -> str | None:
    value = (text or "").strip()
    if not value:
        return None
    if kind == "subscription":
        if "暂停" in value or "封闭" in value or "不开放" in value:
            return "closed"
        if "限" in value:
            return "limited"
        if "开放" in value:
            return "open"
    else:
        if "暂停" in value or "封闭" in value or "不开放" in value:
            return "closed"
        if "限" in value:
            return "limited"
        if "开放" in value:
            return "open"
    return None


def _lsjz(client: HttpClient, code: str, *, page_size: int, start: date | None, end: date | None) -> list[dict[str, str]]:
    params: dict[str, str | int] = {"fundCode": code, "pageIndex": 1, "pageSize": page_size}
    if start:
        params["startDate"] = start.isoformat()
    if end:
        params["endDate"] = end.isoformat()
    body = client.get(f"{LSJZ_URL}?{urlencode(params)}", {"Referer": "https://fundf10.eastmoney.com/", "Accept": "application/json,*/*"})
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError(f"lsjz 返回不是合法 JSON：{exc}") from exc
    if int(payload.get("ErrCode") or 0) != 0:
        raise SourceError(f"lsjz 报错：{payload.get('ErrMsg')}")
    return list((payload.get("Data") or {}).get("LSJZList") or [])


def fetch_fund_nav_incremental(client: HttpClient, code: str, start: date, end: date) -> list[NavPoint]:
    """[start, end] 内的净值；跨度大时分页（每页 20 条）。"""
    points: dict[date, float] = {}
    page = 1
    while True:
        params = {"fundCode": code, "pageIndex": page, "pageSize": 20, "startDate": start.isoformat(), "endDate": end.isoformat()}
        body = client.get(f"{LSJZ_URL}?{urlencode(params)}", {"Referer": "https://fundf10.eastmoney.com/", "Accept": "application/json,*/*"})
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceError(f"lsjz 返回不是合法 JSON：{exc}") from exc
        if int(payload.get("ErrCode") or 0) != 0:
            raise SourceError(f"lsjz 报错：{payload.get('ErrMsg')}")
        rows = list((payload.get("Data") or {}).get("LSJZList") or [])
        for row in rows:
            raw_date = str(row.get("FSRQ") or "").strip()
            raw_nav = str(row.get("DWJZ") or "").strip()
            if raw_date and raw_nav:
                points[date.fromisoformat(raw_date)] = float(raw_nav)
        total = int(payload.get("TotalCount") or 0)
        if not rows or page * 20 >= total or page >= 60:
            break
        page += 1
    return [NavPoint(day, points[day]) for day in sorted(points)]


def fetch_fund_status(client: HttpClient, code: str) -> FundStatus:
    rows = _lsjz(client, code, page_size=1, start=None, end=None)
    if not rows:
        return FundStatus(None, None, None, "", "")
    row = rows[0]
    raw_date = str(row.get("FSRQ") or "").strip()
    sg = str(row.get("SGZT") or "")
    sh = str(row.get("SHZT") or "")
    return FundStatus(
        latest_date=date.fromisoformat(raw_date) if raw_date else None,
        subscription=_map_status(sg, "subscription"),
        redemption=_map_status(sh, "redemption"),
        subscription_text=sg,
        redemption_text=sh,
    )


def fetch_sse_index(client: HttpClient, *, count: int = 900) -> list[NavPoint]:
    """上证综指日收盘。begin=-N 表示最近 N 个交易日。"""
    url = f"{SSE_KLINE_URL}?{urlencode({'begin': -abs(count), 'end': -1, 'select': 'date,close'})}"
    body = client.get(url, {"Referer": "https://www.sse.com.cn/"})
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError(f"上交所行情返回不是合法 JSON：{exc}") from exc
    points: list[NavPoint] = []
    for row in payload.get("kline") or []:
        raw_date, close = row[0], row[1]
        text = str(int(raw_date))
        points.append(NavPoint(date(int(text[:4]), int(text[4:6]), int(text[6:8])), float(close)))
    if not points:
        raise SourceError("上交所行情为空")
    return points


def fetch_fred_sp500(client: HttpClient, *, start: date) -> list[NavPoint]:
    url = f"{FRED_SP500_URL}?{urlencode({'id': 'SP500', 'cosd': start.isoformat()})}"
    body = client.get(url, {"Accept": "text/csv,*/*"}).decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(body))
    header = next(reader, None)
    if not header or len(header) < 2 or header[1].strip() != "SP500":
        raise SourceError("FRED 返回格式异常（缺少 SP500 列）")
    points: list[NavPoint] = []
    for row in reader:
        if len(row) < 2 or row[1].strip() in {"", "."}:
            continue
        points.append(NavPoint(date.fromisoformat(row[0].strip()), float(row[1])))
    if not points:
        raise SourceError("FRED SP500 为空")
    return points
