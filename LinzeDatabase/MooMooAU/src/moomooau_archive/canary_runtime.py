"""Dependency-injected real-data runner for Stage 7 Beta Raw-only.

The runner owns orchestration only.  Credentials, network transports, capacity observations and
the protected execution environment are supplied by a separate bootstrap.  A completed result
is aggregate private evidence, not a final production acceptance claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Protocol

from .attachment_inspector import AttachmentInspector
from .canonical_raw import CanonicalRawFetcher
from .capacity import git_capacity_demand
from .document_parser import (
    ParserActivation,
    ParserProfile,
    ParserProfileRegistry,
    ProcessingDisposition,
    SafeArtifactExtractor,
    StatementParser,
)
from .gmail_discovery import (
    FullMailboxDiscoverer,
    GmailReadClient,
    MessageMetadataUnverifiable,
    MinimalMessage,
)
from .m3 import ExactMessageTrashExecutor, M3State, MutationBudget, MutationPhase
from .operation_gate import OperationalGate, SensitiveOperation
from .processed_commit import (
    CurrentProcessedPointer,
    ParserBlueGreenComparator,
    ProcessedCiphertextStore,
    ProcessedCommitPlan,
    ProcessedCommitPlanner,
    ProcessedCommitSaga,
    PromotionAction,
)
from .processed_models import (
    ClassificationActivation,
    ClassificationRegistry,
    DocumentClass,
    DocumentClassifier,
    DocumentEnvelopeFactory,
)
from .processed_product import ProcessedBundle, ProcessedProductBuilder
from .protected_beta_diagnostics import (
    ProtectedBetaDiagnostics,
    ProtectedBetaFailurePhase,
)
from .protected_m3_diagnostics import ProtectedM3Diagnostics, ProtectedM3FailurePhase
from .raw_commit import OpaqueIdFactory, RawCommitPlanner, RawCommitSaga
from .release_control import FeatureFlags, PhaseObservation, ReleasePhase, Stage7ReleaseGate
from .remote_recovery_gate import CiphertextDecryptor, RemoteRecoveryGate
from .sender_registry import (
    MessageVerification,
    RegistryActivation,
    SenderDecision,
    SenderRegistry,
    SenderVerifier,
    VerificationPhase,
)


class CanaryRuntimeError(RuntimeError):
    """A redacted fail-closed canary orchestration failure."""


class FirstImportTimestampSource(Protocol):
    """Return immutable Processed lineage needed to replay one opaque source ID."""

    def resolve(self, source_id: str, observed_at_utc: datetime) -> datetime: ...

    def resolve_label_state(
        self,
        source_id: str,
        observed_at_utc: datetime,
    ) -> tuple[str, ...] | None: ...


class ProcessedPlanFactory(Protocol):
    """Bind a Processed bundle to the currently encrypted remote pointer."""

    def plan(self, bundle: ProcessedBundle, *, key_epoch: str) -> ProcessedCommitPlan: ...


class ReconciliationSourceMatcher(Protocol):
    """Identify a source backed by a pre-existing encrypted Processed pointer."""

    def has_preexisting_current(self, gmail_message_id: str) -> bool: ...


class ExistingProcessedReconciliationMatcher:
    """Match only an opaque source whose current pointer existed before this run writes."""

    def __init__(
        self,
        opaque_ids: OpaqueIdFactory,
        store: ProcessedCiphertextStore,
    ) -> None:
        self._opaque_ids = opaque_ids
        self._store = store

    def has_preexisting_current(self, gmail_message_id: str) -> bool:
        source_id = self._opaque_ids.message_id(gmail_message_id)
        pointer_path = f"MooMooAU/State/processed-current/{source_id}.json.age"
        return self._store.fetch_current(pointer_path) is not None


class CurrentProcessedPlanFactory:
    """Decrypt and bind the current pointer before an idempotent M3 plan is issued.

    M3 Canary may create the first current Processed pointer or reuse an exactly equal current
    parser output.  A parser upgrade, rollback, same-version output drift or corrupt pointer is
    a Blue-Green concern and therefore fails closed here.
    """

    _ALLOWED_ACTIONS = {
        PromotionAction.INITIAL_PROMOTION,
        PromotionAction.IDEMPOTENT_CURRENT,
    }

    def __init__(
        self,
        store: ProcessedCiphertextStore,
        decryptor: CiphertextDecryptor,
        planner: ProcessedCommitPlanner,
    ) -> None:
        self._store = store
        self._decryptor = decryptor
        self._planner = planner
        self._comparator = ParserBlueGreenComparator()

    def plan(self, bundle: ProcessedBundle, *, key_epoch: str) -> ProcessedCommitPlan:
        pointer_path = f"MooMooAU/State/processed-current/{bundle.source_id}.json.age"
        revisioned = self._store.fetch_current(pointer_path)
        incumbent: CurrentProcessedPointer | None = None
        expected_revision: str | None = None
        if revisioned is not None:
            try:
                incumbent = CurrentProcessedPointer.from_bytes(
                    self._decryptor.decrypt(revisioned.ciphertext)
                )
            except Exception as exc:
                raise CanaryRuntimeError("Processed current pointer recovery failed") from exc
            if incumbent.source_id != bundle.source_id:
                raise CanaryRuntimeError("Processed current pointer source binding failed")
            expected_revision = revisioned.revision
        decision = self._comparator.compare(bundle, incumbent, observed_days=0)
        if decision.action not in self._ALLOWED_ACTIONS:
            raise CanaryRuntimeError("M3 parser output requires the Blue-Green path")
        return self._planner.plan(
            bundle,
            decision,
            incumbent,
            key_epoch=key_epoch,
            expected_pointer_revision=expected_revision,
        )


@dataclass(frozen=True, slots=True, repr=False)
class CanaryRunResult:
    phase: ReleasePhase
    discovered_refs: int
    metadata_reads: int
    verified_candidates: int
    archived_and_recovered: int
    deferred_verified: int
    unknown_candidates: int
    rejected_candidates: int
    quarantined_candidates: int
    source_mutations: int
    already_trashed: int
    maximum_live_timeline_assets: int = 0

    def __post_init__(self) -> None:
        counters = (
            self.discovered_refs,
            self.metadata_reads,
            self.verified_candidates,
            self.archived_and_recovered,
            self.deferred_verified,
            self.unknown_candidates,
            self.rejected_candidates,
            self.quarantined_candidates,
            self.source_mutations,
            self.already_trashed,
            self.maximum_live_timeline_assets,
        )
        if (
            self.phase is not ReleasePhase.BETA_RAW_ONLY
            or any(type(value) is not int or value < 0 for value in counters)
            or self.archived_and_recovered + self.deferred_verified > self.verified_candidates
            or self.source_mutations > self.archived_and_recovered
            or self.already_trashed > self.archived_and_recovered
            or self.maximum_live_timeline_assets != 0
            or self.source_mutations != 0
            or self.already_trashed != 0
        ):
            raise CanaryRuntimeError("canary result is internally inconsistent")

    def __repr__(self) -> str:
        return (
            f"CanaryRunResult(phase={self.phase.value!r}, "
            "mailbox_counts=<redacted>, private_values=<redacted>, "
            f"source_mutations={self.source_mutations}, live_assets=0)"
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": "moomooau.beta-raw-run-public.v1",
            "phase": self.phase.value,
            "run_status": "BETA_RAW_ONLY_COMPLETED_NOT_FINAL",
            "discovered_bucket": _bucket(self.discovered_refs),
            "verified_bucket": _bucket(self.verified_candidates),
            "recovered_bucket": _bucket(self.archived_and_recovered),
            "source_mutations": self.source_mutations,
            "maximum_live_timeline_assets": 0,
            "processing_enabled": False,
            "timeline_enabled": False,
            "production_health_claimed": False,
        }


class RawOnlyCanaryRunner:
    """Archive only deterministically verified Raw during Beta; M3 is unreachable."""

    def __init__(
        self,
        gmail: GmailReadClient,
        registry: SenderRegistry,
        verifier: SenderVerifier,
        raw_fetcher: CanonicalRawFetcher,
        inspector: AttachmentInspector,
        raw_planner: RawCommitPlanner,
        raw_commit: RawCommitSaga,
        recovery: RemoteRecoveryGate,
        operational_gate: OperationalGate,
        diagnostics: ProtectedBetaDiagnostics | None = None,
    ) -> None:
        if registry.activation is not RegistryActivation.ACTIVE:
            raise CanaryRuntimeError("protected sender registry is not active")
        self._gmail = gmail
        self._registry = registry
        self._verifier = verifier
        self._raw_fetcher = raw_fetcher
        self._inspector = inspector
        self._raw_planner = raw_planner
        self._raw_commit = raw_commit
        self._recovery = recovery
        self._operational_gate = operational_gate
        self._diagnostics = diagnostics or ProtectedBetaDiagnostics()

    def run(
        self,
        phase: ReleasePhase,
        *,
        maximum_verified_candidates: int,
        key_epoch: str,
        predecessor_observations: tuple[PhaseObservation, ...],
        beta_message_budget: int,
    ) -> CanaryRunResult:
        self._diagnostics.enter(ProtectedBetaFailurePhase.RUNTIME_PREFLIGHT)
        if (
            phase is not ReleasePhase.BETA_RAW_ONLY
            or type(maximum_verified_candidates) is not int
            or maximum_verified_candidates <= 0
            or type(beta_message_budget) is not int
            or beta_message_budget <= 0
            or maximum_verified_candidates > beta_message_budget
            or not key_epoch
        ):
            raise CanaryRuntimeError("canary run configuration is invalid")
        promotion = Stage7ReleaseGate().evaluate_promotion(
            ReleasePhase.BETA_RAW_ONLY,
            predecessor_observations,
            beta_message_budget=beta_message_budget,
        )
        if not promotion.ready:
            raise CanaryRuntimeError("Beta Raw-only protected predecessor gate is blocked")
        flags = FeatureFlags.for_phase(phase)
        if flags.processing_enabled or flags.timeline_enabled:
            raise CanaryRuntimeError("raw-only canary unexpectedly enabled a downstream product")

        self._operational_gate.preflight(SensitiveOperation.PRODUCTION_RUN)
        self._operational_gate.preflight(SensitiveOperation.RAW_WRITE)
        self._diagnostics.enter(ProtectedBetaFailurePhase.MAILBOX_DISCOVERY)
        discovery = FullMailboxDiscoverer(self._gmail).scan()
        metadata_reads = 0
        verified = archived = deferred = 0
        unknown = rejected = quarantined = 0
        source_mutations = already_trashed = 0

        for ref in discovery.refs:
            self._diagnostics.enter(ProtectedBetaFailurePhase.METADATA_VERIFICATION)
            metadata_reads += 1
            try:
                message = self._gmail.get_metadata(
                    ref.message_id,
                    header_names=self._registry.requested_header_names,
                )
            except MessageMetadataUnverifiable:
                quarantined += 1
                continue
            first = self._verifier.verify_message(
                message,
                self._registry,
                phase=VerificationPhase.PRE_RAW,
            )
            if first.decision is not SenderDecision.VERIFIED:
                if first.decision is SenderDecision.UNKNOWN:
                    unknown += 1
                elif first.decision is SenderDecision.REJECTED:
                    rejected += 1
                else:
                    quarantined += 1
                continue
            verified += 1
            if archived >= maximum_verified_candidates:
                deferred += 1
                continue
            permit = first.raw_fetch_permit
            if permit is None:
                raise CanaryRuntimeError("verified PRE_RAW result did not issue a fetch permit")
            self._diagnostics.enter(ProtectedBetaFailurePhase.RAW_FETCH)
            canonical = self._raw_fetcher.fetch(permit, self._registry)
            self._diagnostics.enter(ProtectedBetaFailurePhase.RAW_ENCRYPTION_PLAN)
            attachments = self._inspector.inspect(canonical)
            raw_plan = self._raw_planner.plan(canonical, attachments, key_epoch=key_epoch)
            self._diagnostics.enter(ProtectedBetaFailurePhase.RAW_COMMIT)
            self._operational_gate.execute(
                SensitiveOperation.RAW_WRITE,
                partial(self._raw_commit.commit, raw_plan),
                demand=git_capacity_demand(item.ciphertext for item in raw_plan.objects),
            )
            self._diagnostics.enter(ProtectedBetaFailurePhase.REMOTE_RECOVERY)
            proof = self._recovery.verify_raw_only(canonical, first, raw_plan)
            if proof.recovered_object_count != len(raw_plan.objects):
                raise CanaryRuntimeError("Raw-only remote recovery count differs from the plan")
            archived += 1

        return CanaryRunResult(
            phase=phase,
            discovered_refs=len(discovery.refs),
            metadata_reads=metadata_reads,
            verified_candidates=verified,
            archived_and_recovered=archived,
            deferred_verified=deferred,
            unknown_candidates=unknown,
            rejected_candidates=rejected,
            quarantined_candidates=quarantined,
            source_mutations=source_mutations,
            already_trashed=already_trashed,
        )


@dataclass(frozen=True, slots=True, repr=False)
class M3CanaryRunResult:
    """Aggregate-only result for one protected M3 attempt or zero-write reconciliation."""

    phase: ReleasePhase
    discovered_refs: int
    metadata_reads: int
    metadata_quarantined: int
    verified_candidates: int
    raw_archived: int
    processed_complete: int
    processed_safe_deferred: int
    processing_blocked: int
    full_recovery_successes: int
    mutation_calls: int
    confirmed_trashed: int
    already_trashed: int
    failed_mutation_outcomes: int
    deferred_mutations: int
    halted_fail_closed: bool
    reconciliation_mode: bool = False
    maximum_live_timeline_assets: int = 0

    def __post_init__(self) -> None:
        counters = (
            self.discovered_refs,
            self.metadata_reads,
            self.metadata_quarantined,
            self.verified_candidates,
            self.raw_archived,
            self.processed_complete,
            self.processed_safe_deferred,
            self.processing_blocked,
            self.full_recovery_successes,
            self.mutation_calls,
            self.confirmed_trashed,
            self.already_trashed,
            self.failed_mutation_outcomes,
            self.deferred_mutations,
            self.maximum_live_timeline_assets,
        )
        recovered_processed = self.processed_complete + self.processed_safe_deferred
        accounted_recovered = (
            self.confirmed_trashed
            + self.already_trashed
            + self.failed_mutation_outcomes
            + self.deferred_mutations
        )
        if (
            self.phase is not ReleasePhase.M3_CANARY
            or any(type(value) is not int or value < 0 for value in counters)
            or type(self.halted_fail_closed) is not bool
            or type(self.reconciliation_mode) is not bool
            or self.raw_archived > self.verified_candidates
            or recovered_processed + self.processing_blocked != self.raw_archived
            or self.full_recovery_successes != recovered_processed
            or accounted_recovered != recovered_processed
            or self.mutation_calls != self.confirmed_trashed + self.failed_mutation_outcomes
            or self.mutation_calls > 1
            or self.confirmed_trashed > 1
            or self.failed_mutation_outcomes > 1
            or self.halted_fail_closed != (self.failed_mutation_outcomes > 0)
            or (
                self.reconciliation_mode
                and (
                    self.mutation_calls != 0
                    or self.confirmed_trashed != 0
                    or self.already_trashed > 1
                )
            )
            or self.maximum_live_timeline_assets != 0
        ):
            raise CanaryRuntimeError("M3 Canary result is internally inconsistent")

    def __repr__(self) -> str:
        return (
            "M3CanaryRunResult(phase='M3_CANARY', mailbox_counts=<redacted>, "
            f"mutation_calls={self.mutation_calls}, halted={self.halted_fail_closed}, "
            "live_assets=0, private_values=<redacted>)"
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": "moomooau.m3-canary-run-public.v1",
            "phase": self.phase.value,
            "run_status": (
                "M3_CANARY_HALTED_FAIL_CLOSED"
                if self.halted_fail_closed
                else "M3_CANARY_RUN_COMPLETED_NOT_FINAL"
            ),
            "verified_bucket": _bucket(self.verified_candidates),
            "metadata_quarantine_bucket": _bucket(self.metadata_quarantined),
            "processed_or_safe_deferred_bucket": _bucket(self.full_recovery_successes),
            "mutation_budget_max": 1,
            "new_mutation_budget_max": 0 if self.reconciliation_mode else 1,
            "reconciliation_mode": self.reconciliation_mode,
            "mutation_calls_bucket": _bucket(self.mutation_calls),
            "confirmed_trashed_bucket": _bucket(self.confirmed_trashed),
            "reconciled_prior_unknown_mutation_bucket": _bucket(
                self.already_trashed if self.reconciliation_mode else 0
            ),
            "failed_mutation_outcomes_bucket": _bucket(self.failed_mutation_outcomes),
            "maximum_live_timeline_assets": 0,
            "timeline_enabled": False,
            "production_health_claimed": False,
        }


class M3CanaryRunner:
    """Archive, process and recover one exact verified message before its bounded M3 action.

    All adapters and protected registries are injected.  The runner never loads a credential,
    repository locator, sender or parser profile by itself, and it has no Timeline dependency.
    Reconciliation mode skips both persistence sagas and permits only an already-Trashed proof.
    """

    def __init__(
        self,
        gmail: GmailReadClient,
        sender_registry: SenderRegistry,
        verifier: SenderVerifier,
        raw_fetcher: CanonicalRawFetcher,
        inspector: AttachmentInspector,
        raw_planner: RawCommitPlanner,
        raw_commit: RawCommitSaga,
        classification_registry: ClassificationRegistry,
        parser_registry: ParserProfileRegistry,
        processed_plan_factory: ProcessedPlanFactory,
        processed_commit: ProcessedCommitSaga,
        recovery: RemoteRecoveryGate,
        trash_executor: ExactMessageTrashExecutor,
        first_import_timestamps: FirstImportTimestampSource,
        operational_gate: OperationalGate,
        reconciliation_source_matcher: ReconciliationSourceMatcher | None = None,
        diagnostics: ProtectedM3Diagnostics | None = None,
    ) -> None:
        active_processing = (
            classification_registry.activation is ClassificationActivation.ACTIVE
            and parser_registry.activation is ParserActivation.ACTIVE
        )
        safe_deferred_processing = (
            classification_registry.activation
            is ClassificationActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
            and parser_registry.activation is ParserActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
            and not classification_registry.rules
            and not parser_registry.profiles
        )
        if sender_registry.activation is not RegistryActivation.ACTIVE or not (
            active_processing or safe_deferred_processing
        ):
            raise CanaryRuntimeError("protected M3 registries are incompatible")
        self._gmail = gmail
        self._sender_registry = sender_registry
        self._verifier = verifier
        self._raw_fetcher = raw_fetcher
        self._inspector = inspector
        self._raw_planner = raw_planner
        self._raw_commit = raw_commit
        self._classification_registry = classification_registry
        self._parser_registry = parser_registry
        self._safe_deferred_only = safe_deferred_processing
        self._processed_plan_factory = processed_plan_factory
        self._processed_commit = processed_commit
        self._recovery = recovery
        self._trash_executor = trash_executor
        self._first_import_timestamps = first_import_timestamps
        self._operational_gate = operational_gate
        self._reconciliation_source_matcher = reconciliation_source_matcher
        self._diagnostics = diagnostics or ProtectedM3Diagnostics()
        self._classifier = DocumentClassifier()
        self._envelope_factory = DocumentEnvelopeFactory()
        self._extractor = SafeArtifactExtractor()
        self._parser = StatementParser()
        self._product_builder = ProcessedProductBuilder()

    def run(
        self,
        phase: ReleasePhase,
        *,
        maximum_verified_candidates: int,
        key_epoch: str,
        parser_current_version: str,
        observed_at_utc: datetime,
        predecessor_observations: tuple[PhaseObservation, ...],
        beta_message_budget: int,
        reconcile_prior_unknown_mutation: bool = False,
    ) -> M3CanaryRunResult:
        self._diagnostics.enter(ProtectedM3FailurePhase.RUNTIME_PREFLIGHT)
        if (
            phase is not ReleasePhase.M3_CANARY
            or type(maximum_verified_candidates) is not int
            or maximum_verified_candidates <= 0
            or not key_epoch
            or not _is_utc(observed_at_utc)
            or type(reconcile_prior_unknown_mutation) is not bool
            or (reconcile_prior_unknown_mutation and self._reconciliation_source_matcher is None)
        ):
            raise CanaryRuntimeError("M3 Canary run configuration is invalid")
        promotion = Stage7ReleaseGate().evaluate_promotion(
            ReleasePhase.M3_CANARY,
            predecessor_observations,
            beta_message_budget=beta_message_budget,
            parser_current_version=parser_current_version,
        )
        if not promotion.ready:
            raise CanaryRuntimeError("M3 Canary protected predecessor gate is blocked")
        flags = FeatureFlags.for_phase(
            phase,
            parser_current_version=parser_current_version,
        )
        if (
            not flags.processing_enabled
            or not flags.m3_enabled
            or flags.timeline_enabled
            or flags.mutation_budget_per_run != 1
            or (
                not self._safe_deferred_only
                and not any(
                    profile.parser_version == parser_current_version
                    for profile in self._parser_registry.profiles
                )
            )
        ):
            raise CanaryRuntimeError("M3 Canary feature or parser configuration is invalid")

        self._operational_gate.preflight(SensitiveOperation.PRODUCTION_RUN)
        self._diagnostics.enter(ProtectedM3FailurePhase.MAILBOX_DISCOVERY)
        discovery = FullMailboxDiscoverer(self._gmail).scan()
        budget = MutationBudget.for_phase(MutationPhase.CANARY)
        metadata_reads = metadata_quarantined = verified = raw_archived = 0
        complete = safe_deferred = processing_blocked = recovered = 0
        mutation_calls = confirmed = already = mutation_failures = deferred = 0
        halted = False

        reconciliation_candidate: tuple[MinimalMessage, MessageVerification] | None = None
        if reconcile_prior_unknown_mutation:
            matches: list[tuple[MinimalMessage, MessageVerification]] = []
            matcher = self._reconciliation_source_matcher
            if matcher is None:
                raise CanaryRuntimeError("M3 reconciliation matcher is unavailable")
            for ref in discovery.refs:
                self._diagnostics.enter(ProtectedM3FailurePhase.METADATA_VERIFICATION)
                metadata_reads += 1
                try:
                    message = self._gmail.get_metadata(
                        ref.message_id,
                        header_names=self._sender_registry.requested_header_names,
                    )
                except MessageMetadataUnverifiable:
                    metadata_quarantined += 1
                    continue
                first = self._verifier.verify_message(
                    message,
                    self._sender_registry,
                    phase=VerificationPhase.PRE_RAW,
                )
                if first.decision is not SenderDecision.VERIFIED:
                    continue
                verified += 1
                if "TRASH" in message.label_ids and matcher.has_preexisting_current(ref.message_id):
                    matches.append((message, first))
            if len(matches) != 1:
                raise CanaryRuntimeError(
                    "M3 reconciliation source is not exactly one pre-existing Trash match"
                )
            reconciliation_candidate = matches[0]

        refs_to_process = (
            (reconciliation_candidate[0].ref,)
            if reconciliation_candidate is not None
            else discovery.refs
        )
        for ref in refs_to_process:
            self._diagnostics.enter(ProtectedM3FailurePhase.METADATA_VERIFICATION)
            if reconciliation_candidate is not None:
                message, first = reconciliation_candidate
            else:
                metadata_reads += 1
                try:
                    message = self._gmail.get_metadata(
                        ref.message_id,
                        header_names=self._sender_registry.requested_header_names,
                    )
                except MessageMetadataUnverifiable:
                    metadata_quarantined += 1
                    continue
                first = self._verifier.verify_message(
                    message,
                    self._sender_registry,
                    phase=VerificationPhase.PRE_RAW,
                )
                if first.decision is not SenderDecision.VERIFIED:
                    continue
                verified += 1
            if raw_archived >= maximum_verified_candidates:
                continue
            permit = first.raw_fetch_permit
            if permit is None:
                raise CanaryRuntimeError("verified PRE_RAW result did not issue a fetch permit")
            self._diagnostics.enter(ProtectedM3FailurePhase.RAW_FETCH)
            canonical = self._raw_fetcher.fetch(permit, self._sender_registry)
            self._diagnostics.enter(ProtectedM3FailurePhase.RAW_ENCRYPTION_PLAN)
            attachments = self._inspector.inspect(canonical)
            raw_plan = self._raw_planner.plan(canonical, attachments, key_epoch=key_epoch)
            if not reconcile_prior_unknown_mutation:
                self._diagnostics.enter(ProtectedM3FailurePhase.RAW_COMMIT)
                self._operational_gate.execute(
                    SensitiveOperation.RAW_WRITE,
                    partial(self._raw_commit.commit, raw_plan),
                    demand=git_capacity_demand(item.ciphertext for item in raw_plan.objects),
                )
            self._diagnostics.enter(ProtectedM3FailurePhase.RAW_RECOVERY)
            raw_proof = self._recovery.verify_raw_only(canonical, first, raw_plan)
            raw_archived += 1

            self._diagnostics.enter(ProtectedM3FailurePhase.PROCESSED_PLAN)
            classification = self._classifier.classify(
                canonical,
                first,
                attachments,
                self._classification_registry,
            )
            imported_at_utc = self._first_import_timestamps.resolve(
                raw_plan.opaque_message_id,
                observed_at_utc,
            )
            if not _is_utc(imported_at_utc) or imported_at_utc > observed_at_utc:
                raise CanaryRuntimeError("first-import timestamp is invalid")
            label_state_override = self._first_import_timestamps.resolve_label_state(
                raw_plan.opaque_message_id,
                observed_at_utc,
            )
            envelope = self._envelope_factory.issue(
                canonical,
                first,
                attachments,
                raw_plan,
                classification,
                imported_at_utc=imported_at_utc,
                recovered_raw_ciphertext_sha256=raw_proof.raw_ciphertext_sha256,
                label_state_override=label_state_override,
            )
            extraction = self._extractor.extract(attachments)
            profile = self._profile_for(
                classification.document_class,
                parser_current_version,
            )
            outcome = self._parser.parse(envelope, classification, extraction, profile)
            if outcome.disposition is ProcessingDisposition.BLOCKED:
                processing_blocked += 1
                continue
            bundle = self._product_builder.build(envelope, outcome)
            processed_plan = self._processed_plan_factory.plan(bundle, key_epoch=key_epoch)
            if not reconcile_prior_unknown_mutation:
                self._diagnostics.enter(ProtectedM3FailurePhase.PROCESSED_COMMIT)
                self._operational_gate.execute(
                    SensitiveOperation.PROCESSED_WRITE,
                    partial(self._processed_commit.commit, processed_plan),
                    demand=git_capacity_demand(
                        tuple(item.ciphertext for item in processed_plan.immutable_objects)
                        + (
                            (processed_plan.current_pointer.ciphertext,)
                            if processed_plan.current_pointer is not None
                            else ()
                        )
                    ),
                )
            self._diagnostics.enter(ProtectedM3FailurePhase.FULL_RECOVERY)
            proof = self._recovery.verify(
                canonical,
                first,
                raw_plan,
                bundle,
                processed_plan,
            )
            expected_recovered = (
                len(raw_plan.objects)
                + len(processed_plan.immutable_objects)
                + (1 if processed_plan.current_pointer is not None else 0)
            )
            if proof.recovered_object_count != expected_recovered:
                raise CanaryRuntimeError("full remote recovery count differs from the plans")
            recovered += 1
            if outcome.disposition is ProcessingDisposition.COMPLETE:
                complete += 1
            else:
                safe_deferred += 1

            if (
                not reconcile_prior_unknown_mutation
                and budget.consumed_calls >= budget.maximum_calls
            ):
                deferred += 1
                continue
            self._diagnostics.enter(ProtectedM3FailurePhase.SECOND_VERIFICATION)
            second_message = self._gmail.get_metadata(
                ref.message_id,
                header_names=self._sender_registry.requested_header_names,
            )
            metadata_reads += 1
            second = self._verifier.verify_message(
                second_message,
                self._sender_registry,
                phase=VerificationPhase.PRE_M3,
            )
            self._diagnostics.enter(ProtectedM3FailurePhase.TRASH_MUTATION)
            if reconcile_prior_unknown_mutation:
                result = self._operational_gate.execute(
                    SensitiveOperation.M3,
                    partial(
                        self._trash_executor.reconcile_already_trashed,
                        second_message,
                        first,
                        second,
                        proof,
                    ),
                )
            else:
                result = self._operational_gate.execute(
                    SensitiveOperation.M3,
                    partial(
                        self._trash_executor.execute,
                        second_message,
                        first,
                        second,
                        proof,
                        budget,
                    ),
                )
            mutation_calls += result.mutation_calls
            if result.state is M3State.TRASHED:
                confirmed += 1
            elif result.state is M3State.ALREADY_TRASHED:
                already += 1
            else:
                mutation_failures += 1
                halted = True
                break

        accounted = confirmed + already + mutation_failures + deferred
        if recovered > accounted:
            deferred += recovered - accounted
        return M3CanaryRunResult(
            phase=phase,
            discovered_refs=len(discovery.refs),
            metadata_reads=metadata_reads,
            metadata_quarantined=metadata_quarantined,
            verified_candidates=verified,
            raw_archived=raw_archived,
            processed_complete=complete,
            processed_safe_deferred=safe_deferred,
            processing_blocked=processing_blocked,
            full_recovery_successes=recovered,
            mutation_calls=mutation_calls,
            confirmed_trashed=confirmed,
            already_trashed=already,
            failed_mutation_outcomes=mutation_failures,
            deferred_mutations=deferred,
            halted_fail_closed=halted,
            reconciliation_mode=reconcile_prior_unknown_mutation,
        )

    def _profile_for(
        self,
        document_class: DocumentClass,
        parser_current_version: str,
    ) -> ParserProfile | None:
        matches = [
            profile
            for profile in self._parser_registry.profiles
            if profile.document_class is document_class
            and profile.parser_version == parser_current_version
        ]
        if len(matches) > 1:
            raise CanaryRuntimeError("multiple current parser profiles match one document")
        return matches[0] if matches else None


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _bucket(value: int) -> str:
    if value == 0:
        return "ZERO"
    if value == 1:
        return "ONE"
    if value < 10:
        return "TWO_TO_NINE"
    return "TEN_PLUS"
