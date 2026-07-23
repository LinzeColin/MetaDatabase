from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from moomooau_archive.capacity import (
    CapacityLimits,
    CapacityPolicy,
    CapacitySnapshot,
    CapacityState,
)
from moomooau_archive.ephemeral import EphemeralPlaintextArena
from moomooau_archive.github_guard import (
    GitHubBoundaryError,
    GitHubEndpointGuard,
    RepositoryLocator,
    TargetRepositoryConfig,
)
from moomooau_archive.gmail_guard import GmailEndpointGuard, GmailEndpointRejected
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.secret_values import SecretText

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$")


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return HttpResponse(201, b"{}")


def test_t0604_gmail_and_github_broad_permissions_reject_before_network() -> None:
    gmail_transport = RecordingTransport()
    gmail = GmailEndpointGuard(gmail_transport)
    forbidden = (
        HttpRequest("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"),
        HttpRequest("DELETE", "https://gmail.googleapis.com/gmail/v1/users/me/messages/x"),
        HttpRequest("POST", "https://gmail.googleapis.com/gmail/v1/users/me/threads/x/trash"),
        HttpRequest("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/batchDelete"),
        HttpRequest("POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/x/modify"),
    )
    for request in forbidden:
        with pytest.raises(GmailEndpointRejected):
            gmail.send(request)
    assert gmail_transport.requests == []

    github_transport = RecordingTransport()
    config = TargetRepositoryConfig(repository_id=7_600_001, installation_id=8_600_001)
    github = GitHubEndpointGuard(github_transport, config)
    broad_body = json.dumps(
        {
            "permissions": {"contents": "write", "issues": "write", "metadata": "read"},
            "repository_ids": [config.repository_id, config.repository_id + 1],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(GitHubBoundaryError, match="broader"):
        github.send(
            HttpRequest(
                "POST",
                f"https://api.github.com/app/installations/{config.installation_id}/access_tokens",
                body=broad_body,
            )
        )
    github.bind_repository(
        RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")
    )
    with pytest.raises(GitHubBoundaryError, match="allowlisted"):
        github.send(
            HttpRequest(
                "GET",
                "https://api.github.com/repos/synthetic-owner/other-private/contents/Raw/object.age",
            )
        )
    assert github_transport.requests == []


@pytest.mark.parametrize(
    "raised",
    (None, RuntimeError, asyncio.CancelledError, TimeoutError, MemoryError),
)
def test_t0604_plaintext_arena_zeroes_normal_error_cancel_timeout_and_oom(
    raised: type[BaseException] | None,
) -> None:
    arena = EphemeralPlaintextArena()
    view = None
    try:
        with arena:
            view = arena.allocate(b"synthetic-sensitive-payload")
            assert bytes(view) == b"synthetic-sensitive-payload"
            if raised is not None:
                raise raised("synthetic exit")
    except BaseException as exc:
        assert raised is not None and isinstance(exc, raised)
    assert arena.closed
    assert arena.outstanding_bytes == 0
    assert view is not None and bytes(view) == bytes(len(view))


def test_t0604_unknown_capacity_and_red_capacity_never_authorize_writes() -> None:
    snapshot = CapacitySnapshot(
        git_repository_bytes=1_000_000,
        lfs_storage_bytes=1_000_000,
        largest_git_object_bytes=100_000,
        largest_lfs_object_bytes=100_000,
        live_release_asset_bytes=100_000,
    )
    unknown = CapacityPolicy().evaluate(
        snapshot,
        CapacityLimits(lfs_storage_budget_bytes=None, lfs_object_maximum_bytes=None),
    )
    assert unknown.state is CapacityState.UNKNOWN
    assert not unknown.write_allowed and not unknown.backfill_allowed
    red = CapacityPolicy().evaluate(
        CapacitySnapshot(
            git_repository_bytes=9_500_000_000,
            lfs_storage_bytes=1,
            largest_git_object_bytes=1,
            largest_lfs_object_bytes=1,
            live_release_asset_bytes=1,
        ),
        CapacityLimits(
            lfs_storage_budget_bytes=10 * 1024 * 1024 * 1024,
            lfs_object_maximum_bytes=2 * 1024 * 1024 * 1024,
        ),
    )
    assert red.state is CapacityState.RED
    assert not red.write_allowed


def test_t0604_dual_ci_is_sha_pinned_contents_read_only_and_has_no_data_persistence_channel() -> (
    None
):
    workflows = (
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage6-ci.yml",
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage6-model-assurance.yml",
    )
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        uses = re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", text, flags=re.MULTILINE)
        assert uses and all(PINNED_ACTION.fullmatch(item) for item in uses)
        lowered = text.casefold()
        assert "self-hosted" not in lowered
        assert "actions/cache" not in lowered
        assert "upload-artifact" not in lowered
        assert "download-artifact" not in lowered
        assert "schedule:" not in lowered
        assert "workflow_dispatch" not in lowered
        assert "contents: write" not in lowered
        assert "pull_request_target" not in lowered
        secret_names = re.findall(
            r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}",
            text,
        )
        if path.name == "moomooau-stage6-ci.yml":
            assert secret_names == ["MOOMOOAU_GOVERNANCE_DEPLOY_KEY"]
            assert "ssh-key: ${{ secrets.MOOMOOAU_GOVERNANCE_DEPLOY_KEY }}" in text
            assert "Reject fork pull requests before protected dependency checkout" in text
        else:
            assert secret_names == []
    software = workflows[0].read_text(encoding="utf-8")
    assert "security-events: write" in software
    assert "pip_audit" in software
    assert "dependency-review-action" in software
    assert "codeql-action/init" in software and "codeql-action/analyze" in software
    assert "--require-hashes" in software
    assert "--network none" in software and "--read-only" in software
    assert "requirements/stage6.lock" in software
    lock = (PROJECT_ROOT / "requirements/stage6.lock").read_text(encoding="utf-8")
    assert "hypothesis==6.156.7" in lock
    assert "--hash=sha256:" in lock


def test_t0604_secret_wrapper_never_renders_credential_value() -> None:
    value = "synthetic" + "-credential-material"
    secret = SecretText(value)
    try:
        assert value not in repr(secret)
        assert value not in str(secret)
    finally:
        secret.destroy()
