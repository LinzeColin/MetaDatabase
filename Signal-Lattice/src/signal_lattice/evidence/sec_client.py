"""SEC 免 key 接口客户端：声明性 User-Agent、全局限速、ETag 缓存、有上限的退避重试。

只用标准库 urllib。所有请求共用一个进程级限速器，同一进程里无论建几个客户端，
对 SEC 的请求都不超过每秒 5 次（SEC 公开上限是 10 次/秒，留一半余量）。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

DEFAULT_USER_AGENT = "SignalLattice research ops@linzezhang.com"
USER_AGENT_ENV = "SIGNAL_LATTICE_SEC_UA"
MAX_REQUESTS_PER_SECOND = 5
# 间隔取 0.21 秒：任意闭区间 1 秒内最多 5 次（5×0.21>1）。
MIN_INTERVAL_SECONDS = 0.21
# 失败重试上限：每个请求最多发 3 次（首发 + 2 次重试）。
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 30.0
TIMEOUT_SECONDS = 30.0

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{period}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{name}"


class SecFetchError(RuntimeError):
    """重试用尽或遇到不可重试的 HTTP 错误。"""


class SecNotFound(SecFetchError):
    """404：这个 CIK/文件在 SEC 没有数据，不重试。"""


class RateLimiter:
    """线程安全的等间隔限速器；时钟与睡眠可注入，便于测试。"""

    def __init__(
        self,
        min_interval: float = MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            wait = self._next_slot - now
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
            self._next_slot = max(now, self._next_slot) + self.min_interval


GLOBAL_LIMITER = RateLimiter()


def user_agent_from_env() -> str:
    return os.environ.get(USER_AGENT_ENV, "").strip() or DEFAULT_USER_AGENT


def form4_raw_xml_name(primary_document: str) -> str:
    """submissions 里的 primaryDocument 带 xslF345X0n/ 前缀（渲染后的 HTML），去掉才是原始 XML。"""
    head, sep, tail = primary_document.partition("/")
    if sep and head.lower().startswith("xslf345"):
        return tail
    return primary_document


class SecClient:
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        user_agent: Optional[str] = None,
        limiter: RateLimiter = GLOBAL_LIMITER,
        opener: Optional[Callable] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent or user_agent_from_env()
        self.limiter = limiter
        self._opener = opener or (lambda request, timeout: urllib.request.urlopen(request, timeout=timeout))
        self._sleep = sleep
        self.requests_sent = 0
        self.cache_hits_304 = 0

    # ---- 缓存 -------------------------------------------------------------
    def _paths(self, url: str) -> Optional[tuple[Path, Path]]:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        folder = self.cache_dir / digest[:2]
        return folder / (digest + ".body"), folder / (digest + ".meta.json")

    def _load_cache(self, url: str) -> Optional[tuple[bytes, dict]]:
        paths = self._paths(url)
        if paths is None or not paths[0].is_file() or not paths[1].is_file():
            return None
        try:
            return paths[0].read_bytes(), json.loads(paths[1].read_text("utf-8"))
        except (OSError, ValueError):
            return None

    def _save_cache(self, url: str, body: bytes, meta: dict) -> None:
        paths = self._paths(url)
        if paths is None:
            return
        paths[0].parent.mkdir(parents=True, exist_ok=True)
        for target, data in ((paths[0], body), (paths[1], json.dumps(meta).encode("utf-8"))):
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(data)
            os.replace(temporary, target)

    # ---- 请求 -------------------------------------------------------------
    def get_bytes(self, url: str) -> bytes:
        cached = self._load_cache(url)
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip", "Accept": "*/*"}
        if cached is not None:
            etag = cached[1].get("etag")
            modified = cached[1].get("last_modified")
            if etag:
                headers["If-None-Match"] = etag
            if modified:
                headers["If-Modified-Since"] = modified
        last_error: Optional[BaseException] = None
        for attempt in range(MAX_ATTEMPTS):
            self.limiter.acquire()
            self.requests_sent += 1
            request = urllib.request.Request(url, headers=headers)
            retry_after = 0.0
            try:
                response = self._opener(request, TIMEOUT_SECONDS)
                try:
                    body = response.read()
                    response_headers = response.headers
                finally:
                    close = getattr(response, "close", None)
                    if close:
                        close()
                if (response_headers.get("Content-Encoding") or "").lower() == "gzip":
                    body = gzip.decompress(body)
                self._save_cache(url, body, {
                    "url": url,
                    "etag": response_headers.get("ETag"),
                    "last_modified": response_headers.get("Last-Modified"),
                    "fetched_at": time.time(),
                })
                return body
            except urllib.error.HTTPError as exc:
                if exc.code == 304 and cached is not None:
                    self.cache_hits_304 += 1
                    return cached[0]
                if exc.code == 404:
                    raise SecNotFound("HTTP_404:%s" % url) from exc
                if exc.code not in (403, 429) and exc.code < 500:
                    raise SecFetchError("HTTP_%s:%s" % (exc.code, url)) from exc
                last_error = exc
                try:
                    retry_after = float(exc.headers.get("Retry-After", 0)) if exc.headers else 0.0
                except (TypeError, ValueError):
                    retry_after = 0.0
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, EOFError) as exc:
                last_error = exc
            if attempt + 1 < MAX_ATTEMPTS:
                self._sleep(min(BACKOFF_CAP_SECONDS, max(retry_after, BACKOFF_BASE_SECONDS * (2 ** attempt))))
        raise SecFetchError("RETRIES_EXHAUSTED:%s:%s" % (type(last_error).__name__, url))

    def get_json(self, url: str):
        try:
            return json.loads(self.get_bytes(url).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise SecFetchError("JSON_INVALID:%s" % url) from exc

    # ---- 具名接口 ---------------------------------------------------------
    def company_tickers_exchange(self) -> list[dict]:
        """返回 [{cik, name, ticker, exchange}, ...]。"""
        payload = self.get_json(TICKERS_URL)
        fields = payload["fields"]
        return [dict(zip(fields, row)) for row in payload["data"]]

    def submissions(self, cik: int) -> dict:
        return self.get_json(SUBMISSIONS_URL.format(cik=int(cik)))

    def companyfacts(self, cik: int) -> dict:
        return self.get_json(COMPANYFACTS_URL.format(cik=int(cik)))

    def frames(self, taxonomy: str, concept: str, unit: str, period: str) -> dict:
        return self.get_json(FRAMES_URL.format(taxonomy=taxonomy, concept=concept, unit=unit, period=period))

    def form4_xml(self, cik: int, accession: str, primary_document: str) -> bytes:
        url = ARCHIVE_URL.format(
            cik=int(cik),
            accession_nodash=accession.replace("-", ""),
            name=form4_raw_xml_name(primary_document),
        )
        return self.get_bytes(url)
