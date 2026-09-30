"""事件研究用的长历史日线（腾讯 fqkline 前复权，1000 根 ≈ 4 年），落盘为紧凑 JSON。

复用 marketdata 的腾讯解析（含 OHLCV 校验）；限速：4 个并发、每次请求后小睡，对腾讯友好。
基准 IWM 走同一接口（usIWM.AM）。
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ..marketdata.base import HttpClient, MarketDataError
from ..marketdata.models import Instrument
from ..marketdata.tencent import TencentKlineProvider

KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/{kind}/get?param={symbol},day,,,%d,qfq"
BAR_COUNT = 1000
SUFFIX = {"Nasdaq": "OQ", "NYSE": "N", "NYSE American": "AM"}
BENCHMARK = ("IWM", "AM")  # 小盘基准：罗素 2000 ETF


def _instrument(symbol: str, suffix: str) -> Instrument:
    return Instrument(
        symbol="us" + symbol, name=symbol, market="US", asset_type="STOCK", timezone="America/New_York",
        sina_symbol=None, tencent_symbol=None, tencent_kline_symbol="us%s.%s" % (symbol, suffix),
        eastmoney_fund_code=None, benchmark=None)


class BarStore:
    """{symbol: [(YYYY-MM-DD, close, volume), ...]}，一只一个文件。"""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, symbol: str) -> Path:
        return self.directory / ("%s.json" % symbol.upper())

    def load(self, symbol: str) -> Optional[List[Tuple[str, float, Optional[float]]]]:
        path = self.path(symbol)
        if not path.is_file():
            return None
        try:
            return [tuple(row) for row in json.loads(path.read_text("utf-8"))["bars"]]
        except (OSError, ValueError, KeyError):
            return None

    def save(self, symbol: str, bars: Sequence[tuple]) -> None:
        temporary = self.path(symbol).with_suffix(".tmp")
        temporary.write_text(json.dumps({"symbol": symbol, "fetched_at": datetime.now(timezone.utc).isoformat(),
                                         "bars": [list(b) for b in bars]}), "utf-8")
        temporary.replace(self.path(symbol))


def fetch_history(store: BarStore, targets: Iterable[Tuple[str, str]], workers: int = 4,
                  log: Callable[[str], None] = print, refetch_older_than_days: Optional[float] = None) -> dict:
    """targets: [(symbol, 交易所标签)]。已有文件的跳过（除非过期）。返回 {ok, failed: [...]}。"""
    targets = list(targets)
    provider = TencentKlineProvider(HttpClient(timeout_seconds=20.0, attempts=3), cache=_NoCache(),
                                    endpoint=KLINE_URL % BAR_COUNT)
    pending = []
    for symbol, exchange in targets:
        path = store.path(symbol)
        if path.is_file() and (refetch_older_than_days is None
                               or time.time() - path.stat().st_mtime < refetch_older_than_days * 86400):
            continue
        pending.append((symbol, exchange))

    def fetch(item):
        symbol, exchange = item
        try:
            bars = provider.fetch(_instrument(symbol, SUFFIX.get(exchange, exchange)))
        except MarketDataError as exc:
            return symbol, None, str(exc)
        finally:
            time.sleep(0.15)
        return symbol, [(b.day.isoformat(), b.close, b.volume) for b in bars], None

    ok, failed = 0, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (symbol, bars, error) in enumerate(pool.map(fetch, pending), 1):
            if bars is None:
                failed.append((symbol, error))
            else:
                store.save(symbol, bars)
                ok += 1
            if index % 200 == 0:
                log("bars %d/%d ok=%d failed=%d" % (index, len(pending), ok, len(failed)))
    return {"ok": ok, "failed": failed, "skipped": len(targets) - len(pending)}


class _NoCache:
    """腾讯 provider 要一个缓存对象；这里我们自己落盘，所以给一个永远未命中的空实现。"""

    def load(self, key, max_age_seconds):
        return None

    def save(self, key, payload):
        return None

    def delete(self, key):
        return None
