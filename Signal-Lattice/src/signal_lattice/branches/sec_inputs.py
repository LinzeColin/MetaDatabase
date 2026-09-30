"""B3a 数据准备：把候选池每家公司的 companyfacts 按需裁剪后入时点事实库，并取日线历史。

- companyfacts 每家一次请求（全局限速 ≤5 次/秒，由 SecClient 的进程级限速器保证）；
  只保留打分用得到的概念（fundamentals.NEEDED_CONCEPTS），事实库不必装下每家上万行；
- 已入过账的公司跳过（可断点续跑）；
- 日线历史用腾讯 fqkline（前复权）800 根，只用于「自身历史估值分位」与价格动量，且按 as_of 截断。
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..evidence.factstore import FactStore
from ..evidence.sec_client import SecClient, SecFetchError, SecNotFound
from ..marketdata.base import DiskCache, HttpClient, MarketDataError
from ..marketdata.models import Instrument
from ..marketdata.tencent import TencentKlineProvider
from ..universe import TENCENT_SUFFIX
from .fundamentals import NEEDED_CONCEPTS

HISTORY_ENDPOINT = "https://web.ifzq.gtimg.cn/appstock/app/{kind}/get?param={symbol},day,,,800,qfq"
INGEST_SOURCE = "companyfacts"


def prune_companyfacts(payload: dict, concepts: Iterable[str] = NEEDED_CONCEPTS) -> dict:
    wanted = set(concepts)
    kept: Dict[str, dict] = {}
    for taxonomy, tags in (payload.get("facts") or {}).items():
        for tag, body in tags.items():
            if "%s:%s" % (taxonomy, tag) in wanted:
                kept.setdefault(taxonomy, {})[tag] = body
    return {**{k: v for k, v in payload.items() if k != "facts"}, "facts": kept}


def already_ingested(store: FactStore) -> set:
    rows = store.db.execute("SELECT DISTINCT cik FROM ingest_log WHERE source = ?", (INGEST_SOURCE,))
    return {int(row[0]) for row in rows}


def collect_companyfacts(client: SecClient, store: FactStore, ciks: Sequence[int], today: str,
                         workers: int = 4, log: Callable[[str], None] = print,
                         max_requests: Optional[int] = None) -> Dict[str, int]:
    """返回 {ingested, skipped, not_found, failed}。max_requests 是本次运行的请求硬上限。"""
    done = already_ingested(store)
    todo = [int(c) for c in ciks if int(c) not in done]
    if max_requests is not None:
        todo = todo[:max_requests]
    stats = {"ingested": 0, "skipped": len(ciks) - len(todo), "not_found": 0, "failed": 0}

    def fetch(cik: int) -> Tuple[int, Optional[dict], Optional[str]]:
        try:
            return cik, prune_companyfacts(client.companyfacts(cik)), None
        except SecNotFound:
            return cik, None, "not_found"
        except SecFetchError as exc:
            return cik, None, "failed:%s" % exc

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (cik, payload, error) in enumerate(pool.map(fetch, todo), 1):
            if payload is not None:
                store.ingest_companyfacts(cik, payload, today)
                stats["ingested"] += 1
            elif error == "not_found":
                stats["not_found"] += 1
            else:
                stats["failed"] += 1
                log("companyfacts %s %s" % (cik, error))
            if index % 100 == 0:
                log("companyfacts progress %d/%d (SEC requests %d)" % (index, len(todo), client.requests_sent))
    return stats


def make_history_fetcher(cache_dir: Path, client: Optional[HttpClient] = None,
                         max_age_seconds: int = 24 * 3600) -> Callable[[Mapping], List[Tuple[str, float]]]:
    provider = TencentKlineProvider(client or HttpClient(timeout_seconds=20.0, attempts=3), DiskCache(Path(cache_dir)),
                                    endpoint=HISTORY_ENDPOINT)

    def fetch(entry: Mapping) -> List[Tuple[str, float]]:
        instrument = Instrument(
            symbol="us" + entry["symbol"], name=entry["name"], market="US", asset_type="STOCK",
            timezone="America/New_York", sina_symbol="gb_" + entry["symbol"].lower(), tencent_symbol=None,
            tencent_kline_symbol="us%s.%s" % (entry["symbol"], TENCENT_SUFFIX[entry["exchange"]]),
            eastmoney_fund_code=None, benchmark=None,
        )
        try:
            bars = provider.fetch(instrument)
        except MarketDataError:
            return []
        return [(bar.day.isoformat(), bar.close) for bar in bars]

    return fetch


def collect_history(entries: Sequence[Mapping], cache_dir: Path, workers: int = 6) -> Dict[str, List[Tuple[str, float]]]:
    fetch = make_history_fetcher(cache_dir)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch, entries))
    return {entry["symbol"]: rows for entry, rows in zip(entries, results)}
