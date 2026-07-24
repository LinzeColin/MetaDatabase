from __future__ import annotations

import base64
import hashlib
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from stage3_support import (
    SyntheticGmailMessage,
    SyntheticGmailTransport,
    make_raw_message,
    metadata_headers,
    registry_payload,
    synthetic_address,
    synthetic_registry,
)
from stage4_support import (
    classification_registry,
    classification_registry_payload,
    csv_statement,
    parser_registry_payload,
    verified_inputs,
)

from moomooau_archive.age_stream import OfficialAgeStream
from moomooau_archive.attachment_inspector import AttachmentInspector, AttachmentKind
from moomooau_archive.auth import GMAIL_MODIFY_SCOPE, GMAIL_OAUTH_SECRET_NAME
from moomooau_archive.blue_green_runtime import (
    BlueGreenTimelineRunner,
    CurrentProcessedPointerSource,
    RecoveredCurrentPointer,
    RemoteCurrentProcessedPointerSource,
)
from moomooau_archive.canary_runtime import (
    CurrentProcessedPlanFactory,
    ExistingProcessedReconciliationMatcher,
    M3CanaryRunner,
    RawOnlyCanaryRunner,
)
from moomooau_archive.canonical_raw import CanonicalRaw, CanonicalRawFetcher
from moomooau_archive.capacity import (
    CapacityAssessment,
    CapacityLimits,
    CapacityPolicy,
    CapacitySnapshot,
)
from moomooau_archive.document_parser import (
    ParserProfileRegistry,
    SafeArtifactExtractor,
    StatementParser,
)
from moomooau_archive.ga_runtime import GAFullPipelineRunner
from moomooau_archive.gmail_discovery import (
    FullMailboxDiscoverer,
    GmailReadClient,
    GmailReconciler,
    SyncState,
)
from moomooau_archive.gmail_guard import GmailEndpointGuard
from moomooau_archive.gmail_sync_checkpoint import (
    EncryptedGmailSyncCheckpoint,
    GmailRunCheckpoint,
    MemoryGmailSyncStateStore,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse
from moomooau_archive.m3 import (
    ExactMessageTrashExecutor,
    GmailLabelConfirmationClient,
)
from moomooau_archive.operation_gate import OperationalGate
from moomooau_archive.processed_commit import (
    CurrentProcessedPointer,
    MemoryProcessedCiphertextStore,
    ParserBlueGreenComparator,
    ProcessedCommitPlanner,
    ProcessedCommitSaga,
)
from moomooau_archive.processed_models import (
    DocumentClass,
    DocumentClassifier,
    DocumentEnvelopeFactory,
)
from moomooau_archive.processed_product import ProcessedProductBuilder
from moomooau_archive.production_adapters import (
    OfficialAgeCrypto,
    RemoteFirstImportTimestampSource,
)
from moomooau_archive.protected_beta import (
    AGE_IDENTITY_SECRET_NAME,
    BETA_CONFIG_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    OPAQUE_ID_KEY_SECRET_NAME,
    SENDER_REGISTRY_SECRET_NAME,
    ProtectedBetaBootstrap,
)
from moomooau_archive.protected_beta_diagnostics import ProtectedBetaDiagnostics
from moomooau_archive.protected_m3 import (
    CLASSIFICATION_REGISTRY_SECRET_NAME,
    M3_CONFIG_SECRET_NAME,
    PARSER_REGISTRY_SECRET_NAME,
    ProtectedM3Bootstrap,
)
from moomooau_archive.protected_m3_diagnostics import ProtectedM3Diagnostics
from moomooau_archive.raw_commit import (
    MemoryAppendOnlyCiphertextStore,
    OpaqueIdFactory,
    RawCommitPlan,
    RawCommitPlanner,
    RawCommitSaga,
)
from moomooau_archive.recovery import AgeIdentityGenerator
from moomooau_archive.release_control import (
    ObservationProvenance,
    PhaseObservation,
    ReleasePhase,
)
from moomooau_archive.remote_recovery_gate import (
    MessageRecoveryProof,
    OfficialAgeDecryptor,
    RemoteRecoveryGate,
    RepositoryCiphertextReader,
)
from moomooau_archive.secret_values import SecretBytes, SecretText
from moomooau_archive.sender_registry import MessageVerification, SenderVerifier
from moomooau_archive.timeline_publish import (
    MemoryTimelineReleaseRemote,
    MemoryTimelineStateStore,
    SingleLatestTimelinePublisher,
)
from moomooau_archive.timeline_render import DeterministicTimelineRenderer
from moomooau_archive.timeline_snapshot import (
    TimelineSnapshotCommitSaga,
    TimelineSnapshotPlanner,
    TimelineSnapshotRecoveryGate,
)


def synthetic_capacity() -> CapacityAssessment:
    return CapacityPolicy().evaluate(
        CapacitySnapshot(
            git_repository_bytes=1_000_000,
            lfs_storage_bytes=0,
            largest_git_object_bytes=1_000,
            largest_lfs_object_bytes=0,
            live_release_asset_bytes=1_000,
        ),
        CapacityLimits(
            lfs_storage_budget_bytes=10_000_000_000,
            lfs_object_maximum_bytes=2_000_000_000,
        ),
    )


def phase_observation(
    phase: ReleasePhase,
    *,
    provenance: ObservationProvenance | None = None,
    days: int | None = None,
    observed_runs: int | None = None,
    scheduled_runs: int | None = None,
    verified_messages: int | None = None,
    source_mutations: int | None = None,
    mutation_budget_max: int | None = None,
    recovery_attempts: int | None = None,
    recovery_successes: int | None = None,
    processed_messages: int | None = None,
    parser_comparisons: int | None = None,
    timeline_publish_attempts: int | None = None,
    full_reconcile_runs: int | None = None,
    minimum_live_assets: int | None = None,
    maximum_live_assets: int | None = None,
    collateral_mutations: int = 0,
    public_sensitive_findings: int = 0,
    logical_duplicates: int = 0,
    full_reconcile_difference: int = 0,
    unresolved_failures: int = 0,
) -> PhaseObservation:
    defaults = {
        ReleasePhase.ALPHA: (0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        ReleasePhase.BETA_RAW_ONLY: (1, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0),
        ReleasePhase.M3_CANARY: (0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 1, 0, 0, 1),
        ReleasePhase.BLUE_GREEN: (0, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
        ReleasePhase.GA: (1, 1, 1, 1, 1, 10, 1, 1, 1, 1, 1, 0, 1, 1),
    }[phase]
    (
        default_days,
        default_runs,
        default_scheduled,
        default_verified,
        default_mutations,
        default_budget,
        default_attempts,
        default_successes,
        default_minimum_assets,
        default_maximum_assets,
        default_processed,
        default_comparisons,
        default_timeline_attempts,
        default_full_reconcile_runs,
    ) = defaults
    start = datetime(2026, 7, 1, tzinfo=UTC)
    return PhaseObservation(
        phase=phase,
        provenance=provenance
        or (
            ObservationProvenance.LOCAL_SYNTHETIC
            if phase is ReleasePhase.ALPHA
            else ObservationProvenance.PROTECTED_GITHUB_ACTIONS
        ),
        started_at_utc=start,
        ended_at_utc=start + timedelta(days=default_days if days is None else days),
        observed_runs=default_runs if observed_runs is None else observed_runs,
        scheduled_0430_runs=(default_scheduled if scheduled_runs is None else scheduled_runs),
        verified_messages=(default_verified if verified_messages is None else verified_messages),
        source_mutations=(default_mutations if source_mutations is None else source_mutations),
        mutation_budget_max=(
            default_budget if mutation_budget_max is None else mutation_budget_max
        ),
        recovery_attempts=(default_attempts if recovery_attempts is None else recovery_attempts),
        recovery_successes=(
            default_successes if recovery_successes is None else recovery_successes
        ),
        processed_messages=(
            default_processed if processed_messages is None else processed_messages
        ),
        parser_blue_green_comparisons=(
            default_comparisons if parser_comparisons is None else parser_comparisons
        ),
        timeline_publish_attempts=(
            default_timeline_attempts
            if timeline_publish_attempts is None
            else timeline_publish_attempts
        ),
        full_reconcile_runs=(
            default_full_reconcile_runs if full_reconcile_runs is None else full_reconcile_runs
        ),
        collateral_mutations=collateral_mutations,
        public_sensitive_findings=public_sensitive_findings,
        logical_duplicates=logical_duplicates,
        full_reconcile_difference=full_reconcile_difference,
        minimum_live_timeline_assets=(
            default_minimum_assets if minimum_live_assets is None else minimum_live_assets
        ),
        maximum_live_timeline_assets=(
            default_maximum_assets if maximum_live_assets is None else maximum_live_assets
        ),
        unresolved_failures=unresolved_failures,
    )


def observations_through(phase: ReleasePhase) -> tuple[PhaseObservation, ...]:
    order = (
        ReleasePhase.ALPHA,
        ReleasePhase.BETA_RAW_ONLY,
        ReleasePhase.M3_CANARY,
        ReleasePhase.BLUE_GREEN,
        ReleasePhase.GA,
    )
    end = order.index(phase) + 1
    return tuple(phase_observation(item) for item in order[:end])


def canary_message(message_id: str, *, verified: bool = True) -> SyntheticGmailMessage:
    sender = None if verified else synthetic_address("unknown", "unregistered.invalid")
    headers = metadata_headers(sender=sender)
    raw = make_raw_message(message_id=message_id, sender=sender)
    return SyntheticGmailMessage(
        message_id=message_id,
        thread_id="thread-" + message_id,
        labels=("INBOX",),
        history_id="9001",
        internal_date_ms=1_767_225_600_000,
        headers=headers,
        raw=raw,
    )


class Stage7GmailTransport:
    """Extend the Stage 3 read fixture with exact-message Trash and confirmation only."""

    def __init__(
        self,
        messages: tuple[SyntheticGmailMessage, ...],
        *,
        events: list[str] | None = None,
        history_pages: tuple[dict[str, object], ...] = (),
        history_status: int = 200,
        malformed_metadata_ids: frozenset[str] = frozenset(),
    ) -> None:
        self.inner = SyntheticGmailTransport(
            messages,
            history_pages=history_pages,
            history_status=history_status,
        )
        self.message_ids = {item.message_id for item in messages}
        self._initial_labels = {item.message_id: item.labels for item in messages}
        self.trashed_ids: list[str] = []
        self._events = events
        self._malformed_metadata_ids = malformed_metadata_ids

    def send(self, request: HttpRequest) -> HttpResponse:
        parsed = urlsplit(request.url)
        query = parse_qs(parsed.query)
        prefix = "/gmail/v1/users/me/messages/"
        relative = parsed.path.removeprefix(prefix) if parsed.path.startswith(prefix) else ""
        if request.method == "POST" and relative.endswith("/trash"):
            message_id = relative.removesuffix("/trash")
            if message_id not in self.message_ids or request.body not in {None, b""}:
                return HttpResponse(404, b"{}")
            self.trashed_ids.append(message_id)
            if self._events is not None:
                self._events.append("trash")
            return HttpResponse(
                200,
                json.dumps(
                    {"id": message_id, "labelIds": self._current_labels(message_id)},
                    separators=(",", ":"),
                ).encode(),
            )
        if (
            request.method == "GET"
            and relative in self.message_ids
            and query == {"format": ["minimal"]}
        ):
            return HttpResponse(
                200,
                json.dumps(
                    {"id": relative, "labelIds": self._current_labels(relative)},
                    separators=(",", ":"),
                ).encode(),
            )
        if (
            request.method == "GET"
            and relative in self.message_ids
            and query.get("format") == ["metadata"]
        ):
            response = self.inner.send(request)
            if relative in self._malformed_metadata_ids:
                payload = json.loads(response.body)
                payload.pop("payload", None)
                return HttpResponse(
                    response.status,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
                )
            if relative not in self.trashed_ids:
                return response
            payload = json.loads(response.body)
            payload["labelIds"] = self._current_labels(relative)
            return HttpResponse(
                response.status,
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            )
        if (
            request.method == "GET"
            and relative in self.message_ids
            and query == {"format": ["raw"]}
            and relative in self.trashed_ids
        ):
            response = self.inner.send(request)
            payload = json.loads(response.body)
            payload["labelIds"] = self._current_labels(relative)
            return HttpResponse(
                response.status,
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            )
        return self.inner.send(request)

    def _current_labels(self, message_id: str) -> list[str]:
        labels = set(self._initial_labels[message_id])
        if message_id in self.trashed_ids:
            labels.discard("INBOX")
            labels.add("TRASH")
        return sorted(labels)


@dataclass(frozen=True, slots=True)
class CanaryContext:
    runner: RawOnlyCanaryRunner
    transport: Stage7GmailTransport
    store: MemoryAppendOnlyCiphertextStore


@contextmanager
def canary_context(
    messages: tuple[SyntheticGmailMessage, ...],
    *,
    capacity: CapacityAssessment | None = None,
    diagnostics: ProtectedBetaDiagnostics | None = None,
    malformed_metadata_ids: frozenset[str] = frozenset(),
) -> Iterator[CanaryContext]:
    generated = AgeIdentityGenerator().generate()
    opaque_key = SecretBytes(b"synthetic-stage7-opaque-key-material-0001")
    temporary = tempfile.TemporaryDirectory(prefix="moomooau-stage7-age-")
    identity_path = Path(temporary.name) / "identity.agekey"
    try:
        identity_path.write_bytes(generated.identity.reveal())
        identity_path.chmod(0o600)
        transport = Stage7GmailTransport(
            messages,
            malformed_metadata_ids=malformed_metadata_ids,
        )
        guard = GmailEndpointGuard(transport)
        gmail = GmailReadClient(guard)
        registry = synthetic_registry()
        verifier = SenderVerifier()
        store = MemoryAppendOnlyCiphertextStore()
        age = OfficialAgeStream()
        runner = RawOnlyCanaryRunner(
            gmail,
            registry,
            verifier,
            CanonicalRawFetcher(guard, verifier),
            AttachmentInspector(),
            RawCommitPlanner(age, generated.recipient, OpaqueIdFactory(opaque_key)),
            RawCommitSaga(store),
            RemoteRecoveryGate(
                store,
                OfficialAgeDecryptor(
                    age,
                    identity_path,
                    allowed_tmpfs_roots=(Path(temporary.name),),
                ),
            ),
            OperationalGate(capacity or synthetic_capacity()),
            diagnostics=diagnostics,
        )
        yield CanaryContext(runner, transport, store)
    finally:
        opaque_key.destroy()
        generated.destroy()
        temporary.cleanup()


def m3_canary_message(
    message_id: str,
    *,
    with_supported_attachment: bool = True,
) -> SyntheticGmailMessage:
    subject = "Synthetic Moomoo AU Daily DAILY_STATEMENT"
    attachments = (
        (("synthetic.csv", "text", "csv", csv_statement()),) if with_supported_attachment else ()
    )
    return SyntheticGmailMessage(
        message_id=message_id,
        thread_id="thread-" + message_id,
        labels=("CATEGORY_UPDATES", "INBOX"),
        history_id="9101",
        internal_date_ms=1_767_225_600_000,
        headers=metadata_headers(subject=subject),
        raw=make_raw_message(
            message_id=message_id,
            subject=subject,
            attachments=attachments,
        ),
    )


class StableFirstImportTimestamps:
    def __init__(self) -> None:
        self._values: dict[str, datetime] = {}

    def resolve(self, source_id: str, observed_at_utc: datetime) -> datetime:
        return self._values.setdefault(source_id, observed_at_utc)

    def resolve_label_state(
        self,
        source_id: str,
        observed_at_utc: datetime,
    ) -> tuple[str, ...] | None:
        del source_id, observed_at_utc
        return None


class RecordingRepositoryReader:
    def __init__(
        self,
        inner: RepositoryCiphertextReader,
        events: list[str],
    ) -> None:
        self._inner = inner
        self._events = events
        self.corrupt_next = False
        self.fetch_calls = 0

    def fetch(self, relative_path: str) -> bytes | None:
        self.fetch_calls += 1
        self._events.append("recover")
        value = self._inner.fetch(relative_path)
        if self.corrupt_next and value is not None:
            self.corrupt_next = False
            return b"synthetic-corrupt-ciphertext"
        return value


@dataclass(frozen=True, slots=True)
class M3CanaryContext:
    runner: M3CanaryRunner
    transport: Stage7GmailTransport
    raw_store: MemoryAppendOnlyCiphertextStore
    processed_store: MemoryProcessedCiphertextStore
    reader: RecordingRepositoryReader
    events: list[str]


@contextmanager
def m3_canary_context(
    messages: tuple[SyntheticGmailMessage, ...],
    *,
    capacity: CapacityAssessment | None = None,
    diagnostics: ProtectedM3Diagnostics | None = None,
    malformed_metadata_ids: frozenset[str] = frozenset(),
) -> Iterator[M3CanaryContext]:
    generated = AgeIdentityGenerator().generate()
    opaque_key = SecretBytes(b"synthetic-stage7-m3-opaque-key-material-001")
    temporary = tempfile.TemporaryDirectory(prefix="moomooau-stage7-m3-age-")
    identity_path = Path(temporary.name) / "identity.agekey"
    try:
        identity_path.write_bytes(generated.identity.reveal())
        identity_path.chmod(0o600)
        events: list[str] = []
        transport = Stage7GmailTransport(
            messages,
            events=events,
            malformed_metadata_ids=malformed_metadata_ids,
        )
        guard = GmailEndpointGuard(transport)
        gmail = GmailReadClient(guard)
        sender_registry = synthetic_registry()
        verifier = SenderVerifier()
        age = OfficialAgeStream()
        decryptor = OfficialAgeDecryptor(
            age,
            identity_path,
            allowed_tmpfs_roots=(Path(temporary.name),),
        )
        raw_store = MemoryAppendOnlyCiphertextStore()
        processed_store = MemoryProcessedCiphertextStore()
        reader = RecordingRepositoryReader(
            RepositoryCiphertextReader(raw_store, processed_store),
            events,
        )
        operational_gate = OperationalGate(capacity or synthetic_capacity())
        opaque_ids = OpaqueIdFactory(opaque_key)
        runner = M3CanaryRunner(
            gmail,
            sender_registry,
            verifier,
            CanonicalRawFetcher(guard, verifier),
            AttachmentInspector(),
            RawCommitPlanner(age, generated.recipient, opaque_ids),
            RawCommitSaga(raw_store),
            classification_registry(DocumentClass.DAILY_STATEMENT, AttachmentKind.CSV),
            ParserProfileRegistry.from_json(
                parser_registry_payload(DocumentClass.DAILY_STATEMENT, AttachmentKind.CSV)
            ),
            CurrentProcessedPlanFactory(
                processed_store,
                decryptor,
                ProcessedCommitPlanner(age, generated.recipient),
            ),
            ProcessedCommitSaga(processed_store),
            RemoteRecoveryGate(reader, decryptor),
            ExactMessageTrashExecutor(guard, GmailLabelConfirmationClient(guard)),
            RemoteFirstImportTimestampSource(processed_store, decryptor),
            operational_gate,
            reconciliation_source_matcher=ExistingProcessedReconciliationMatcher(
                opaque_ids,
                processed_store,
            ),
            diagnostics=diagnostics,
        )
        yield M3CanaryContext(
            runner,
            transport,
            raw_store,
            processed_store,
            reader,
            events,
        )
    finally:
        opaque_key.destroy()
        generated.destroy()
        temporary.cleanup()


class CorruptibleProcessedStore(MemoryProcessedCiphertextStore):
    """Synthetic Processed remote with one read-only corruption injection."""

    def __init__(self) -> None:
        super().__init__()
        self.corrupt_next_immutable_path: str | None = None

    def fetch_immutable(self, relative_path: str) -> bytes | None:
        value = super().fetch_immutable(relative_path)
        if value is not None and relative_path == self.corrupt_next_immutable_path:
            self.corrupt_next_immutable_path = None
            return b"synthetic-corrupt-ciphertext"
        return value


class DriftOnResolveCurrentPointerSource:
    """Inject one logically changed pointer without mutating the synthetic remote."""

    def __init__(self, inner: CurrentProcessedPointerSource, drift_on_call: int) -> None:
        self._inner = inner
        self._drift_on_call = drift_on_call
        self._calls = 0

    def resolve(self, source_id: str) -> RecoveredCurrentPointer:
        recovered = self._inner.resolve(source_id)
        self._calls += 1
        if self._calls != self._drift_on_call:
            return recovered
        value = json.loads(recovered.pointer.to_bytes())
        value["generation"] += 1
        pointer = CurrentProcessedPointer.from_bytes(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        )
        return RecoveredCurrentPointer(
            pointer,
            recovered.revision,
            recovered.ciphertext_sha256,
        )


@dataclass(frozen=True, slots=True)
class BlueGreenContext:
    runner: BlueGreenTimelineRunner
    canonical: CanonicalRaw
    first_verification: MessageVerification
    raw_plan: RawCommitPlan
    raw_proof: MessageRecoveryProof
    processed_store: CorruptibleProcessedStore
    current_source: RemoteCurrentProcessedPointerSource
    snapshot_planner: TimelineSnapshotPlanner
    snapshot_commit: TimelineSnapshotCommitSaga
    snapshot_recovery: TimelineSnapshotRecoveryGate
    timeline_remote: MemoryTimelineReleaseRemote
    timeline_state: MemoryTimelineStateStore
    key_epoch: str
    imported_at_utc: datetime
    observed_at_utc: datetime


def _blue_green_parser_registry(*, candidate_business_change: bool) -> ParserProfileRegistry:
    incumbent = json.loads(
        parser_registry_payload(
            DocumentClass.DAILY_STATEMENT,
            AttachmentKind.CSV,
            parser_version="1.0.0",
        )
    )
    candidate = json.loads(
        parser_registry_payload(
            DocumentClass.DAILY_STATEMENT,
            AttachmentKind.CSV,
            parser_version="2.0.0",
        )
    )
    if candidate_business_change:
        candidate["profiles"][0]["fields"][2]["output_name"] = "portfolio_value"
    incumbent["registry_version"] = "2.0.0"
    incumbent["profiles"] = incumbent["profiles"] + candidate["profiles"]
    return ParserProfileRegistry.from_json(
        json.dumps(
            incumbent,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


@contextmanager
def blue_green_context(
    *,
    candidate_business_change: bool = False,
    capacity: CapacityAssessment | None = None,
    drift_on_runner_resolve: int | None = None,
) -> Iterator[BlueGreenContext]:
    """Build T0704 entirely from synthetic Raw and one in-memory private repository."""

    generated = AgeIdentityGenerator().generate()
    opaque_key = SecretBytes(b"synthetic-stage7-blue-green-opaque-key-01")
    temporary = tempfile.TemporaryDirectory(prefix="moomooau-stage7-blue-green-age-")
    identity_path = Path(temporary.name) / "identity.agekey"
    key_epoch = "synthetic-epoch-1"
    imported_at_utc = datetime(2026, 1, 1, tzinfo=UTC)
    observed_at_utc = datetime(2026, 7, 15, tzinfo=UTC)
    try:
        identity_path.write_bytes(generated.identity.reveal())
        identity_path.chmod(0o600)
        age = OfficialAgeStream()
        decryptor = OfficialAgeDecryptor(
            age,
            identity_path,
            allowed_tmpfs_roots=(Path(temporary.name),),
        )
        verified = verified_inputs(
            DocumentClass.DAILY_STATEMENT,
            csv_statement(),
            AttachmentKind.CSV,
            message_suffix=(
                "stage7-blue-green-changed"
                if candidate_business_change
                else "stage7-blue-green-equal"
            ),
        )
        raw_store = MemoryAppendOnlyCiphertextStore()
        raw_plan = RawCommitPlanner(
            age,
            generated.recipient,
            OpaqueIdFactory(opaque_key),
        ).plan(
            verified.canonical,
            verified.attachments,
            key_epoch=key_epoch,
        )
        RawCommitSaga(raw_store).commit(raw_plan)

        processed_store = CorruptibleProcessedStore()
        reader = RepositoryCiphertextReader(raw_store, processed_store)
        processed_recovery = RemoteRecoveryGate(reader, decryptor)
        raw_proof = processed_recovery.verify_raw_only(
            verified.canonical,
            verified.verification,
            raw_plan,
        )
        class_registry = classification_registry(
            DocumentClass.DAILY_STATEMENT,
            AttachmentKind.CSV,
        )
        parser_registry = _blue_green_parser_registry(
            candidate_business_change=candidate_business_change
        )
        classification = DocumentClassifier().classify(
            verified.canonical,
            verified.verification,
            verified.attachments,
            class_registry,
        )
        envelope = DocumentEnvelopeFactory().issue(
            verified.canonical,
            verified.verification,
            verified.attachments,
            raw_plan,
            classification,
            imported_at_utc=imported_at_utc,
            recovered_raw_ciphertext_sha256=raw_proof.raw_ciphertext_sha256,
        )
        incumbent_profile = next(
            item for item in parser_registry.profiles if item.parser_version == "1.0.0"
        )
        incumbent_outcome = StatementParser().parse(
            envelope,
            classification,
            SafeArtifactExtractor().extract(verified.attachments),
            incumbent_profile,
        )
        incumbent_bundle = ProcessedProductBuilder().build(envelope, incumbent_outcome)
        comparator = ParserBlueGreenComparator()
        initial_decision = comparator.compare(incumbent_bundle, None, observed_days=0)
        processed_planner = ProcessedCommitPlanner(age, generated.recipient)
        incumbent_plan = processed_planner.plan(
            incumbent_bundle,
            initial_decision,
            None,
            key_epoch=key_epoch,
            expected_pointer_revision=None,
        )
        ProcessedCommitSaga(processed_store).commit(incumbent_plan)
        processed_recovery.verify(
            verified.canonical,
            verified.verification,
            raw_plan,
            incumbent_bundle,
            incumbent_plan,
        )

        current_source = RemoteCurrentProcessedPointerSource(processed_store, decryptor)
        runner_current_source: CurrentProcessedPointerSource = current_source
        if drift_on_runner_resolve is not None:
            runner_current_source = DriftOnResolveCurrentPointerSource(
                current_source,
                drift_on_runner_resolve,
            )
        snapshot_planner = TimelineSnapshotPlanner(age, generated.recipient)
        snapshot_commit = TimelineSnapshotCommitSaga(processed_store)
        snapshot_recovery = TimelineSnapshotRecoveryGate(processed_store, decryptor)
        timeline_remote = MemoryTimelineReleaseRemote()
        timeline_state = MemoryTimelineStateStore()
        runner = BlueGreenTimelineRunner(
            class_registry,
            parser_registry,
            runner_current_source,
            processed_planner,
            ProcessedCommitSaga(processed_store),
            processed_recovery,
            snapshot_planner,
            snapshot_commit,
            snapshot_recovery,
            SingleLatestTimelinePublisher(
                DeterministicTimelineRenderer(),
                OfficialAgeCrypto(age, generated.recipient, decryptor),
                timeline_remote,
                timeline_state,
            ),
            OperationalGate(capacity or synthetic_capacity()),
        )
        # The fixture itself proves the incumbent current is decryptable before T0704 starts.
        current_source.resolve(incumbent_bundle.source_id)
        yield BlueGreenContext(
            runner,
            verified.canonical,
            verified.verification,
            raw_plan,
            raw_proof,
            processed_store,
            current_source,
            snapshot_planner,
            snapshot_commit,
            snapshot_recovery,
            timeline_remote,
            timeline_state,
            key_epoch,
            imported_at_utc,
            observed_at_utc,
        )
    finally:
        opaque_key.destroy()
        generated.destroy()
        temporary.cleanup()


@dataclass(frozen=True, slots=True)
class GAContext:
    runner: GAFullPipelineRunner
    transport: Stage7GmailTransport
    raw_store: MemoryAppendOnlyCiphertextStore
    processed_store: CorruptibleProcessedStore
    checkpoint_store: MemoryGmailSyncStateStore
    checkpoint: EncryptedGmailSyncCheckpoint
    timeline_remote: MemoryTimelineReleaseRemote
    timeline_state: MemoryTimelineStateStore
    events: list[str]


@contextmanager
def ga_context(
    messages: tuple[SyntheticGmailMessage, ...],
    *,
    initial_sync_state: SyncState | None = None,
    history_pages: tuple[dict[str, object], ...] = (),
    capacity: CapacityAssessment | None = None,
) -> Iterator[GAContext]:
    """Build the T0705 full pipeline with one synthetic ciphertext-only private remote."""

    generated = AgeIdentityGenerator().generate()
    opaque_key = SecretBytes(b"synthetic-stage7-ga-opaque-key-material-01")
    temporary = tempfile.TemporaryDirectory(prefix="moomooau-stage7-ga-age-")
    identity_path = Path(temporary.name) / "identity.agekey"
    try:
        identity_path.write_bytes(generated.identity.reveal())
        identity_path.chmod(0o600)
        events: list[str] = []
        transport = Stage7GmailTransport(
            messages,
            events=events,
            history_pages=history_pages,
        )
        guard = GmailEndpointGuard(transport)
        gmail = GmailReadClient(guard)
        reconciler = GmailReconciler(gmail, FullMailboxDiscoverer(gmail))
        sender_registry = synthetic_registry()
        verifier = SenderVerifier()
        age = OfficialAgeStream()
        decryptor = OfficialAgeDecryptor(
            age,
            identity_path,
            allowed_tmpfs_roots=(Path(temporary.name),),
        )
        crypto = OfficialAgeCrypto(age, generated.recipient, decryptor)
        checkpoint_store = MemoryGmailSyncStateStore()
        checkpoint = EncryptedGmailSyncCheckpoint(checkpoint_store, crypto)
        if initial_sync_state is not None:
            checkpoint.commit(None, GmailRunCheckpoint(initial_sync_state, ()))
        raw_store = MemoryAppendOnlyCiphertextStore()
        processed_store = CorruptibleProcessedStore()
        reader = RecordingRepositoryReader(
            RepositoryCiphertextReader(raw_store, processed_store),
            events,
        )
        recovery = RemoteRecoveryGate(reader, decryptor)
        class_registry = classification_registry(
            DocumentClass.DAILY_STATEMENT,
            AttachmentKind.CSV,
        )
        parser_registry = ParserProfileRegistry.from_json(
            parser_registry_payload(DocumentClass.DAILY_STATEMENT, AttachmentKind.CSV)
        )
        current_source = RemoteCurrentProcessedPointerSource(processed_store, decryptor)
        processed_planner = ProcessedCommitPlanner(age, generated.recipient)
        snapshot_planner = TimelineSnapshotPlanner(age, generated.recipient)
        snapshot_commit = TimelineSnapshotCommitSaga(processed_store)
        snapshot_recovery = TimelineSnapshotRecoveryGate(processed_store, decryptor)
        timeline_remote = MemoryTimelineReleaseRemote()
        timeline_state = MemoryTimelineStateStore()
        operational_gate = OperationalGate(capacity or synthetic_capacity())
        runner = GAFullPipelineRunner(
            gmail,
            reconciler,
            checkpoint,
            sender_registry,
            verifier,
            CanonicalRawFetcher(guard, verifier),
            AttachmentInspector(),
            RawCommitPlanner(age, generated.recipient, OpaqueIdFactory(opaque_key)),
            RawCommitSaga(raw_store),
            class_registry,
            parser_registry,
            CurrentProcessedPlanFactory(
                processed_store,
                decryptor,
                processed_planner,
            ),
            ProcessedCommitSaga(processed_store),
            recovery,
            ExactMessageTrashExecutor(guard, GmailLabelConfirmationClient(guard)),
            StableFirstImportTimestamps(),
            current_source,
            snapshot_planner,
            snapshot_commit,
            snapshot_recovery,
            SingleLatestTimelinePublisher(
                DeterministicTimelineRenderer(),
                crypto,
                timeline_remote,
                timeline_state,
            ),
            operational_gate,
        )
        yield GAContext(
            runner,
            transport,
            raw_store,
            processed_store,
            checkpoint_store,
            checkpoint,
            timeline_remote,
            timeline_state,
            events,
        )
    finally:
        opaque_key.destroy()
        generated.destroy()
        temporary.cleanup()


class TrackingProtectedSecretSource:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values
        self.reads: list[str] = []
        self.issued: list[SecretText] = []

    def read(self, name: str) -> SecretText:
        self.reads.append(name)
        if name not in self._values:
            raise KeyError("synthetic protected Secret is absent")
        value = SecretText(self._values[name])
        self.issued.append(value)
        return value

    @property
    def all_issued_destroyed(self) -> bool:
        return all(item.destroyed for item in self.issued)


class SyntheticOAuthTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return HttpResponse(
            200,
            json.dumps(
                {
                    "access_token": "synthetic-protected-gmail-access",
                    "expires_in": 3600,
                    "scope": GMAIL_MODIFY_SCOPE,
                    "token_type": "Bearer",
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
        )


class SyntheticProtectedGitHubTransport:
    def __init__(
        self,
        *,
        repository_id: int,
        installation_id: int,
        now: datetime,
    ) -> None:
        self.repository_id = repository_id
        self.installation_id = installation_id
        self.now = now
        self.owner = "synthetic-owner"
        self.name = "synthetic-private-database"
        self.requests: list[HttpRequest] = []
        self.objects: dict[str, bytes] = {}
        self.revisions: dict[str, str] = {}
        self.write_calls = 0

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        parsed = urlsplit(request.url)
        if (
            request.method == "POST"
            and parsed.path == f"/app/installations/{self.installation_id}/access_tokens"
        ):
            return self._json(
                201,
                {
                    "token": "synthetic-protected-installation-token",
                    "expires_at": (self.now + timedelta(hours=1))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "repositories": [{"id": self.repository_id}],
                    "permissions": {"contents": "write", "metadata": "read"},
                },
            )
        if request.method == "GET" and parsed.path == f"/repositories/{self.repository_id}":
            return self._json(
                200,
                {
                    "id": self.repository_id,
                    "private": True,
                    "full_name": f"{self.owner}/{self.name}",
                },
            )
        content_prefix = f"/repos/{self.owner}/{self.name}/contents/"
        if parsed.path.startswith(content_prefix):
            relative_path = unquote(parsed.path.removeprefix(content_prefix))
            if request.method == "GET":
                value = self.objects.get(relative_path)
                if value is None:
                    return HttpResponse(404, b"{}")
                if dict(request.headers).get("Accept") == "application/vnd.github.raw+json":
                    return HttpResponse(200, value)
                return self._json(
                    200,
                    {
                        "content": base64.b64encode(value).decode("ascii"),
                        "encoding": "base64",
                        "sha": self.revisions[relative_path],
                    },
                )
            if request.method == "PUT" and request.body is not None:
                payload = json.loads(request.body)
                expected = payload.get("sha")
                current = self.revisions.get(relative_path)
                if current is not None and expected is None:
                    return HttpResponse(422, b"{}")
                if expected is not None and expected != current:
                    return HttpResponse(409, b"{}")
                ciphertext = base64.b64decode(payload["content"], validate=True)
                self.write_calls += 1
                revision = hashlib.sha1(
                    str(self.write_calls).encode("ascii") + b"\0" + ciphertext,
                    usedforsecurity=False,
                ).hexdigest()
                self.objects[relative_path] = ciphertext
                self.revisions[relative_path] = revision
                return self._json(
                    200 if current is not None else 201,
                    {"content": {"sha": revision}},
                )
        raise AssertionError("synthetic protected GitHub transport received an unexpected request")

    @staticmethod
    def _json(status: int, payload: object) -> HttpResponse:
        return HttpResponse(
            status,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        )


@dataclass(frozen=True, slots=True)
class ProtectedBetaContext:
    bootstrap: ProtectedBetaBootstrap
    source: TrackingProtectedSecretSource
    oauth_transport: SyntheticOAuthTransport
    gmail_transport: Stage7GmailTransport
    github_transport: SyntheticProtectedGitHubTransport
    tmpfs_root: Path
    now: datetime


@contextmanager
def protected_beta_context(
    messages: tuple[SyntheticGmailMessage, ...],
    *,
    sender_active: bool = True,
    capacity_age_hours: int = 0,
    identity_matches_recipient: bool = True,
    github_key_valid: bool = True,
    diagnostics: ProtectedBetaDiagnostics | None = None,
) -> Iterator[ProtectedBetaContext]:
    now = datetime(2026, 7, 22, 1, tzinfo=UTC)
    repository_id = 7_100_101
    installation_id = 8_100_101
    app_id = 9_100_101
    generated = AgeIdentityGenerator().generate()
    other_identity = None
    if not identity_matches_recipient:
        other_identity = AgeIdentityGenerator().generate()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    temporary = tempfile.TemporaryDirectory(prefix="moomooau-stage7-protected-beta-")
    try:
        config = {
            "schema_version": "moomooau.protected-beta-config.v1",
            "phase": "BETA_RAW_ONLY",
            "beta_message_budget": 1,
            "key_epoch": "synthetic-epoch-1",
            "age_recipient": generated.recipient,
            "github": {
                "app_id": app_id,
                "installation_id": installation_id,
                "repository_id": repository_id,
            },
            "capacity": {
                "observed_at_utc": (now - timedelta(hours=capacity_age_hours))
                .isoformat()
                .replace("+00:00", "Z"),
                "limits": {
                    "lfs_storage_budget_bytes": 10_000_000,
                    "lfs_object_maximum_bytes": 1_000_000,
                },
                "snapshot": {
                    "git_repository_bytes": 1_000,
                    "lfs_storage_bytes": 1_000,
                    "largest_git_object_bytes": 1_000,
                    "largest_lfs_object_bytes": 1_000,
                    "live_release_asset_bytes": 0,
                },
            },
        }
        identity_value = (
            other_identity.identity if other_identity is not None else generated.identity
        )
        values = {
            BETA_CONFIG_SECRET_NAME: json.dumps(
                config,
                sort_keys=True,
                separators=(",", ":"),
            ),
            SENDER_REGISTRY_SECRET_NAME: registry_payload(active=sender_active).decode("utf-8"),
            GITHUB_APP_PRIVATE_KEY_SECRET_NAME: (
                private_key_pem.decode("ascii") if github_key_valid else "synthetic-invalid-key"
            ),
            OPAQUE_ID_KEY_SECRET_NAME: base64.b64encode(b"synthetic-protected-opaque-key-1").decode(
                "ascii"
            ),
            AGE_IDENTITY_SECRET_NAME: identity_value.reveal().decode("ascii"),
            GMAIL_OAUTH_SECRET_NAME: json.dumps(
                {
                    "type": "authorized_user",
                    "client_id": "synthetic-protected-client",
                    "client_secret": (  # pragma: allowlist secret
                        "synthetic-protected-client-secret"
                    ),
                    "refresh_token": "synthetic-protected-refresh-token",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "scopes": [GMAIL_MODIFY_SCOPE],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        source = TrackingProtectedSecretSource(values)
        oauth_transport = SyntheticOAuthTransport()
        gmail_transport = Stage7GmailTransport(messages)
        github_transport = SyntheticProtectedGitHubTransport(
            repository_id=repository_id,
            installation_id=installation_id,
            now=now,
        )
        bootstrap = ProtectedBetaBootstrap(
            source,
            oauth_transport=oauth_transport,
            gmail_transport=gmail_transport,
            github_transport=github_transport,
            approved_tmpfs_root=Path(temporary.name),
            clock=lambda: now,
            allow_synthetic_ephemeral_root=True,
            diagnostics=diagnostics,
        )
        yield ProtectedBetaContext(
            bootstrap,
            source,
            oauth_transport,
            gmail_transport,
            github_transport,
            Path(temporary.name),
            now,
        )
    finally:
        if other_identity is not None:
            other_identity.destroy()
        generated.destroy()
        temporary.cleanup()


@dataclass(frozen=True, slots=True)
class ProtectedM3Context:
    bootstrap: ProtectedM3Bootstrap
    source: TrackingProtectedSecretSource
    oauth_transport: SyntheticOAuthTransport
    gmail_transport: Stage7GmailTransport
    github_transport: SyntheticProtectedGitHubTransport
    tmpfs_root: Path
    now: datetime


@contextmanager
def protected_m3_context(
    messages: tuple[SyntheticGmailMessage, ...],
    *,
    capacity_age_hours: int = 0,
    empty_processing_registries: bool = False,
    diagnostics: ProtectedM3Diagnostics | None = None,
    malformed_metadata_ids: frozenset[str] = frozenset(),
) -> Iterator[ProtectedM3Context]:
    now = datetime(2026, 7, 24, 1, tzinfo=UTC)
    repository_id = 7_100_103
    installation_id = 8_100_103
    app_id = 9_100_103
    generated = AgeIdentityGenerator().generate()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    temporary = tempfile.TemporaryDirectory(prefix="moomooau-stage7-protected-m3-")
    try:
        config = {
            "schema_version": "moomooau.protected-beta-config.v1",
            "phase": "BETA_RAW_ONLY",
            "key_epoch": "synthetic-epoch-1",
            "age_recipient": generated.recipient,
            "beta_message_budget": 1,
            "github": {
                "app_id": app_id,
                "installation_id": installation_id,
                "repository_id": repository_id,
            },
            "capacity": {
                "observed_at_utc": (now - timedelta(hours=capacity_age_hours))
                .isoformat()
                .replace("+00:00", "Z"),
                "limits": {
                    "lfs_storage_budget_bytes": 10_000_000,
                    "lfs_object_maximum_bytes": 1_000_000,
                },
                "snapshot": {
                    "git_repository_bytes": 1_000,
                    "lfs_storage_bytes": 1_000,
                    "largest_git_object_bytes": 1_000,
                    "largest_lfs_object_bytes": 1_000,
                    "live_release_asset_bytes": 0,
                },
            },
        }
        parser_payload = (
            json.dumps(
                {
                    "schema_version": "moomooau.parser-profile-registry.v1",
                    "registry_version": "1.0.0",
                    "issued_at_utc": "2026-01-01T00:00:00Z",
                    "activation_state": "EMPTY_PROTECTED_EVIDENCE_REQUIRED",
                    "profiles": [],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            if empty_processing_registries
            else parser_registry_payload(
                DocumentClass.DAILY_STATEMENT,
                AttachmentKind.CSV,
            ).decode("utf-8")
        )
        values = {
            M3_CONFIG_SECRET_NAME: json.dumps(
                config,
                sort_keys=True,
                separators=(",", ":"),
            ),
            SENDER_REGISTRY_SECRET_NAME: registry_payload().decode("utf-8"),
            CLASSIFICATION_REGISTRY_SECRET_NAME: classification_registry_payload(
                ()
                if empty_processing_registries
                else ((DocumentClass.DAILY_STATEMENT, AttachmentKind.CSV),)
            ).decode("utf-8"),
            PARSER_REGISTRY_SECRET_NAME: parser_payload,
            GITHUB_APP_PRIVATE_KEY_SECRET_NAME: private_key_pem.decode("ascii"),
            OPAQUE_ID_KEY_SECRET_NAME: base64.b64encode(b"synthetic-protected-opaque-key-1").decode(
                "ascii"
            ),
            AGE_IDENTITY_SECRET_NAME: generated.identity.reveal().decode("ascii"),
            GMAIL_OAUTH_SECRET_NAME: json.dumps(
                {
                    "type": "authorized_user",
                    "client_id": "synthetic-protected-m3-client",
                    "client_secret": (  # pragma: allowlist secret
                        "synthetic-protected-m3-client-secret"
                    ),
                    "refresh_token": "synthetic-protected-m3-refresh-token",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "scopes": [GMAIL_MODIFY_SCOPE],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        source = TrackingProtectedSecretSource(values)
        oauth_transport = SyntheticOAuthTransport()
        gmail_transport = Stage7GmailTransport(
            messages,
            malformed_metadata_ids=malformed_metadata_ids,
        )
        github_transport = SyntheticProtectedGitHubTransport(
            repository_id=repository_id,
            installation_id=installation_id,
            now=now,
        )
        bootstrap = ProtectedM3Bootstrap(
            source,
            oauth_transport=oauth_transport,
            gmail_transport=gmail_transport,
            github_transport=github_transport,
            approved_tmpfs_root=Path(temporary.name),
            clock=lambda: now,
            allow_synthetic_ephemeral_root=True,
            diagnostics=diagnostics,
        )
        yield ProtectedM3Context(
            bootstrap,
            source,
            oauth_transport,
            gmail_transport,
            github_transport,
            Path(temporary.name),
            now,
        )
    finally:
        generated.destroy()
        temporary.cleanup()
