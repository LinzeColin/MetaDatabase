from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from moomooau_archive.github_guard import (
    GitHubBoundaryError,
    GitHubEndpointGuard,
    InstallationToken,
    RepositoryResolver,
    TargetRepositoryConfig,
    content_url,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.secret_values import SecretText


class QueueTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return self.responses.pop(0) if self.responses else HttpResponse(200, b"{}")


def _repository_response(
    repository_id: int, full_name: str, *, private: bool = True
) -> HttpResponse:
    body = json.dumps(
        {"id": repository_id, "full_name": full_name, "private": private},
        sort_keys=True,
    ).encode()
    return HttpResponse(200, body)


def _synthetic_token() -> InstallationToken:
    return InstallationToken(
        SecretText("synthetic-" + "resolver-value"),
        datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=30),
    )


def test_t0203_repository_rename_is_resolved_by_immutable_id() -> None:
    config = TargetRepositoryConfig(repository_id=7000001, installation_id=8000001)
    transport = QueueTransport(
        [
            _repository_response(config.repository_id, "synthetic-owner/first-name"),
            _repository_response(config.repository_id, "synthetic-owner/renamed-database"),
        ]
    )
    guard = GitHubEndpointGuard(transport, config)
    resolver = RepositoryResolver(guard, config)
    token = _synthetic_token()

    try:
        first = resolver.resolve(token)
        old_url = content_url(first, "MooMooAU/Raw/synthetic.eml.age")
        second = resolver.resolve(token)
        new_url = content_url(second, "MooMooAU/Raw/synthetic.eml.age")
        guard.send(HttpRequest("GET", new_url))
    finally:
        token.destroy()

    assert first.repository_id == second.repository_id == config.repository_id
    assert first.name != second.name
    assert old_url != new_url
    assert "renamed-database" not in repr(second)
    assert "resolver-value" not in repr(transport.requests[0])
    before = len(transport.requests)
    with pytest.raises(GitHubBoundaryError):
        guard.send(HttpRequest("GET", old_url))
    assert len(transport.requests) == before
    assert guard.metrics.cross_repository_network_calls == 0


def test_t0203_rejects_public_or_out_of_namespace_repository_targets() -> None:
    config = TargetRepositoryConfig(repository_id=7000002, installation_id=8000002)
    public_transport = QueueTransport(
        [_repository_response(config.repository_id, "synthetic-owner/public-target", private=False)]
    )
    public_token = _synthetic_token()
    try:
        with pytest.raises(GitHubBoundaryError, match="identity response"):
            RepositoryResolver(GitHubEndpointGuard(public_transport, config), config).resolve(
                public_token
            )
    finally:
        public_token.destroy()

    private_transport = QueueTransport(
        [_repository_response(config.repository_id, "synthetic-owner/private-target")]
    )
    guard = GitHubEndpointGuard(private_transport, config)
    private_token = _synthetic_token()
    try:
        locator = RepositoryResolver(guard, config).resolve(private_token)
    finally:
        private_token.destroy()
    before = len(private_transport.requests)
    for relative_path in (
        "Other/root.age",
        "MooMooAU/../Other/root.age",
        "MooMooAU/%2e%2e/root.age",
    ):
        with pytest.raises(GitHubBoundaryError):
            content_url(locator, relative_path)
    assert len(private_transport.requests) == before
