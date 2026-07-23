from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from moomooau_archive.adapters import AGE_HEADER
from moomooau_archive.github_guard import (
    GITHUB_UPLOAD_ORIGIN,
    LIVE_ASSET_NAME,
    GitHubAppJwtSigner,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    GitHubInstallationTokenClient,
    GitHubInstallationTokenError,
    InstallationTokenFailureClass,
    RepositoryLocator,
    TargetRepositoryConfig,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.secret_values import SecretBytes


class TokenTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return self.response


def _decode_segment(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _synthetic_age_envelope() -> bytes:
    encoded_32_bytes = b"A" * 43
    return b"\n".join(
        (
            AGE_HEADER,
            b"-> X25519 " + encoded_32_bytes,
            encoded_32_bytes,
            b"--- " + encoded_32_bytes,
            b"\x00" * 32,
        )
    )


def _token_response(
    repository_id: int, now: datetime, *, extra_repository: bool = False
) -> HttpResponse:
    repositories = [{"id": repository_id, "name": "synthetic-target"}]
    if extra_repository:
        repositories.append({"id": repository_id + 1})
    return HttpResponse(
        201,
        json.dumps(
            {
                "token": "synthetic-installation-token",
                "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                "repositories": repositories,
                "permissions": {"contents": "write", "metadata": "read"},
            },
            sort_keys=True,
        ).encode(),
    )


def test_t0204_mints_short_token_for_exactly_one_repository_and_verifies_rs256() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100001, installation_id=8100001)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    secret = SecretBytes(pem)
    transport = TokenTransport(_token_response(config.repository_id, now))
    guard = GitHubEndpointGuard(transport, config)
    client = GitHubInstallationTokenClient(guard, config, GitHubAppJwtSigner(9100001, secret))

    token = client.mint(now)
    assert token.expires_at - now == timedelta(hours=1)
    assert "synthetic-installation-token" not in repr(token)
    assert len(transport.requests) == 1
    request = transport.requests[0]
    payload = json.loads(request.body or b"{}")
    assert payload == {
        "permissions": {"contents": "write", "metadata": "read"},
        "repository_ids": [config.repository_id],
    }
    authorization = dict(request.headers)["Authorization"]
    encoded_jwt = authorization.removeprefix("Bearer ")
    encoded_header, encoded_claims, encoded_signature = encoded_jwt.split(".")
    claims = json.loads(_decode_segment(encoded_claims))
    assert claims["iss"] == "9100001"
    assert claims["exp"] - int(now.timestamp()) == 9 * 60
    private_key.public_key().verify(
        _decode_segment(encoded_signature),
        (encoded_header + "." + encoded_claims).encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    assert encoded_jwt not in repr(request)
    token.destroy()
    secret.destroy()


def test_t0204_blocks_cross_repository_and_nonfixed_release_surfaces_before_network() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100002, installation_id=8100002)
    transport = TokenTransport(_token_response(config.repository_id, now))
    guard = GitHubEndpointGuard(transport, config)
    guard.bind_repository(
        RepositoryLocator(config.repository_id, "synthetic-owner", "target-private")
    )
    before = len(transport.requests)
    forbidden = (
        HttpRequest(
            "GET",
            "https://api.github.com/repos/synthetic-owner/other-private/contents/MooMooAU/a.age",
        ),
        HttpRequest(
            "POST", "https://api.github.com/repos/synthetic-owner/target-private/issues", body=b"{}"
        ),
        HttpRequest(
            "POST",
            GITHUB_UPLOAD_ORIGIN
            + "/repos/synthetic-owner/target-private/releases/123/assets?name=history.png.age",
            body=_synthetic_age_envelope(),
        ),
    )
    for request in forbidden:
        with pytest.raises(GitHubBoundaryError):
            guard.send(request)
    assert len(transport.requests) == before

    fixed_upload = HttpRequest(
        "POST",
        GITHUB_UPLOAD_ORIGIN
        + f"/repos/synthetic-owner/target-private/releases/123/assets?name={LIVE_ASSET_NAME}",
        body=_synthetic_age_envelope(),
    )
    guard.send(fixed_upload)
    assert len(transport.requests) == before + 1
    assert guard.metrics.cross_repository_network_calls == 0


def test_t0204_rejects_overbroad_installation_token_response() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100003, installation_id=8100003)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    transport = TokenTransport(_token_response(config.repository_id, now, extra_repository=True))
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(transport, config),
        config,
        GitHubAppJwtSigner(9100003, secret),
    )
    with pytest.raises(GitHubInstallationTokenError) as error:
        client.mint(now)
    assert error.value.failure_class is InstallationTokenFailureClass.RESPONSE_SCOPE_REJECTED
    secret.destroy()


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (400, InstallationTokenFailureClass.REQUEST_REJECTED),
        (401, InstallationTokenFailureClass.AUTHENTICATION_REJECTED),
        (403, InstallationTokenFailureClass.AUTHORIZATION_REJECTED),
        (404, InstallationTokenFailureClass.INSTALLATION_NOT_FOUND),
        (422, InstallationTokenFailureClass.REQUEST_REJECTED),
        (500, InstallationTokenFailureClass.REMOTE_SERVICE_FAILED),
    ),
)
def test_t0204_classifies_token_rejection_without_response_body(
    status: int,
    expected: InstallationTokenFailureClass,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100004, installation_id=8100004)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(TokenTransport(HttpResponse(status, b"private-response")), config),
        config,
        GitHubAppJwtSigner(9100004, secret),
    )
    with pytest.raises(GitHubInstallationTokenError) as error:
        client.mint(now)
    assert error.value.failure_class is expected
    assert "private-response" not in repr(error.value)
    secret.destroy()


def test_t0204_classifies_malformed_token_success_without_dynamic_output() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100005, installation_id=8100005)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(TokenTransport(HttpResponse(201, b"private-invalid-json")), config),
        config,
        GitHubAppJwtSigner(9100005, secret),
    )
    with pytest.raises(GitHubInstallationTokenError) as error:
        client.mint(now)
    assert error.value.failure_class is InstallationTokenFailureClass.RESPONSE_INVALID
    assert "private-invalid-json" not in repr(error.value)
    secret.destroy()
