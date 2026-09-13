"""免密钥市场数据 provider 共用的 HTTP、缓存和解析辅助。"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


class MarketDataError(RuntimeError):
    """调用端收到这个异常时必须阻断结论，不能回退到旧市场快照。"""


class HttpClient:
    def __init__(self, timeout_seconds: float = 10.0, attempts: int = 3) -> None:
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts

    def get(self, url: str, headers: Optional[Dict[str, str]] = None) -> bytes:
        merged = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if headers:
            merged.update(headers)
        last_error: Optional[BaseException] = None
        for attempt in range(self.attempts):
            request = urllib.request.Request(url, headers=merged)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    if response.status != 200:
                        raise MarketDataError("HTTP_STATUS_%s" % response.status)
                    return response.read()
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, MarketDataError) as exc:
                last_error = exc
                if attempt + 1 < self.attempts:
                    time.sleep(0.25 * (2 ** attempt))
        raise MarketDataError("HTTP_REQUEST_FAILED:%s" % type(last_error).__name__)


class DiskCache:
    """历史日线缓存；运行时目录由 systemd 写入 /var/lib，不进入 Git。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self, key: str, max_age_seconds: int) -> Optional[bytes]:
        path = self.root / (key + ".json")
        if not path.is_file() or time.time() - path.stat().st_mtime > max_age_seconds:
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    def save(self, key: str, payload: bytes) -> None:
        path = self.root / (key + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, path)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_json(payload: bytes, source: str) -> dict:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketDataError("%s_JSON_INVALID" % source) from exc
    if not isinstance(value, dict):
        raise MarketDataError("%s_OBJECT_REQUIRED" % source)
    return value
