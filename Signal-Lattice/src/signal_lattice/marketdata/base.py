"""免密钥市场数据 provider 共用的 HTTP、缓存和解析辅助。"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, TypeVar


USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
ParsedPayload = TypeVar("ParsedPayload")


class MarketDataError(RuntimeError):
    """调用端收到这个异常时必须阻断结论，不能回退到旧市场快照。"""


class CollectionBudgetExceeded(RuntimeError):
    """本轮或当日请求预算已用尽，当前请求没有发往上游。"""


def decode_text(payload: bytes, encoding: str, source: str) -> str:
    """把上游字节解码边界统一收敛为可阻断的市场数据错误。"""
    try:
        return payload.decode(encoding, errors="strict")
    except (AttributeError, UnicodeDecodeError) as exc:
        raise MarketDataError("%s_DECODE_FAILED" % source) from exc


class HttpClient:
    def __init__(
        self,
        timeout_seconds: float = 10.0,
        attempts: int = 3,
        on_request: Callable[[str], None] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts
        self.on_request = on_request

    def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        *,
        provider: str,
    ) -> bytes:
        merged = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if headers:
            merged.update(headers)
        last_error: Optional[BaseException] = None
        for attempt in range(self.attempts):
            if self.on_request is not None:
                self.on_request(provider)
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

    def delete(self, key: str) -> None:
        """移除已确认不能解析的缓存项，使本轮可以受限地重新取数。"""
        try:
            (self.root / (key + ".json")).unlink()
        except FileNotFoundError:
            return


def fetch_validated_cached(
    cache: DiskCache,
    key: str,
    max_age_seconds: int,
    fetch_payload: Callable[[], bytes],
    parse_payload: Callable[[bytes], ParsedPayload],
) -> ParsedPayload:
    """只缓存已完成语义解析的日线响应。

    过期前的缓存仍需重新解析。缓存损坏时只删该键，并在当前调用内执行一次
    新拉取；新响应同样必须先解析成功，才允许写回缓存。
    """
    cached = cache.load(key, max_age_seconds)
    if cached is not None:
        try:
            return parse_payload(cached)
        except MarketDataError:
            cache.delete(key)
    payload = fetch_payload()
    parsed = parse_payload(payload)
    cache.save(key, payload)
    return parsed


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def read_json(payload: bytes, source: str) -> dict:
    try:
        value = json.loads(decode_text(payload, "utf-8", source))
    except (TypeError, json.JSONDecodeError) as exc:
        raise MarketDataError("%s_JSON_INVALID" % source) from exc
    if not isinstance(value, dict):
        raise MarketDataError("%s_OBJECT_REQUIRED" % source)
    return value
