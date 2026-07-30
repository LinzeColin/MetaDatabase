from __future__ import annotations

import hashlib
import hmac
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .constants import VERSION

ALLOWED_UPSTREAM_HOSTS = frozenset(
    {
        "github.com",
        "raw.githubusercontent.com",
        "api.github.com",
        "codeload.github.com",
    }
)


@dataclass(frozen=True)
class FetchResult:
    state: str
    etag: str | None
    body: bytes | None
    status: int


def verify_webhook(secret: bytes, body: bytes, signature_header: str) -> bool:
    if not secret or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def validate_upstream_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise ValueError("UPSTREAM_HTTPS_REQUIRED")
    if parsed.username or parsed.password:
        raise ValueError("UPSTREAM_USERINFO_FORBIDDEN")
    if parsed.port not in (None, 443):
        raise ValueError("UPSTREAM_PORT_FORBIDDEN")
    hostname = (parsed.hostname or "").lower()
    if hostname not in ALLOWED_UPSTREAM_HOSTS:
        raise ValueError("UPSTREAM_HOST_NOT_ALLOWED")
    decoded_path = urllib.parse.unquote(parsed.path)
    if any(segment in {".", ".."} for segment in decoded_path.split("/")):
        raise ValueError("UPSTREAM_PATH_TRAVERSAL")
    if parsed.fragment:
        raise ValueError("UPSTREAM_FRAGMENT_FORBIDDEN")
    return urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        validated = validate_upstream_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, validated)


def conditional_get(
    url: str,
    etag: str | None = None,
    max_bytes: int = 2_000_000,
    timeout: int = 20,
) -> FetchResult:
    if max_bytes < 1 or max_bytes > 50_000_000:
        raise ValueError("INVALID_MAX_BYTES")
    if timeout < 1 or timeout > 120:
        raise ValueError("INVALID_TIMEOUT")
    validated_url = validate_upstream_url(url)
    headers = {"User-Agent": f"Signal-Lattice/{VERSION}", "Accept": "application/json,text/plain,*/*"}
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(validated_url, headers=headers, method="GET")
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw_length = response.headers.get("Content-Length")
            try:
                length = int(raw_length) if raw_length else 0
            except ValueError as exc:
                raise RuntimeError("UPSTREAM_INVALID_CONTENT_LENGTH") from exc
            if length > max_bytes:
                raise RuntimeError("UPSTREAM_CONTENT_TOO_LARGE")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise RuntimeError("UPSTREAM_CONTENT_TOO_LARGE")
            return FetchResult("UPDATED", response.headers.get("ETag"), body, response.status)
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return FetchResult("NOT_MODIFIED", etag, None, 304)
        raise
