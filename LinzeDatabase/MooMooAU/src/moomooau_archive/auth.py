"""Fail-closed loading for the single Gmail OAuth credential Secret."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, cast

from .secret_values import SecretText

GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GMAIL_OAUTH_SECRET_NAME = "MOOMOOAU_GMAIL_OAUTH"  # pragma: allowlist secret


class CredentialConfigurationError(RuntimeError):
    pass


class SecretSource(Protocol):
    def read(self, name: str) -> SecretText: ...


@dataclass(frozen=True, slots=True, repr=False)
class GmailOAuthCredential:
    client_id: SecretText
    client_secret: SecretText
    refresh_token: SecretText
    scope: str = GMAIL_MODIFY_SCOPE
    token_endpoint: str = GOOGLE_TOKEN_ENDPOINT

    def __repr__(self) -> str:
        return (
            "GmailOAuthCredential(scope="
            f"{self.scope!r}, token_endpoint={self.token_endpoint!r}, values=<redacted>)"
        )

    def destroy(self) -> None:
        self.client_id.destroy()
        self.client_secret.destroy()
        self.refresh_token.destroy()


def load_gmail_oauth_credential(
    source: SecretSource,
    *,
    secret_name: str = GMAIL_OAUTH_SECRET_NAME,
) -> GmailOAuthCredential:
    """Read exactly one named Secret and validate a deliberately narrow JSON contract."""

    if secret_name != GMAIL_OAUTH_SECRET_NAME:
        raise CredentialConfigurationError("unexpected Gmail OAuth Secret name")
    encoded = source.read(secret_name)
    try:
        parsed = json.loads(encoded.reveal())
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CredentialConfigurationError("Gmail OAuth Secret is not valid JSON") from exc
    finally:
        encoded.destroy()
    if not isinstance(parsed, dict):
        raise CredentialConfigurationError("Gmail OAuth Secret must be a JSON object")
    value = cast(dict[str, object], parsed)
    required = {"type", "client_id", "client_secret", "refresh_token", "token_uri", "scopes"}
    if set(value) != required:
        raise CredentialConfigurationError("Gmail OAuth Secret fields do not match the contract")
    if value.get("type") != "authorized_user" or value.get("token_uri") != GOOGLE_TOKEN_ENDPOINT:
        raise CredentialConfigurationError("Gmail OAuth authority is not allowed")
    scopes = value.get("scopes")
    if scopes != [GMAIL_MODIFY_SCOPE]:
        raise CredentialConfigurationError("Gmail OAuth scope must be exactly gmail.modify")
    secret_fields = ("client_id", "client_secret", "refresh_token")
    if any(not isinstance(value.get(field), str) or not value[field] for field in secret_fields):
        raise CredentialConfigurationError("Gmail OAuth credential value is missing")
    return GmailOAuthCredential(
        client_id=SecretText(cast(str, value["client_id"])),
        client_secret=SecretText(cast(str, value["client_secret"])),
        refresh_token=SecretText(cast(str, value["refresh_token"])),
    )
