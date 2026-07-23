from __future__ import annotations

import base64
import json

import pytest
from stage4_support import (
    current_pointer,
    parser_profile,
    parser_registry_payload,
    signed_approval,
    stage4_context,
)

from moomooau_archive.age_stream import OfficialAgeStream, is_age_envelope
from moomooau_archive.attachment_inspector import AttachmentKind
from moomooau_archive.document_parser import (
    ParserProfileRegistry,
    SafeArtifactExtractor,
    StatementParser,
)
from moomooau_archive.github_guard import (
    CONTENT_APPEND_MESSAGE,
    CONTENT_POINTER_MESSAGE,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    RepositoryLocator,
    TargetRepositoryConfig,
    content_url,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.processed_commit import (
    MemoryProcessedCiphertextStore,
    ParserBlueGreenComparator,
    ProcessedCommitError,
    ProcessedCommitPlanner,
    ProcessedCommitSaga,
    ProcessedCommitState,
    PromotionAction,
    ProtectedPromotionApproval,
)
from moomooau_archive.processed_models import DocumentClass
from moomooau_archive.processed_product import ProcessedBundle, ProcessedProductBuilder
from moomooau_archive.secret_values import SecretBytes


def _bundle(*, parser_version: str, rename_summary: bool = False) -> ProcessedBundle:
    context = stage4_context(message_suffix="blue-green")
    profile = parser_profile(
        DocumentClass.DAILY_STATEMENT,
        AttachmentKind.CSV,
        parser_version=parser_version,
    )
    if rename_summary:
        value = json.loads(
            parser_registry_payload(
                DocumentClass.DAILY_STATEMENT,
                AttachmentKind.CSV,
                parser_version=parser_version,
            )
        )
        value["profiles"][0]["fields"][2]["output_name"] = "portfolio_value"
        registry = ParserProfileRegistry.from_json(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        changed = registry.current_for(DocumentClass.DAILY_STATEMENT)
        assert changed is not None
        profile = changed
    outcome = StatementParser().parse(
        context.envelope,
        context.classification,
        SafeArtifactExtractor().extract(context.attachments),
        profile,
    )
    return ProcessedProductBuilder().build(context.envelope, outcome)


def test_t0406_blue_green_keeps_v1_appends_v2_and_promotes_only_after_fourteen_days() -> None:
    v1 = _bundle(parser_version="1.0.0")
    v2 = _bundle(parser_version="2.0.0")
    assert v1.source_id == v2.source_id
    assert v1.business_root == v2.business_root
    assert v1.snapshot_root != v2.snapshot_root

    comparator = ParserBlueGreenComparator()
    initial = comparator.compare(v1, None, observed_days=0)
    assert initial.action is PromotionAction.INITIAL_PROMOTION
    planner = ProcessedCommitPlanner(
        OfficialAgeStream(),
        stage4_context(message_suffix="blue-green").recipient,
    )
    store = MemoryProcessedCiphertextStore()
    v1_plan = planner.plan(
        v1,
        initial,
        None,
        key_epoch="synthetic-epoch-1",
        expected_pointer_revision=None,
    )
    first = ProcessedCommitSaga(store).commit(v1_plan)
    assert first.state is ProcessedCommitState.PRIVATE_PROCESSED_COMMITTED_RECOVERY_PENDING
    assert first.current_pointer_updated
    incumbent = current_pointer(v1)
    pointer_path = f"MooMooAU/State/processed-current/{v1.source_id}.json.age"
    stored_pointer = store.fetch_current(pointer_path)
    assert stored_pointer is not None

    pending = comparator.shadow(v2, incumbent)
    assert pending.action is PromotionAction.CANDIDATE_SHADOW_ONLY
    pending_plan = planner.plan(
        v2,
        pending,
        incumbent,
        key_epoch="synthetic-epoch-1",
        expected_pointer_revision=stored_pointer.revision,
    )
    pending_result = ProcessedCommitSaga(store).commit(pending_plan)
    assert pending_result.state is ProcessedCommitState.CANDIDATE_COMMITTED_CURRENT_UNCHANGED
    assert not pending_result.current_pointer_updated
    assert store.fetch_current(pointer_path) == stored_pointer

    promotion = comparator.compare(v2, incumbent, observed_days=0)
    assert promotion.action is PromotionAction.SEMANTICALLY_EQUAL_PROMOTION
    promotion_plan = planner.plan(
        v2,
        promotion,
        incumbent,
        key_epoch="synthetic-epoch-1",
        expected_pointer_revision=stored_pointer.revision,
    )
    promoted = ProcessedCommitSaga(store).commit(promotion_plan)
    assert promoted.current_pointer_updated
    names = store.immutable_names()
    assert any("/1.0.0/" in name for name in names)
    assert any("/2.0.0/" in name for name in names)
    assert len(store.current_names()) == 1
    assert all(is_age_envelope(value) for value in store.ciphertexts())
    assert not promoted.remote_recovery_verified
    assert not promoted.public_publish_eligible
    assert not promoted.m3_eligible

    retried = ProcessedCommitSaga(store).commit(promotion_plan)
    assert retried.created_count == 0
    assert retried.existing_count == retried.immutable_count
    assert not retried.current_pointer_updated


def test_t0406_changed_business_output_requires_bound_protected_approval() -> None:
    v1 = _bundle(parser_version="1.0.0")
    changed = _bundle(parser_version="2.0.0", rename_summary=True)
    incumbent = current_pointer(v1)
    comparator = ParserBlueGreenComparator()
    required = comparator.compare(changed, incumbent, observed_days=0)
    assert required.action is PromotionAction.PROTECTED_APPROVAL_REQUIRED
    assert not required.promote_current

    key = SecretBytes(b"synthetic-protected-approval-key-material")
    try:
        payload, signature = signed_approval(incumbent, changed, key)
        with pytest.raises(ProcessedCommitError, match="signature"):
            ProtectedPromotionApproval.verify_signed_payload(payload, "0" * 64, key)
        approval = ProtectedPromotionApproval.verify_signed_payload(payload, signature, key)
    finally:
        key.destroy()
    approved = comparator.compare(
        changed,
        incumbent,
        observed_days=0,
        approval=approval,
    )
    assert approved.action is PromotionAction.PROTECTED_APPROVED_PROMOTION
    assert approved.promote_current

    planner = ProcessedCommitPlanner(
        OfficialAgeStream(),
        stage4_context(message_suffix="blue-green").recipient,
    )
    reused_version = _bundle(parser_version="1.0.0", rename_summary=True)
    reuse_conflict = comparator.compare(reused_version, incumbent, observed_days=0)
    assert reuse_conflict.action is PromotionAction.VERSION_REUSE_CONFLICT
    with pytest.raises(ProcessedCommitError, match="cannot be committed"):
        planner.plan(
            reused_version,
            reuse_conflict,
            incumbent,
            key_epoch="synthetic-epoch-1",
            expected_pointer_revision="a" * 40,
        )

    v2_incumbent = current_pointer(_bundle(parser_version="2.0.0"))
    rollback = comparator.compare(v1, v2_incumbent, observed_days=0)
    assert rollback.action is PromotionAction.VERSION_ROLLBACK_BLOCKED
    with pytest.raises(ProcessedCommitError, match="cannot be committed"):
        planner.plan(
            v1,
            rollback,
            v2_incumbent,
            key_epoch="synthetic-epoch-1",
            expected_pointer_revision="a" * 40,
        )


def test_t0406_partial_immutable_failure_retries_to_one_complete_current() -> None:
    class FailOnceProcessedStore(MemoryProcessedCiphertextStore):
        def __init__(self) -> None:
            super().__init__()
            self.failed_once = False

        def append_immutable(self, relative_path: str, ciphertext: bytes) -> bool:
            if not self.failed_once and self.write_calls == 1:
                self.failed_once = True
                raise ProcessedCommitError("synthetic one-shot Processed write failed")
            return super().append_immutable(relative_path, ciphertext)

    bundle = _bundle(parser_version="1.0.0")
    decision = ParserBlueGreenComparator().compare(bundle, None, observed_days=0)
    context = stage4_context(message_suffix="blue-green")
    plan = ProcessedCommitPlanner(OfficialAgeStream(), context.recipient).plan(
        bundle,
        decision,
        None,
        key_epoch="synthetic-epoch-1",
        expected_pointer_revision=None,
    )
    store = FailOnceProcessedStore()
    saga = ProcessedCommitSaga(store)
    with pytest.raises(ProcessedCommitError, match="one-shot"):
        saga.commit(plan)
    assert len(store.immutable_names()) == 1
    assert store.current_names() == ()

    recovered = saga.commit(plan)
    assert recovered.existing_count == 1
    assert recovered.created_count == recovered.immutable_count - 1
    assert recovered.current_pointer_updated
    assert len(store.current_names()) == 1
    assert all(is_age_envelope(value) for value in store.ciphertexts())


def test_t0406_github_guard_allows_sha_only_for_the_encrypted_processed_current_pointer() -> None:
    class RecordingTransport:
        def __init__(self) -> None:
            self.requests: list[HttpRequest] = []

        def send(self, request: HttpRequest) -> HttpResponse:
            self.requests.append(request)
            return HttpResponse(200, b"{}")

    v1 = _bundle(parser_version="1.0.0")
    context = stage4_context(message_suffix="blue-green")
    decision = ParserBlueGreenComparator().compare(v1, None, observed_days=0)
    plan = ProcessedCommitPlanner(OfficialAgeStream(), context.recipient).plan(
        v1,
        decision,
        None,
        key_epoch="synthetic-epoch-1",
        expected_pointer_revision=None,
    )
    pointer = plan.current_pointer
    assert pointer is not None
    transport = RecordingTransport()
    config = TargetRepositoryConfig(repository_id=7_400_001, installation_id=8_400_001)
    guard = GitHubEndpointGuard(transport, config)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")
    guard.bind_repository(locator)
    revision = "a" * 40
    body = json.dumps(
        {
            "content": base64.b64encode(pointer.ciphertext).decode("ascii"),
            "message": CONTENT_POINTER_MESSAGE,
            "sha": revision,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    guard.send(HttpRequest("PUT", content_url(locator, pointer.relative_path), body=body))
    assert len(transport.requests) == 1

    append_with_sha = json.dumps(
        {
            "content": base64.b64encode(pointer.ciphertext).decode("ascii"),
            "message": CONTENT_APPEND_MESSAGE,
            "sha": revision,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with pytest.raises(GitHubBoundaryError, match="append-only"):
        guard.send(
            HttpRequest(
                "PUT",
                content_url(locator, "MooMooAU/Raw/messages/2026/01/object.eml.age"),
                body=append_with_sha,
            )
        )
    assert len(transport.requests) == 1
