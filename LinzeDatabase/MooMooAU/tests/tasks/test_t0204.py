from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from urllib.parse import urlsplit

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


class SequenceTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected synthetic GitHub request")
        return self.responses.pop(0)


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
    repository_id: int,
    now: datetime,
    *,
    extra_repository: bool = False,
    permissions: object = None,
) -> HttpResponse:
    repositories = [{"id": repository_id, "name": "synthetic-target"}]
    if extra_repository:
        repositories.append({"id": repository_id + 1})
    response_permissions = (
        {"contents": "write", "metadata": "read"} if permissions is None else permissions
    )
    return HttpResponse(
        201,
        json.dumps(
            {
                "token": "synthetic-installation-token",
                "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                "repositories": repositories,
                "permissions": response_permissions,
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


def test_t0204_accepts_token_response_without_mandatory_metadata_echo() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100010, installation_id=8100010)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    transport = TokenTransport(
        _token_response(config.repository_id, now, permissions={"contents": "write"})
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(transport, config),
        config,
        GitHubAppJwtSigner(9100010, secret),
    )

    token = client.mint(now)

    assert token.expires_at - now == timedelta(hours=1)
    token.destroy()
    secret.destroy()


def test_t0204_accepts_optional_scope_echo_absence_after_exact_repository_probe() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    server_now = now + timedelta(seconds=2)
    config = TargetRepositoryConfig(repository_id=7100012, installation_id=8100012)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    transport = SequenceTransport(
        [
            HttpResponse(
                201,
                json.dumps(
                    {
                        "token": "synthetic-installation-token",
                        "expires_at": (server_now + timedelta(hours=1))
                        .isoformat()
                        .replace("+00:00", "Z"),
                    }
                ).encode(),
                (("Date", format_datetime(server_now, usegmt=True)),),
            ),
            HttpResponse(
                200,
                json.dumps(
                    {
                        "total_count": 1,
                        "repositories": [{"id": config.repository_id}],
                    }
                ).encode(),
            ),
        ]
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(transport, config),
        config,
        GitHubAppJwtSigner(9100012, secret),
    )

    token = client.mint(now)

    assert token.expires_at - server_now == timedelta(hours=1)
    assert [urlsplit(request.url).path for request in transport.requests] == [
        f"/app/installations/{config.installation_id}/access_tokens",
        "/installation/repositories",
    ]
    token.destroy()
    secret.destroy()


def test_t0204_rejects_optional_scope_echo_absence_when_repository_probe_is_not_exact() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100013, installation_id=8100013)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    transport = SequenceTransport(
        [
            HttpResponse(
                201,
                json.dumps(
                    {
                        "token": "synthetic-installation-token",
                        "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                    }
                ).encode(),
                (("Date", format_datetime(now, usegmt=True)),),
            ),
            HttpResponse(
                200,
                json.dumps(
                    {
                        "total_count": 2,
                        "repositories": [
                            {"id": config.repository_id},
                            {"id": config.repository_id + 1},
                        ],
                    }
                ).encode(),
            ),
        ]
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(transport, config),
        config,
        GitHubAppJwtSigner(9100013, secret),
    )

    with pytest.raises(GitHubInstallationTokenError) as error:
        client.mint(now)

    assert error.value.failure_class is InstallationTokenFailureClass.RESPONSE_SCOPE_REJECTED
    assert len(transport.requests) == 2
    secret.destroy()


def test_t0204_rejects_token_response_with_unbounded_server_date() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    server_now = now + timedelta(minutes=6)
    config = TargetRepositoryConfig(repository_id=7100014, installation_id=8100014)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    transport = TokenTransport(
        HttpResponse(
            201,
            json.dumps(
                {
                    "token": "synthetic-installation-token",
                    "expires_at": (server_now + timedelta(hours=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            ).encode(),
            (("Date", format_datetime(server_now, usegmt=True)),),
        )
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(transport, config),
        config,
        GitHubAppJwtSigner(9100014, secret),
    )

    with pytest.raises(GitHubInstallationTokenError) as error:
        client.mint(now)

    assert error.value.failure_class is InstallationTokenFailureClass.RESPONSE_INVALID
    assert len(transport.requests) == 1
    secret.destroy()


@pytest.mark.parametrize(
    "permissions",
    (
        {"contents": "read"},
        {"metadata": "read"},
        {"contents": "write", "metadata": "write"},
        {"contents": "write", "issues": "read"},
    ),
)
def test_t0204_rejects_weak_or_additional_token_response_permissions(
    permissions: dict[str, str],
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100011, installation_id=8100011)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(
            TokenTransport(_token_response(config.repository_id, now, permissions=permissions)),
            config,
        ),
        config,
        GitHubAppJwtSigner(9100011, secret),
    )

    with pytest.raises(GitHubInstallationTokenError) as error:
        client.mint(now)

    assert error.value.failure_class is InstallationTokenFailureClass.RESPONSE_SCOPE_REJECTED
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


def test_t0204_recovers_stale_installation_id_only_from_one_exact_installation() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100006, installation_id=8100006)
    discovered_installation_id = 8100099
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    transport = SequenceTransport(
        [
            HttpResponse(404, b"private-not-found-response"),
            HttpResponse(
                200,
                json.dumps(
                    [
                        {
                            "id": discovered_installation_id,
                            "permissions": {"contents": "write", "metadata": "read"},
                            "repository_selection": "selected",
                            "suspended_at": None,
                        }
                    ],
                    sort_keys=True,
                ).encode(),
            ),
            _token_response(config.repository_id, now),
        ]
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(transport, config),
        config,
        GitHubAppJwtSigner(9100006, secret),
    )

    token = client.mint(now)

    assert [urlsplit(item.url).path for item in transport.requests] == [
        f"/app/installations/{config.installation_id}/access_tokens",
        "/app/installations",
        f"/app/installations/{discovered_installation_id}/access_tokens",
    ]
    assert urlsplit(transport.requests[1].url).query == "per_page=2"
    assert transport.requests[0].body == transport.requests[2].body
    token.destroy()
    secret.destroy()


def test_t0204_classifies_target_absent_from_discovered_installation() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100009, installation_id=8100009)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    transport = SequenceTransport(
        [
            HttpResponse(404, b"{}"),
            HttpResponse(
                200,
                json.dumps(
                    [
                        {
                            "id": 8100199,
                            "permissions": {"contents": "write", "metadata": "read"},
                            "repository_selection": "selected",
                            "suspended_at": None,
                        }
                    ],
                    sort_keys=True,
                ).encode(),
            ),
            HttpResponse(404, b"private-target-absent-response"),
        ]
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(transport, config),
        config,
        GitHubAppJwtSigner(9100009, secret),
    )

    with pytest.raises(GitHubInstallationTokenError) as error:
        client.mint(now)

    assert error.value.failure_class is InstallationTokenFailureClass.INSTALLATION_NOT_FOUND
    assert "private-target-absent-response" not in repr(error.value)
    secret.destroy()


@pytest.mark.parametrize(
    ("installations", "expected"),
    (
        ([], InstallationTokenFailureClass.INSTALLATION_ZERO),
        (
            [
                {
                    "id": 8100101,
                    "permissions": {"contents": "write", "metadata": "read"},
                    "repository_selection": "selected",
                    "suspended_at": None,
                },
                {
                    "id": 8100102,
                    "permissions": {"contents": "write", "metadata": "read"},
                    "repository_selection": "selected",
                    "suspended_at": None,
                },
            ],
            InstallationTokenFailureClass.INSTALLATION_MULTIPLE,
        ),
        (
            [
                {
                    "id": 8100103,
                    "permissions": {"contents": "read", "metadata": "read"},
                    "repository_selection": "selected",
                    "suspended_at": None,
                }
            ],
            InstallationTokenFailureClass.INSTALLATION_PERMISSIONS_REJECTED,
        ),
        (
            [
                {
                    "id": 8100104,
                    "permissions": {"contents": "write", "metadata": "read"},
                    "repository_selection": "all",
                    "suspended_at": None,
                }
            ],
            InstallationTokenFailureClass.INSTALLATION_SELECTION_REJECTED,
        ),
        (
            [
                {
                    "id": 8100105,
                    "permissions": {"contents": "write", "metadata": "read"},
                    "repository_selection": "selected",
                    "suspended_at": "2026-01-01T00:00:00Z",
                }
            ],
            InstallationTokenFailureClass.INSTALLATION_SUSPENDED,
        ),
    ),
)
def test_t0204_rejects_nonunique_or_overbroad_installation_discovery(
    installations: list[dict[str, object]],
    expected: InstallationTokenFailureClass,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100007, installation_id=8100007)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    secret = SecretBytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    transport = SequenceTransport(
        [
            HttpResponse(404, b"{}"),
            HttpResponse(200, json.dumps(installations, sort_keys=True).encode()),
        ]
    )
    client = GitHubInstallationTokenClient(
        GitHubEndpointGuard(transport, config),
        config,
        GitHubAppJwtSigner(9100007, secret),
    )

    with pytest.raises(GitHubInstallationTokenError) as error:
        client.mint(now)

    assert error.value.failure_class is expected
    assert len(transport.requests) == 2
    secret.destroy()


def test_t0204_blocks_unbounded_installation_discovery_before_network() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = TargetRepositoryConfig(repository_id=7100008, installation_id=8100008)
    transport = TokenTransport(_token_response(config.repository_id, now))
    guard = GitHubEndpointGuard(transport, config)

    for url in (
        "https://api.github.com/app/installations",
        "https://api.github.com/app/installations?per_page=100",
        "https://api.github.com/app/installations?per_page=2&since=1",
    ):
        with pytest.raises(GitHubBoundaryError, match="bounded"):
            guard.send(HttpRequest("GET", url))
    assert transport.requests == []
