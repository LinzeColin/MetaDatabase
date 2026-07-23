"""Small dependency-injected HTTP boundary with redacted representations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True, repr=False)
class HttpRequest:
    method: str
    url: str
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None

    def __repr__(self) -> str:
        parsed = urlsplit(self.url)
        return (
            "HttpRequest(method="
            f"{self.method!r}, host={parsed.hostname!r}, path=<redacted>, body=<redacted>)"
        )


@dataclass(frozen=True, slots=True, repr=False)
class HttpResponse:
    status: int
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()

    def __repr__(self) -> str:
        return f"HttpResponse(status={self.status!r}, body=<redacted>)"


class HttpTransport(Protocol):
    def send(self, request: HttpRequest) -> HttpResponse: ...
