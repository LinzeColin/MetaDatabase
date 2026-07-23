from __future__ import annotations

import asyncio
import io
import json
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

import pikepdf
import pytest
from stage5_support import (
    SyntheticM3Transport,
    pre_m3_message,
    recovery_context,
    timeline_event,
)
from stage6_support import (
    ExpiredHistoryClient,
    GeneratedMailboxClient,
    StaticDiscoverer,
    canonical_with_attachments,
    public_document,
)

import moomooau_archive.ephemeral as ephemeral_module
from moomooau_archive.adapters import EphemeralAgeSession
from moomooau_archive.age_stream import OfficialAgeStream
from moomooau_archive.attachment_inspector import AttachmentInspector
from moomooau_archive.capacity import (
    CapacityAssessment,
    CapacityLimits,
    CapacityPolicy,
    CapacitySnapshot,
)
from moomooau_archive.document_parser import ExtractionState, SafeArtifactExtractor
from moomooau_archive.ephemeral import EphemeralPlaintextArena
from moomooau_archive.gmail_discovery import (
    FullMailboxDiscoverer,
    GmailReconciler,
    MessageRef,
    ReconcileMode,
    SyncState,
)
from moomooau_archive.gmail_guard import GmailEndpointGuard
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.kill_switch import KillId, KillSwitch
from moomooau_archive.load_probe import LoadProbeError, LogicalObjectIndex, UpsertResult
from moomooau_archive.m3 import (
    ExactMessageTrashExecutor,
    GmailLabelConfirmationClient,
    M3Error,
    M3State,
    MutationBudget,
    MutationPhase,
)
from moomooau_archive.model_boundary import (
    AutoAction,
    CodexAutoMonitor,
    PublicHealthObservation,
)
from moomooau_archive.operation_gate import (
    OperationalGate,
    OperationGateError,
    SensitiveOperation,
)
from moomooau_archive.public_inventory import PublicInventoryError, PublicRunState
from moomooau_archive.public_inventory import _validate_public_shape as validate_public_shape
from moomooau_archive.publication_saga import (
    PrivateFirstPublicationSaga,
    PrivateState,
    PublicationSagaError,
    PublicState,
)
from moomooau_archive.recovery import AgeIdentityGenerator
from moomooau_archive.remote_recovery_gate import (
    OfficialAgeDecryptor,
    RemoteRecoveryError,
    RemoteRecoveryGate,
)
from moomooau_archive.retry import (
    BoundedRetryPolicy,
    RetryExhausted,
    RetryOperation,
    send_with_retry,
)
from moomooau_archive.run_schedule import RunPlanner, RunTrigger
from moomooau_archive.secret_values import SecretText
from moomooau_archive.timeline_publish import (
    MemoryTimelineReleaseRemote,
    MemoryTimelineStateStore,
    SingleLatestTimelinePublisher,
    TimelinePublishAction,
    TimelinePublishError,
)
from moomooau_archive.timeline_render import DeterministicTimelineRenderer


