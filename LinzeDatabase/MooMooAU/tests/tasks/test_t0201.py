from __future__ import annotations

import json
import logging

import pytest

from moomooau_archive.auth import (
    GMAIL_MODIFY_SCOPE,
    GMAIL_OAUTH_SECRET_NAME,
    CredentialConfigurationError,
    load_gmail_oauth_credential,
)
from moomooau_archive.secret_values import SecretText


class TrackingSecretSource:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.reads: list[str] = []

    def read(self, name: str) -> SecretText:
        self.reads.append(name)
        return SecretText(json.dumps(self.payload, sort_keys=True))


def _credential_payload() -> dict[str, object]:
    return {
        "type": "authorized_user",
        "client_id": "synthetic-client-id",
        "client_secret": "synthetic-client-secret",  # pragma: allowlist secret
        "refresh_token": "synthetic-refresh-value",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": [GMAIL_MODIFY_SCOPE],
    }


def test_t0201_loads_exactly_one_narrow_oauth_secret_without_logging_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = TrackingSecretSource(_credential_payload())
    credential = load_gmail_oauth_credential(source)
    logging.getLogger("stage2-auth-test").warning("%r", credential)

    assert source.reads == [GMAIL_OAUTH_SECRET_NAME]
    assert credential.scope == GMAIL_MODIFY_SCOPE
    assert credential.client_id.reveal() == "synthetic-client-id"
    rendered = repr(credential) + caplog.text
    for private_value in (
        "synthetic-client-id",
        "synthetic-client-secret",
        "synthetic-refresh-value",
    ):
        assert private_value not in rendered
    credential.destroy()
    assert credential.client_id.destroyed
    assert credential.client_secret.destroyed
    assert credential.refresh_token.destroyed


def test_t0201_rejects_scope_or_secret_name_drift_fail_closed() -> None:
    payload = _credential_payload()
    payload["scopes"] = ["https://www.googleapis.com/auth/gmail.readonly"]
    source = TrackingSecretSource(payload)
    with pytest.raises(CredentialConfigurationError, match="exactly gmail.modify"):
        load_gmail_oauth_credential(source)
    assert source.reads == [GMAIL_OAUTH_SECRET_NAME]

    untouched = TrackingSecretSource(_credential_payload())
    with pytest.raises(CredentialConfigurationError, match="unexpected"):
        load_gmail_oauth_credential(
            untouched,
            secret_name="UNAPPROVED_SECRET",  # pragma: allowlist secret
        )
    assert untouched.reads == []
