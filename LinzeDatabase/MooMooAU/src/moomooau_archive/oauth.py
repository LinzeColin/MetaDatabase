"""Exact Gmail OAuth refresh exchange and bound bearer injection."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import urlencode, urlsplit

from .auth import GMAIL_MODIFY_SCOPE, GOOGLE_TOKEN_ENDPOINT, GmailOAuthCredential
from .http_boundary import HttpRequest, HttpResponse, HttpTransport
from .secret_values import SecretText

_VISIBLE_ASCII = re.compile(r"^[\x21-\x7e]+$")


class OAuthExchangeError(RuntimeError):
    """A redacted OAuth exchange or bearer-boundary failure."""


@dataclass(frozen=True, slots=True, repr=False)
class GmailAccessToken:
    value: SecretText
    expires_at_utc: datetime
    scope: str = GMAIL_MODIFY_SCOPE

    def __post_init__(self) -> None:
        if (
            self.scope != GMAIL_MODIFY_SCOPE
            or self.expires_at_utc.tzinfo is None
            or self.expires_at_utc.utcoffset() != timedelta(0)
        ):
            raise OAuthExchangeError("Gmail access token metadata is invalid")

    def __repr__(self) -> str:
        return (
            "GmailAccessToken(value=<redacted>, "
            f"scope={self.scope!r}, expires_at_utc={self.expires_at_utc.isoformat()!r})"
        )

    def destroy(self) -> None:
        self.value.destroy()


class GmailOAuthTokenClient:
    """Exchange the one allowed authorized-user credential at Google's exact endpoint."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def exchange(self, credential: GmailOAuthCredential, *, now_utc: datetime) -> GmailAccessToken:
        current = _require_utc(now_utc)
        if (
            credential.token_endpoint != GOOGLE_TOKEN_ENDPOINT
            or credential.scope != GMAIL_MODIFY_SCOPE
        ):
            raise OAuthExchangeError("Gmail OAuth authority or scope is invalid")
        client_id = credential.client_id.reveal()
        client_secret = credential.client_secret.reveal()
        refresh_token = credential.refresh_token.reveal()
        if (
            not client_id.isascii()
            or not client_secret.isascii()
            or not refresh_token.isascii()
            or len(client_id) > 4096
            or len(client_secret) > 4096
            or len(refresh_token) > 16_384
        ):
            raise OAuthExchangeError("Gmail OAuth credential exceeds the byte contract")
        body = urlencode(
            (
                ("client_id", client_id),
                ("client_secret", client_secret),
                ("refresh_token", refresh_token),
                ("grant_type", "refresh_token"),
            )
        ).encode("ascii")
        response = self._transport.send(
            HttpRequest(
                "POST",
                GOOGLE_TOKEN_ENDPOINT,
                headers=(
                    ("Accept", "application/json"),
                    ("Content-Type", "application/x-www-form-urlencoded"),
                ),
                body=body,
            )
        )
        if response.status != 200:
            raise OAuthExchangeError("Gmail OAuth refresh failed")
        if len(response.body) > 64 * 1024:
            raise OAuthExchangeError("Gmail OAuth response exceeds the byte contract")
        try:
            value = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OAuthExchangeError("Gmail OAuth response is invalid") from exc
        if not isinstance(value, dict):
            raise OAuthExchangeError("Gmail OAuth response is not an object")
        payload = cast(dict[str, object], value)
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if (
            not isinstance(access_token, str)
            or not access_token
            or len(access_token) > 16_384
            or _VISIBLE_ASCII.fullmatch(access_token) is None
            or type(expires_in) is not int
            or not 1 <= expires_in <= 3600
            or payload.get("token_type") != "Bearer"
            or payload.get("scope") != GMAIL_MODIFY_SCOPE
        ):
            raise OAuthExchangeError("Gmail OAuth response exceeds the exact token contract")
        return GmailAccessToken(
            value=SecretText(access_token),
            expires_at_utc=current + timedelta(seconds=expires_in),
        )


class GmailBearerTransport:
    """Add one short-lived token only after GmailEndpointGuard accepts the request."""

    def __init__(
        self,
        transport: HttpTransport,
        token: GmailAccessToken,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._transport = transport
        self._token = token
        self._clock = clock or (lambda: datetime.now(UTC))

    def send(self, request: HttpRequest) -> HttpResponse:
        try:
            parsed = urlsplit(request.url)
            port = parsed.port
        except (TypeError, ValueError):
            raise OAuthExchangeError("Gmail bearer boundary rejected the request") from None
        if (
            parsed.scheme != "https"
            or parsed.hostname != "gmail.googleapis.com"
            or port is not None
            or any(name.casefold() == "authorization" for name, _ in request.headers)
        ):
            raise OAuthExchangeError("Gmail bearer boundary rejected the request")
        if _require_utc(self._clock()) >= self._token.expires_at_utc:
            raise OAuthExchangeError("Gmail access token has expired")
        headers = request.headers + (("Authorization", "Bearer " + self._token.value.reveal()),)
        return self._transport.send(
            HttpRequest(request.method, request.url, headers=headers, body=request.body)
        )


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise OAuthExchangeError("OAuth exchange time must be timezone-aware UTC")
    return value.astimezone(UTC)