class SequenceTransport:
    def __init__(self, responses: tuple[HttpResponse, ...]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def send(self, request: HttpRequest) -> HttpResponse:
        del request
        self.calls += 1
        if not self._responses:
            raise AssertionError("synthetic response sequence exhausted")
        return self._responses.pop(0)


def _record_operation(destination: list[str], operation: SensitiveOperation) -> None:
    destination.append(operation.value)


def test_t0608_ch01_ch02_bounded_remote_retry() -> None:
    request = HttpRequest("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages")
    delays: list[int] = []
    transient = SequenceTransport(
        (
            HttpResponse(429, b"{}", (("Retry-After", "1"),)),
            HttpResponse(503, b"{}"),
            HttpResponse(200, b"{}"),
        )
    )
    result = send_with_retry(
        transient.send,
        request,
        RetryOperation.READ,
        sleeper=delays.append,
    )
    assert result.status == 200
    assert transient.calls == 3
    assert delays == [1, 2]

    exhausted = SequenceTransport((HttpResponse(500, b"{}"), HttpResponse(503, b"{}")))
    delays.clear()
    with pytest.raises(RetryExhausted):
        send_with_retry(
            exhausted.send,
            request,
            RetryOperation.READ,
            policy=BoundedRetryPolicy(maximum_attempts=2),
            sleeper=delays.append,
        )
    assert exhausted.calls == 2
    assert delays == [1]
    saga = PrivateFirstPublicationSaga()
    assert saga.snapshot.private_state is PrivateState.NOT_STARTED
    assert saga.snapshot.source_mutation_attempts == 0
    retry = SequenceTransport((HttpResponse(200, b"{}"),))
    assert send_with_retry(retry.send, request, RetryOperation.READ).status == 200


def test_t0608_ch03_ch04_ch18_reconciliation_recovery() -> None:
    refs = tuple(MessageRef(f"msg-{index:03d}", f"thread-{index:03d}") for index in range(8))
    expired_client = ExpiredHistoryClient(refs)
    expired = GmailReconciler(
        expired_client,  # type: ignore[arg-type]
        StaticDiscoverer(refs),  # type: ignore[arg-type]
    ).reconcile(
        SyncState("8000", refs[:3]),
        now_sydney=datetime(2026, 7, 20, 5, tzinfo=ZoneInfo("Australia/Sydney")),
    )
    assert expired.mode is ReconcileMode.FULL_HISTORY_EXPIRED
    assert expired.state.known_refs == refs

    interrupted_client = GeneratedMailboxClient(pages=4, refs_per_page=25, fail_at_page=2)
    with pytest.raises(ConnectionError):
        FullMailboxDiscoverer(interrupted_client).scan()  # type: ignore[arg-type]
    completed = FullMailboxDiscoverer(
        GeneratedMailboxClient(pages=4, refs_per_page=25),  # type: ignore[arg-type]
    ).scan()
    assert len(completed.refs) == 100
    index = LogicalObjectIndex()
    for ref in completed.refs + tuple(reversed(completed.refs)):
        index.upsert(ref.message_id, (ref.message_id.encode().hex() + "0" * 64)[:64])
    assert index.object_count == 100

    manual = GmailReconciler(
        expired_client,  # type: ignore[arg-type]
        StaticDiscoverer(refs),  # type: ignore[arg-type]
    ).reconcile(
        SyncState("8000", refs),
        now_sydney=datetime(2026, 7, 21, 5, tzinfo=ZoneInfo("Australia/Sydney")),
        force_full=True,
    )
    assert manual.mode is ReconcileMode.FULL_MANUAL
    assert manual.state.known_refs == refs
    delayed = RunPlanner().plan(
        RunTrigger.SCHEDULE,
        started_at_utc=datetime(2026, 7, 19, 18, 37, tzinfo=UTC),
        last_successful_run_date_sydney=datetime(2026, 7, 17, tzinfo=UTC).date(),
    )
    assert delayed.schedule_delay_minutes == 7
    assert delayed.missed_run_days == 2
    assert delayed.catch_up_required
    assert delayed.to_public_dict()["platform_sla_claimed"] is False


def test_t0608_ch05_ch06_private_first_and_compensation() -> None:
    failed = PrivateFirstPublicationSaga()
    failed.record_private(committed=False, recovery_verified=False)
    with pytest.raises(PublicationSagaError):
        failed.record_public(remote_verified=True)
    with pytest.raises(PublicationSagaError):
        failed.record_source_mutation(confirmed=True)
    assert not failed.snapshot.public_success_claimed
    assert failed.snapshot.source_mutation_attempts == 0

    pending = PrivateFirstPublicationSaga()
    pending.record_private(committed=True, recovery_verified=True)
    pending.record_public(remote_verified=False)
    before_reconciliation = pending.snapshot
    assert before_reconciliation.public_state is PublicState.PENDING_RECONCILIATION
    assert not before_reconciliation.public_success_claimed
    pending.record_source_mutation(confirmed=True)
    pending.reconcile_public(remote_verified=True)
    after_reconciliation = pending.snapshot
    assert after_reconciliation.public_state is PublicState.VERIFIED
    assert after_reconciliation.private_attempts == 1
    assert after_reconciliation.public_attempts == 2
    assert after_reconciliation.source_mutation_attempts == 1


def test_t0608_ch07_ch08_recovery_corruption_and_wrong_identity() -> None:
    with recovery_context() as context:
        first = context.raw_plan.objects[0]
        context.reader.replace_for_test(first.relative_path, b"x" + first.ciphertext[1:])
        with pytest.raises(RemoteRecoveryError, match="ciphertext"):
            RemoteRecoveryGate(context.reader, context.decryptor).verify(
                context.canonical,
                context.first_verification,
                context.raw_plan,
                context.processed_bundle,
                context.processed_plan,
            )
        context.reader.replace_for_test(first.relative_path, first.ciphertext)

        wrong = AgeIdentityGenerator().generate()
        temporary = tempfile.TemporaryDirectory(prefix="moomooau-stage6-wrong-age-")
        try:
            identity_path = Path(temporary.name) / "identity.agekey"
            identity_path.write_bytes(wrong.identity.reveal())
            identity_path.chmod(0o600)
            wrong_decryptor = OfficialAgeDecryptor(
                OfficialAgeStream(),
                identity_path,
                allowed_tmpfs_roots=(Path(temporary.name),),
            )
            with pytest.raises(RemoteRecoveryError, match="decryption"):
                RemoteRecoveryGate(context.reader, wrong_decryptor).verify(
                    context.canonical,
                    context.first_verification,
                    context.raw_plan,
                    context.processed_bundle,
                    context.processed_plan,
                )
        finally:
            wrong.destroy()
            temporary.cleanup()

        proof = RemoteRecoveryGate(context.reader, context.decryptor).verify(
            context.canonical,
            context.first_verification,
            context.raw_plan,
            context.processed_bundle,
            context.processed_plan,
        )
        assert proof.recovered_object_count >= 2


def _encrypted_text_pdf(password: str) -> bytes:
    sink = io.BytesIO()
    with pikepdf.Pdf.new() as document:
        page = document.add_blank_page(page_size=(200, 200))
        font = document.make_indirect(
            pikepdf.Dictionary(
                Type=pikepdf.Name("/Font"),
                Subtype=pikepdf.Name("/Type1"),
                BaseFont=pikepdf.Name("/Helvetica"),
            )
        )
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
        page.Contents = document.make_stream(b"BT /F1 12 Tf 20 100 Td (synthetic statement) Tj ET")
        document.save(
            sink,
            static_id=True,
            encryption=pikepdf.Encryption(owner="synthetic-owner-pass", user=password, R=6),
        )
    return sink.getvalue()


def test_t0608_ch09_ch15_deferred_input_and_registry_race() -> None:
    report = AttachmentInspector().inspect(
        canonical_with_attachments(
            (("protected.pdf", "application", "pdf", _encrypted_text_pdf("valid-pass")),),
            suffix="protected-pdf-chaos",
        )
    )
    assert report.attachments[0].reason_code == "PDF_ENCRYPTED_DEFERRED"
    extractor = SafeArtifactExtractor()
    assert extractor.extract(report).state is ExtractionState.WAITING_FOR_PDF_PASSWORD
    wrong = SecretText("wrong-pass")
    correct = SecretText("valid-pass")
    try:
        assert extractor.extract(report, pdf_passwords={1: wrong}).state is (
            ExtractionState.WAITING_FOR_PDF_PASSWORD
        )
        assert extractor.extract(report, pdf_passwords={1: correct}).state is ExtractionState.READY
    finally:
        wrong.destroy()
        correct.destroy()

    with recovery_context() as context:
        proof = RemoteRecoveryGate(context.reader, context.decryptor).verify(
            context.canonical,
            context.first_verification,
            context.raw_plan,
            context.processed_bundle,
            context.processed_plan,
        )
        message, changed_verification = pre_m3_message(
            context,
            subject="Synthetic sender registry changed",
        )
        transport = SyntheticM3Transport(message.ref.message_id)
        guard = GmailEndpointGuard(transport)
        with pytest.raises(M3Error, match="not bound"):
            ExactMessageTrashExecutor(
                guard,
                GmailLabelConfirmationClient(guard),
            ).execute(
                message,
                context.first_verification,
                changed_verification,
                proof,
                MutationBudget.for_phase(MutationPhase.CANARY),
            )
        assert transport.requests == []


def test_t0608_ch10_content_conflict_converges_or_blocks() -> None:
    index = LogicalObjectIndex()
    assert index.upsert("object-1", "a" * 64) is UpsertResult.CREATED
    assert index.upsert("object-1", "a" * 64) is UpsertResult.UNCHANGED
    root = index.merkle_root()
    with pytest.raises(LoadProbeError, match="conflict"):
        index.upsert("object-1", "b" * 64)
    assert index.object_count == 1
    assert index.merkle_root() == root


def test_t0608_ch11_ch12_ch16_ch17_cleanup_publication_and_auto() -> None:
    for failure in (asyncio.CancelledError, TimeoutError, MemoryError):
        arena = EphemeralPlaintextArena()
        view = None
        try:
            with arena:
                view = arena.allocate(b"synthetic ephemeral plaintext")
                raise failure("synthetic chaos exit")
        except BaseException as exc:
            assert isinstance(exc, failure)
        assert view is not None
        assert bytes(view) == bytes(len(view))
        assert arena.closed and arena.outstanding_bytes == 0

    module_path = ephemeral_module.__file__
    assert module_path is not None
    source = Path(module_path).read_text(encoding="utf-8")
    assert all(token not in source for token in ("open(", "tempfile", "NamedTemporaryFile"))
    with pytest.raises(PublicInventoryError, match="forbidden private field"):
        validate_public_shape(b'{"message_id":"synthetic-private-shape"}\n')

    monitor = CodexAutoMonitor()
    auto_now = datetime(2026, 7, 20, 4, 30, tzinfo=UTC)
    disabled = monitor.plan(
        PublicHealthObservation(
            public_document(PublicRunState.FAILED),
            "LinzeDatabase/MooMooAU/evidence/ops/latest.json",
            auto_now,
        ),
        now_utc=auto_now,
        enabled=False,
    )
    assert disabled.action is AutoAction.DISABLED
    assert disabled.issue_updates == 0
    saga = PrivateFirstPublicationSaga()
    saga.record_private(committed=True, recovery_verified=True)
    assert saga.snapshot.m3_authorized


def test_t0608_ch13_timeline_repair_from_zero_asset() -> None:
    with recovery_context() as context, EphemeralAgeSession() as crypto:
        event = timeline_event(context)
        changed = replace(event, m3_state=M3State.ALREADY_TRASHED)
        remote = MemoryTimelineReleaseRemote()
        publisher = SingleLatestTimelinePublisher(
            DeterministicTimelineRenderer(),
            crypto,
            remote,
            MemoryTimelineStateStore(),
        )
        publisher.publish(
            (event,),
            processed_snapshot_root="1" * 64,
            key_epoch="synthetic-stage6",
            now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        )
        remote.fail_next_upload = True
        failed = publisher.publish(
            (changed,),
            processed_snapshot_root="2" * 64,
            key_epoch="synthetic-stage6",
            now_utc=datetime(2026, 7, 21, tzinfo=UTC),
        )
        assert failed.action is TimelinePublishAction.REPAIR_REQUIRED
        assert failed.asset_count == 0
        with pytest.raises(TimelinePublishError, match="replayed first"):
            publisher.publish(
                (changed,),
                processed_snapshot_root="3" * 64,
                key_epoch="synthetic-stage6",
                now_utc=datetime(2026, 7, 22, tzinfo=UTC),
            )
        repaired = publisher.publish(
            (changed,),
            processed_snapshot_root="2" * 64,
            key_epoch="synthetic-stage6",
            now_utc=datetime(2026, 7, 22, 1, tzinfo=UTC),
        )
        assert repaired.action is TimelinePublishAction.ASSET_REPAIRED
        assert repaired.asset_count == 1
        assert remote.maximum_observed_asset_count == 1


def test_t0608_ch14_uncertain_trash_is_not_repeated() -> None:
    class ConfirmationReadFails(SyntheticM3Transport):
        def send(self, request: HttpRequest) -> HttpResponse:
            if request.method == "GET":
                self.requests.append(request)
                raise ConnectionError("synthetic confirmation interruption")
            return super().send(request)

    with recovery_context() as context:
        proof = RemoteRecoveryGate(context.reader, context.decryptor).verify(
            context.canonical,
            context.first_verification,
            context.raw_plan,
            context.processed_bundle,
            context.processed_plan,
        )
        message, second = pre_m3_message(context)
        transport = ConfirmationReadFails(message.ref.message_id)
        guard = GmailEndpointGuard(transport)
        result = ExactMessageTrashExecutor(
            guard,
            GmailLabelConfirmationClient(guard),
        ).execute(
            message,
            context.first_verification,
            second,
            proof,
            MutationBudget.for_phase(MutationPhase.CANARY),
        )
        assert result.state is M3State.UNKNOWN
        assert result.mutation_calls == 1
        assert [request.method for request in transport.requests] == ["POST", "GET"]

        reconciled_message, reconciled_verification = pre_m3_message(context, trashed=True)
        next_transport = SyntheticM3Transport(reconciled_message.ref.message_id)
        next_guard = GmailEndpointGuard(next_transport)
        reconciled = ExactMessageTrashExecutor(
            next_guard,
            GmailLabelConfirmationClient(next_guard),
        ).execute(
            reconciled_message,
            context.first_verification,
            reconciled_verification,
            proof,
            MutationBudget.for_phase(MutationPhase.CANARY),
        )
        assert reconciled.state is M3State.ALREADY_TRASHED
        assert reconciled.mutation_calls == 0
        assert next_transport.requests == []


def _capacity(*, red: bool = False) -> CapacityAssessment:
    return CapacityPolicy().evaluate(
        CapacitySnapshot(
            git_repository_bytes=9_100_000_000 if red else 1_000_000,
            lfs_storage_bytes=1_000_000,
            largest_git_object_bytes=100_000,
            largest_lfs_object_bytes=100_000,
            live_release_asset_bytes=100_000,
        ),
        CapacityLimits(
            lfs_storage_budget_bytes=10_000_000_000,
            lfs_object_maximum_bytes=2_000_000_000,
        ),
    )


def test_t0608_all_kill_criteria_trigger_and_require_exact_recovery_gates() -> None:
    operation_flags = {
        SensitiveOperation.PRODUCTION_RUN: "production_enabled",
        SensitiveOperation.REMOTE_READ: "production_enabled",
        SensitiveOperation.RAW_WRITE: "raw_enabled",
        SensitiveOperation.PROCESSED_WRITE: "processed_enabled",
        SensitiveOperation.M3: "m3_enabled",
        SensitiveOperation.TIMELINE_WRITE: "timeline_enabled",
        SensitiveOperation.MODEL_USE: "model_enabled",
        SensitiveOperation.BACKFILL: "backfill_enabled",
    }
    for kill_id in KillId:
        switch = KillSwitch()
        impact = switch.trigger(kill_id)
        assert switch.trigger(kill_id) is impact
        if kill_id is KillId.KILL_007:
            assert not any(
                (
                    impact.production_enabled,
                    impact.raw_enabled,
                    impact.processed_enabled,
                    impact.m3_enabled,
                    impact.timeline_enabled,
                    impact.backfill_enabled,
                )
            )
        gate = OperationalGate(
            _capacity(red=kill_id is KillId.KILL_007),
            kill_impact=switch.active_impact,
        )
        executed: list[str] = []
        disabled = [
            operation for operation, flag in operation_flags.items() if not getattr(impact, flag)
        ]
        assert disabled
        for operation in disabled:
            with pytest.raises(OperationGateError):
                gate.execute(operation, partial(_record_operation, executed, operation))
        assert executed == []

        required = switch.required_resume_gates(kill_id)
        missing = frozenset(tuple(sorted(required))[:-1])
        assert not switch.recover(missing)
        assert json.loads(switch.canonical_audit_bytes())["active_kill_id"] == kill_id.value
        assert not switch.recovery_authorized(kill_id, required | {"EXTRA_GATE"})
        assert switch.recover(required)
        assert switch.active_impact is None
        audit = json.loads(switch.canonical_audit_bytes())
        assert audit["active_kill_id"] is None
        assert [item["action"] for item in audit["transitions"]] == ["TRIGGER", "RECOVER"]
        assert audit["transitions"][1]["observed_passing_gates"] == sorted(required)
