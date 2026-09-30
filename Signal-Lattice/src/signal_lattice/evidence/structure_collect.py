"""结构性证据采集：候选池每家公司取「最新 10-K + 比它更新的 10-Q」的正文，抽取后只留小 JSON。

- 抽取结果缓存在 ExtractionCache（一份申报一个小文件，抽取器升级自动作废）；正文（段落保留的纯文本）压缩缓存在
  TextCache，和 Lazy Prices 共用同一个目录，同一份申报不重复下载；
- SEC 请求全部走传入的 SecClient（限速由调用方决定，研究层用 4 次/秒），本模块不绕过限速；
- 解析（去标签 + 正则）是 CPU 活，放进进程池；下载在线程里排队，互不阻塞；
- 任何一家失败只记数，不拖垮整批；请求总量有硬上限（max_requests）。
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .factstore import FactStore
from .prospectus import document_url
from .sec_client import SecClient, SecFetchError
from .structure_text import (EXTRACTOR_VERSION, ExtractionCache, FilingExtraction, build_filing_extraction)
from .text_similarity import TextCache, html_to_text

ANNUAL_FORMS = ("10-K", "10-KT")
QUARTERLY_FORMS = ("10-Q", "10-QT")
MIN_TEXT_CHARS = 2000


def pick_filings(rows: Sequence[Mapping]) -> List[Mapping]:
    """最新 10-K；再加一份比它更新的最新 10-Q（当前数字：积压/产能/客户占比）。都要有主文档。"""
    usable = [r for r in rows if r.get("primary_document") and "/" not in r["primary_document"]]
    annual = [r for r in usable if r["form"] in ANNUAL_FORMS]
    quarterly = [r for r in usable if r["form"] in QUARTERLY_FORMS]
    picked: List[Mapping] = []
    latest_annual = max(annual, key=lambda r: (r["filed"], r["accession"])) if annual else None
    if latest_annual:
        picked.append(latest_annual)
    if quarterly:
        latest_q = max(quarterly, key=lambda r: (r["filed"], r["accession"]))
        if latest_annual is None or latest_q["filed"] > latest_annual["filed"]:
            picked.append(latest_q)
    return picked


def parse_document(payload: bytes, meta: Mapping) -> Tuple[Optional[str], Optional[FilingExtraction]]:
    """CPU 部分（可在子进程里跑）：字节 -> (正文, 抽取)。正文太短（多半是抓到了错误页）返回 (None, None)。"""
    text = html_to_text(payload)
    if len(text) < MIN_TEXT_CHARS:
        return None, None
    return text, build_filing_extraction(text, cik=meta["cik"], accession=meta["accession"], form=meta["form"],
                                         filed=meta["filed"], period_end=meta.get("period_end"), url=meta["url"])


def _meta(cik: int, row: Mapping) -> dict:
    return {"cik": int(cik), "accession": row["accession"], "form": row["form"], "filed": row["filed"],
            "period_end": row.get("report_date"), "url": document_url(int(cik), row["accession"], row["primary_document"])}


def collect_structure(client: SecClient, store: FactStore, ciks: Sequence[int], as_of: str, text_cache: TextCache,
                      extraction_cache: ExtractionCache, *, fetch_workers: int = 4, parse_workers: int = 0,
                      max_requests: Optional[int] = None, log: Callable[[str], None] = print) -> Dict[str, object]:
    """返回 {"by_cik": {cik: [FilingExtraction...]}, "stats": {...}}。

    stats：filings（应有份数）、cached（抽取缓存命中）、from_text_cache（正文缓存命中、只重抽）、fetched（真下载）、
    failed、short_text、requests（本次 SEC 请求数）、skipped_by_cap。"""
    stats = {"companies": len(ciks), "filings": 0, "cached": 0, "from_text_cache": 0, "fetched": 0, "failed": 0,
             "short_text": 0, "skipped_by_cap": 0, "no_filing": 0}
    requests_before = client.requests_sent
    jobs: List[Tuple[int, Mapping]] = []
    by_cik: Dict[int, List[FilingExtraction]] = {}
    for cik in ciks:                                       # SQLite 只在主线程读
        rows = store.filings_as_of(int(cik), as_of, ANNUAL_FORMS + QUARTERLY_FORMS)
        picked = pick_filings([dict(r) for r in rows])
        if not picked:
            stats["no_filing"] += 1
            continue
        for row in picked:
            stats["filings"] += 1
            cached = extraction_cache.get(row["accession"])
            if cached is not None:
                by_cik.setdefault(int(cik), []).append(cached)
                stats["cached"] += 1
            else:
                jobs.append((int(cik), row))
    log("structure: %d filings needed, %d cached, %d to process" % (stats["filings"], stats["cached"], len(jobs)))

    pool = ProcessPoolExecutor(max_workers=parse_workers) if parse_workers > 0 else None

    def process(job: Tuple[int, Mapping]) -> Tuple[int, Optional[FilingExtraction], str]:
        cik, row = job
        meta = _meta(cik, row)
        text = text_cache.get(row["accession"])
        origin = "text_cache"
        if text is not None:
            _, extraction = parse_document_text(text, meta)
        else:
            try:
                payload = client.get_bytes(meta["url"], cache=False)
            except SecFetchError:
                return cik, None, "failed"
            origin = "fetched"
            if pool is not None:
                text, extraction = pool.submit(parse_document, payload, meta).result()
            else:
                text, extraction = parse_document(payload, meta)
            if text is None:
                return cik, None, "short_text"
            text_cache.put(row["accession"], text)
        if extraction is None:
            return cik, None, "short_text"
        extraction_cache.put(extraction)
        return cik, extraction, origin

    try:
        budget = len(jobs) if max_requests is None else max_requests
        # 只有「需要下载」的才占请求额度；先按额度截断（正文缓存命中的不占）
        runnable: List[Tuple[int, Mapping]] = []
        need_download = 0
        for job in jobs:
            if text_cache.get(job[1]["accession"]) is None:
                if need_download >= budget:
                    stats["skipped_by_cap"] += 1
                    continue
                need_download += 1
            runnable.append(job)
        with ThreadPoolExecutor(max_workers=fetch_workers) as threads:
            for index, (cik, extraction, origin) in enumerate(threads.map(process, runnable), 1):
                if extraction is None:
                    stats[origin] += 1
                else:
                    by_cik.setdefault(cik, []).append(extraction)
                    stats["fetched" if origin == "fetched" else "from_text_cache"] += 1
                if index % 100 == 0:
                    log("structure %d/%d fetched=%d failed=%d SEC requests %d" % (
                        index, len(runnable), stats["fetched"], stats["failed"], client.requests_sent - requests_before))
    finally:
        if pool is not None:
            pool.shutdown()
    stats["requests"] = client.requests_sent - requests_before
    stats["extractor_version"] = EXTRACTOR_VERSION
    return {"by_cik": by_cik, "stats": stats}


def parse_document_text(text: str, meta: Mapping) -> Tuple[Optional[str], Optional[FilingExtraction]]:
    if len(text) < MIN_TEXT_CHARS:
        return None, None
    return text, build_filing_extraction(text, cik=meta["cik"], accession=meta["accession"], form=meta["form"],
                                         filed=meta["filed"], period_end=meta.get("period_end"), url=meta["url"])
