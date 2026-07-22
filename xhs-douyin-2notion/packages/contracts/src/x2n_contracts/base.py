"""Shared strict primitives for the x2n 1.0 contract family."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import Enum
from typing import Annotated, Any
from urllib.parse import unquote, urlsplit

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, model_validator

CONTRACT_VERSION = "1.0"

PLATFORM_MEDIA_HOST_MARKERS = (
    "xhscdn",
    "douyinvod",
    "byteimg",
    "pstatp",
    "bilivideo",
    "hdslb",
    "kscdn",
    "yximgs",
    "sinaimg",
    "alicdn",
    "tbcdn",
)

CANONICAL_PAGE_HOSTS: dict[str, frozenset[str]] = {
    "xiaohongshu": frozenset({"xiaohongshu.com", "www.xiaohongshu.com"}),
    "douyin": frozenset({"douyin.com", "www.douyin.com"}),
    "bilibili": frozenset({"bilibili.com", "www.bilibili.com"}),
    "kuaishou": frozenset({"kuaishou.com", "www.kuaishou.com"}),
    "weibo": frozenset({"weibo.com", "www.weibo.com"}),
    "taobao": frozenset({"item.taobao.com", "taobao.com", "www.taobao.com"}),
}

_URL_RE = re.compile(r"https?://[^\s<>\"']+", flags=re.IGNORECASE)
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)


def _parse_rfc3339(value: Any) -> Any:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or _RFC3339_RE.fullmatch(value) is None:
        raise ValueError("RFC3339 datetime with timezone is required")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + ("+00:00" if value.endswith("Z") else ""))
    if parsed.utcoffset() is None:
        raise ValueError("RFC3339 datetime must contain a timezone")
    return parsed


RFC3339DateTime = Annotated[AwareDatetime, BeforeValidator(_parse_rfc3339)]


def _validate_canonical_json_value(value: Any) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError("canonical JSON integers must be JavaScript-safe")
        return
    if isinstance(value, float):
        raise ValueError("canonical payload JSON does not permit floating-point numbers")
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("canonical payload JSON object keys must be strings")
        for item in value.values():
            _validate_canonical_json_value(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_canonical_json_value(item)
        return
    raise ValueError("canonical payload contains a non-JSON value")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the cross-language payload-hash representation."""

    _validate_canonical_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _strings(item)


def contains_platform_media_url(value: str) -> bool:
    """Detect URL-shaped platform media references without storing host values."""

    for match in _URL_RE.finditer(value):
        try:
            host = (urlsplit(match.group(0)).hostname or "").lower()
        except ValueError:
            return True
        if any(marker in host for marker in PLATFORM_MEDIA_HOST_MARKERS):
            return True
    return False


def validate_canonical_page_url(value: str, platform: str | Enum) -> str:
    """Validate a persistable page URL; media URLs and redirect inputs are excluded."""

    platform_value = str(platform.value if isinstance(platform, Enum) else platform)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("canonical page URL is malformed") from error
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or host not in CANONICAL_PAGE_HOSTS.get(platform_value, frozenset())
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
    ):
        raise ValueError("canonical page URL must be an allowlisted https host/path without authority extras")
    decoded_segments = unquote(parsed.path).split("/")
    if any(segment in {".", ".."} for segment in decoded_segments):
        raise ValueError("canonical page URL contains a traversal segment")
    rebuilt = f"https://{host}{parsed.path}"
    if value != rebuilt:
        raise ValueError("canonical page URL is not normalized")
    if contains_platform_media_url(value):
        raise ValueError("platform media URL cannot enter a persistent contract")
    return value


class StrictContract(BaseModel):
    """Default-deny model used by every non-root contract object."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )

    @model_validator(mode="after")
    def reject_persisted_media_urls(self) -> "StrictContract":
        values = self.model_dump(mode="python", by_alias=True)
        if any(contains_platform_media_url(item) for item in _strings(values)):
            raise ValueError("platform media CDN URL persistence is forbidden")
        return self
