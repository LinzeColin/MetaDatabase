"""Bounded HTTPS transport for protected cloud runners.

Endpoint-specific guards remain authoritative.  This adapter adds TLS verification through the
standard library defaults, rejects redirects and prevents unbounded request/response buffering.
Diagnostics intentionally omit URLs, headers and bodies.
"""

from __future__ import annotations

import re
from email.message import Message
from http.client import HTTPResponse
from io import BufferedIOBase
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

from .http_boundary import HttpRequest
from .http_boundary import HttpResponse as BoundaryResponse

_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class HttpTransportError(RuntimeError):
    """A redacted transport failure."""


class _ReadableResponse(Protocol):
    headers: Message

    def getcode(self) -> int | None: ...

    def read(self, amount: int = -1) -> bytes: ...

    def close(self) -> None: ...


class _Opener(Protocol):
    def open(self, request: Request, timeout: float | None = None) -> _ReadableResponse: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: Request,
        fp: BufferedIOBase | HTTPResponse,
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


class StdlibHttpsTransport:
    """Send one HTTPS request with no redirect following and bounded bodies."""

    _SAFE_RESPONSE_HEADERS = frozenset({"content-type", "etag", "retry-after", "x-ratelimit-reset"})

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        maximum_request_bytes: int = 128 * 1024 * 1024,
        maximum_response_bytes: int = 128 * 1024 * 1024,
        opener: _Opener | None = None,
    ) -> None:
        if (
            type(timeout_seconds) not in {int, float}
            or not 0 < timeout_seconds <= 120
            or type(maximum_request_bytes) is not int
            or not 1 <= maximum_request_bytes <= 128 * 1024 * 1024
            or type(maximum_response_bytes) is not int
            or not 1 <= maximum_response_bytes <= 128 * 1024 * 1024
        ):
            raise HttpTransportError("HTTPS transport limits are invalid")
        self._timeout_seconds = timeout_seconds
        self._maximum_request_bytes = maximum_request_bytes
        self._maximum_response_bytes = maximum_response_bytes
        self._opener: _Opener = opener if opener is not None else _default_opener()

    def send(self, request: HttpRequest) -> BoundaryResponse:
        self._validate_request(request)
        try:
            outbound = Request(
                request.url,
                data=request.body,
                headers={name: value for name, value in request.headers},
                method=request.method,
            )
        except (TypeError, ValueError):
            raise HttpTransportError("HTTPS request could not be constructed") from None
        response: _ReadableResponse
        try:
            response = self._opener.open(outbound, timeout=self._timeout_seconds)
        except HTTPError as exc:
            response = exc
        except (URLError, TimeoutError, OSError):
            raise HttpTransportError("HTTPS request failed") from None
        try:
            body = response.read(self._maximum_response_bytes + 1)
            if len(body) > self._maximum_response_bytes:
                raise HttpTransportError("HTTPS response exceeded the byte limit")
            status = response.getcode()
            if type(status) is not int or not 100 <= status <= 599:
                raise HttpTransportError("HTTPS response status is invalid")
            headers = self._safe_headers(response.headers)
            return BoundaryResponse(status=status, body=body, headers=headers)
        except (OSError, ValueError):
            raise HttpTransportError("HTTPS response could not be read") from None
        finally:
            response.close()

    def _validate_request(self, request: HttpRequest) -> None:
        if not isinstance(request.url, str) or not isinstance(request.method, str):
            raise HttpTransportError("HTTPS request boundary rejected the request")
        try:
            parsed = urlsplit(request.url)
            port = parsed.port
        except (TypeError, ValueError):
            raise HttpTransportError("HTTPS request authority is invalid") from None
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or request.method not in {"GET", "POST", "PUT", "DELETE"}
        ):
            raise HttpTransportError("HTTPS request boundary rejected the request")
        if request.body is not None and len(request.body) > self._maximum_request_bytes:
            raise HttpTransportError("HTTPS request exceeded the byte limit")
        names: set[str] = set()
        for name, value in request.headers:
            if not isinstance(name, str) or not isinstance(value, str):
                raise HttpTransportError("HTTPS request header is invalid")
            lowered = name.casefold()
            if (
                _HEADER_NAME.fullmatch(name) is None
                or lowered in names
                or len(name) > 128
                or len(value) > 16_384
                or any(character in name or character in value for character in ("\r", "\n"))
            ):
                raise HttpTransportError("HTTPS request header is invalid")
            names.add(lowered)

    @classmethod
    def _safe_headers(cls, headers: Message) -> tuple[tuple[str, str], ...]:
        safe: list[tuple[str, str]] = []
        for name, value in headers.items():
            if (
                name.casefold() in cls._SAFE_RESPONSE_HEADERS
                and len(value) <= 4096
                and "\r" not in value
                and "\n" not in value
            ):
                safe.append((name, value))
        return tuple(safe)


def _default_opener() -> _Opener:
    opener: OpenerDirector = build_opener(_NoRedirect())
    return opener  # type: ignore[return-value]
