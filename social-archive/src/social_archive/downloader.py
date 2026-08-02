from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Iterable

import httpx

from .storage import ContentAddressedStore, StoredObject
from .utils import assert_public_http_url


class DirectMediaDownloader:
    def __init__(self, cas: ContentAddressedStore, max_bytes: int):
        self.cas = cas
        self.max_bytes = max_bytes

    def download(self, url: str) -> StoredObject:
        clean = assert_public_http_url(url, resolve_dns=True)
        chunks: list[bytes] = []
        total = 0
        with httpx.stream("GET", clean, timeout=60.0, follow_redirects=True, headers={"User-Agent":"SocialArchive/0.0.0.5"}) as response:
            response.raise_for_status()
            length = int(response.headers.get("content-length", "0") or 0)
            if length > self.max_bytes:
                raise ValueError("媒体超过单文件零费用预算")
            for chunk in response.iter_bytes(1024 * 1024):
                total += len(chunk)
                if total > self.max_bytes:
                    raise ValueError("媒体超过单文件零费用预算")
                chunks.append(chunk)
            media_type = response.headers.get("content-type", "").split(";",1)[0] or None
        suffix = mimetypes.guess_extension(media_type or "") or ""
        return self.cas.put_bytes(b"".join(chunks), suffix=suffix, media_type=media_type)
