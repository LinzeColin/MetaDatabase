from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace

import pytest
from stage3_support import make_raw_message, synthetic_pdf

from moomooau_archive.age_stream import OfficialAgeStream, is_age_envelope
from moomooau_archive.attachment_inspector import AttachmentInspector
from moomooau_archive.canonical_raw import CanonicalRaw
from moomooau_archive.github_guard import (
    CONTENT_APPEND_MESSAGE,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    RepositoryLocator,
    TargetRepositoryConfig,
    content_url,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.raw_commit import (
    MemoryAppendOnlyCiphertextStore,
    OpaqueIdFactory,
    RawCommitError,
    RawCommitPlanner,
    RawCommitSaga,
    RawCommitState,
    RawObjectRole,
)
from moomooau_archive.recovery import AgeIdentityGenerator
from moomooau_archive.secret_values import SecretBytes


def _canonical() -> CanonicalRaw:
    raw = make_raw_message(
        message_id="synthetic-commit-1",
        attachments=(
            ("first.pdf", "application", "octet-stream", synthetic_pdf()),
            ("second.pdf", "application", "octet-stream", synthetic_pdf()),
        ),
    )
    return CanonicalRaw(
        message_id="synthetic-commit-1",
        thread_id="thread-synthetic-commit-1",
        internal_date_ms=1_767_225_600_000,
        label_ids=("INBOX",),
        plaintext_sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        data=raw,
    )


def _planner() -> tuple[RawCommitPlanner, SecretBytes]:
    generated = AgeIdentityGenerator().generate()
    key = SecretBytes(b"synthetic-opaque-key-material-32b")
    try:
        planner = RawCommitPlanner(
            OfficialAgeStream(),
            generated.recipient,
            OpaqueIdFactory(key),
        )
    finally:
        generated.destroy()
    return planner, key


def test_t0307_content_addressed_raw_commit_is_encrypted_append_only_and_idempotent() -> None:
    canonical = _canonical()
    report = AttachmentInspector().inspect(canonical)
    planner, key = _planner()
    try:
        first_plan = planner.plan(canonical, report, key_epoch="synthetic-epoch-1")
        second_plan = planner.plan(canonical, report, key_epoch="synthetic-epoch-1")
        with pytest.raises(RawCommitError, match="does not belong"):
            planner.plan(
                canonical,
                replace(report, canonical_plaintext_sha256="0" * 64),
                key_epoch="synthetic-epoch-1",
            )
    finally:
        key.destroy()

    assert first_plan.opaque_message_id == second_plan.opaque_message_id
    assert first_plan.content_id == second_plan.content_id
    assert [item.relative_path for item in first_plan.objects] == [
        item.relative_path for item in second_plan.objects
    ]
    assert len(first_plan.objects) == 3
    assert [item.role for item in first_plan.objects].count(RawObjectRole.ATTACHMENT) == 1
    assert first_plan.objects[-1].role is RawObjectRole.MANIFEST
    assert any(
        first.ciphertext != second.ciphertext
        for first, second in zip(first_plan.objects, second_plan.objects, strict=True)
    )
    assert all(is_age_envelope(item.ciphertext) for item in first_plan.objects)
    assert all(canonical.data not in item.ciphertext for item in first_plan.objects)

    store = MemoryAppendOnlyCiphertextStore()
    first_result = RawCommitSaga(store).commit(first_plan)
    second_result = RawCommitSaga(store).commit(second_plan)
    assert first_result.state is RawCommitState.PRIVATE_COMMITTED_RECOVERY_PENDING
    assert first_result.created_count == first_result.object_count == 3
    assert first_result.existing_count == 0
    assert second_result.created_count == 0
    assert second_result.existing_count == second_result.object_count == 3
    assert store.create_calls == 3
    assert not first_result.remote_recovery_verified
    assert not first_result.public_publish_eligible
    assert not first_result.m3_eligible
    assert all(
        name.startswith("MooMooAU/") and name.endswith(".age") for name in store.object_names()
    )


def test_t0307_partial_private_failure_is_resumable_without_overwrite() -> None:
    class FailOnceStore(MemoryAppendOnlyCiphertextStore):
        def __init__(self) -> None:
            super().__init__()
            self.failed = False

        def create(self, relative_path: str, ciphertext: bytes) -> bool:
            if self.create_calls == 1 and not self.failed:
                self.failed = True
                raise RawCommitError("synthetic injected failure")
            return super().create(relative_path, ciphertext)

    canonical = _canonical()
    planner, key = _planner()
    try:
        plan = planner.plan(
            canonical,
            AttachmentInspector().inspect(canonical),
            key_epoch="synthetic-epoch-1",
        )
    finally:
        key.destroy()
    store = FailOnceStore()
    with pytest.raises(RawCommitError, match="injected"):
        RawCommitSaga(store).commit(plan)
    assert len(store.object_names()) == 1
    recovered = RawCommitSaga(store).commit(plan)
    assert recovered.existing_count == 1
    assert recovered.created_count == recovered.object_count - 1
    assert len(store.object_names()) == recovered.object_count


def test_t0307_github_contents_guard_blocks_plaintext_before_transport() -> None:
    class RecordingTransport:
        def __init__(self) -> None:
            self.requests: list[HttpRequest] = []

        def send(self, request: HttpRequest) -> HttpResponse:
            self.requests.append(request)
            return HttpResponse(201, b"{}")

    transport = RecordingTransport()
    config = TargetRepositoryConfig(repository_id=7_200_001, installation_id=8_200_001)
    guard = GitHubEndpointGuard(transport, config)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")
    guard.bind_repository(locator)
    plaintexts = (
        b"synthetic plaintext",
        b"prefix age-encryption.org/v1\nsynthetic plaintext",
        b"age-encryption.org/v1\nsynthetic plaintext",
    )
    for plaintext in plaintexts:
        assert not is_age_envelope(plaintext)
        plaintext_body = json.dumps(
            {
                "content": base64.b64encode(plaintext).decode("ascii"),
                "message": CONTENT_APPEND_MESSAGE,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        with pytest.raises(GitHubBoundaryError, match="age envelope"):
            guard.send(
                HttpRequest(
                    "PUT",
                    content_url(locator, "MooMooAU/Raw/messages/2026/01/object.eml.age"),
                    body=plaintext_body,
                )
            )
    assert transport.requests == []
    assert guard.metrics.cross_repository_network_calls == 0
