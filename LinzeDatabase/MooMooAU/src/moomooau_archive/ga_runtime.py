"""Fail-closed GA discovery-to-Timeline runner for Stage 7 T0705.

This module owns deterministic orchestration only.  Every Gmail, private-repository, age and
Release adapter is injected; there is no environment discovery or executable production entry
point.  A run opens only after all protected predecessor observations, an explicit stable M3
budget, a current parser and capacity authorization pass.  Its Gmail History checkpoint is
committed last and accepted only after encrypted remote recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesHeaderParser
from functools import partial

from .attachment_inspector import AttachmentInspector
from .blue_green_runtime import CurrentProcessedPointerSource
from .canary_runtime import FirstImportTimestampSource, ProcessedPlanFactory
from .canonical_raw import CanonicalRaw, CanonicalRawFetcher
from .capacity import git_capacity_demand, reserved_git_capacity_demand
from .document_parser import (
    ParserActivation,
    ParserOutcome,
    ParserProfile,
    ParserProfileRegistry,
    ProcessingDisposition,
    SafeArtifactExtractor,
    StatementParser,
)
from .gmail_discovery import (
    GmailReadClient,
    GmailReconciler,
    MessageRef,
    ReconcileMode,
)
from .gmail_sync_checkpoint import (
    MAXIMUM_GMAIL_SYNC_CIPHERTEXT_BYTES,
    EncryptedGmailSyncCheckpoint,
    GmailRunCheckpoint,
    GmailSyncCheckpointCommitResult,
)
from .m3 import ExactMessageTrashExecutor, M3State, MutationBudget, MutationPhase
from .market_calendar import ExpectationPolicy, USMarketCalendar
from .operation_gate import OperationalGate, SensitiveOperation
from .processed_commit import ProcessedCommitSaga
from .processed_models import (
    ClassificationActivation,
    ClassificationRegistry,
    DocumentClass,
    DocumentClassifier,
    DocumentEnvelope,
    DocumentEnvelopeFactory,
)
from .processed_product import ProcessedBundle, ProcessedProductBuilder
from .raw_commit import RawCommitPlanner, RawCommitSaga
from .release_control import FeatureFlags, PhaseObservation, ReleasePhase, Stage7ReleaseGate
from .remote_recovery_gate import RemoteRecoveryGate
from .run_schedule import RunMode, RunTrigger, ScheduledRunPlan
from .sender_registry import (
    RegistryActivation,
    SenderDecision,
    SenderRegistry,
    SenderVerifier,
    VerificationPhase,
)
from .timeline_event import TimelineEvent, TimelineEventFactory
from .timeline_publish import (
    MAXIMUM_TIMELINE_ASSET_CIPHERTEXT_BYTES,
    MAXIMUM_TIMELINE_STATE_CIPHERTEXT_BYTES,
    MAXIMUM_TIMELINE_STATE_MUTATIONS_PER_PUBLISH,
    SingleLatestTimelinePublisher,
    TimelinePublishAction,
    TimelinePublishStateName,
)
from .timeline_snapshot import (
    TimelineSnapshotCommitSaga,
    TimelineSnapshotFact,
    TimelineSnapshotPlanner,
    TimelineSnapshotRecoveryGate,
    TimelineSnapshotRecoveryProof,
)


class GARuntimeError(RuntimeError):
    """The GA run stopped without exposing mailbox, repository or financial values."""


@dataclass(frozen=True, slots=True, repr=False)
class GAFullPipelineRunResult:
    phase: ReleasePhase
    trigger: RunTrigger
    mode: RunMode
    scheduled_0430_target: bool
    catch_up_required: bool
    reconciliation_mode: ReconcileMode
    full_reconcile_runs: int
    full_reconcile_comparisons: int
    full_reconcile_difference: int | None
    candidate_refs: int
    metadata_reads: int
    verified_candidates: int
    unknown_candidates: int
    rejected_candidates: int
    quarantined_candidates: int
    raw_archived: int
    processed_complete: int
    processed_safe_deferred: int
    processing_blocked: int
    full_recovery_successes: int
    mutation_budget_max: int
    mutation_calls: int
    confirmed_trashed: int
    already_trashed: int
    deferred_mutations: int
    timeline_snapshot_recoveries: int
    timeline_publish_attempts: int
    final_live_timeline_assets: int
    timeline_action: TimelinePublishAction
    timeline_state: TimelinePublishStateName
    sync_checkpoint_mutations: int
    sync_checkpoint_recoveries: int
    pending_verified_refs: int

    def __post_init__(self) -> None:
        counters = (
            self.full_reconcile_runs,
            self.full_reconcile_comparisons,
            self.candidate_refs,
            self.metadata_reads,
            self.verified_candidates,
            self.unknown_candidates,
            self.rejected_candidates,
            self.quarantined_candidates,
            self.raw_archived,
            self.processed_complete,
            self.processed_safe_deferred,
            self.processing_blocked,
            self.full_recovery_successes,
            self.mutation_budget_max,
            self.mutation_calls,
            self.confirmed_trashed,
            self.already_trashed,
            self.deferred_mutations,
            self.timeline_snapshot_recoveries,
            self.timeline_publish_attempts,
            self.final_live_timeline_assets,
            self.sync_checkpoint_mutations,
            self.sync_checkpoint_recoveries,
            self.pending_verified_refs,
        )
        recovered_processed = self.processed_complete + self.processed_safe_deferred
        if (
            self.phase is not ReleasePhase.GA
            or not isinstance(self.trigger, RunTrigger)
            or not isinstance(self.mode, RunMode)
            or type(self.scheduled_0430_target) is not bool
            or self.scheduled_0430_target != (self.trigger is RunTrigger.SCHEDULE)
            or type(self.catch_up_required) is not bool
            or not isinstance(self.reconciliation_mode, ReconcileMode)
            or any(type(value) is not int or value < 0 for value in counters)
            or self.full_reconcile_runs not in {0, 1}
            or self.full_reconcile_comparisons not in {0, 1}
            or self.full_reconcile_comparisons != int(self.full_reconcile_difference is not None)
            or (
                self.full_reconcile_difference is not None
                and (
                    type(self.full_reconcile_difference) is not int
                    or self.full_reconcile_difference != 0
                    or self.full_reconcile_runs != 1
                )
            )
            or self.metadata_reads < self.candidate_refs
            or self.verified_candidates
            + self.unknown_candidates
            + self.rejected_candidates
            + self.quarantined_candidates
            != self.candidate_refs
            or self.raw_archived != self.verified_candidates
            or recovered_processed + self.processing_blocked != self.raw_archived
            or self.full_recovery_successes != recovered_processed
            or self.confirmed_trashed + self.already_trashed + self.deferred_mutations
            != self.full_recovery_successes
            or self.mutation_budget_max <= 0
            or self.mutation_calls != self.confirmed_trashed
            or self.mutation_calls > self.mutation_budget_max
            or self.timeline_snapshot_recoveries != 1
            or self.timeline_publish_attempts != 1
            or self.final_live_timeline_assets != 1
            or not isinstance(self.timeline_action, TimelinePublishAction)
            or self.timeline_state is not TimelinePublishStateName.HEALTHY
            or self.sync_checkpoint_mutations not in {0, 1}
            or self.sync_checkpoint_recoveries != 1
        ):
            raise GARuntimeError("GA full-pipeline result is internally inconsistent")

    def __repr__(self) -> str:
        return (
            f"GAFullPipelineRunResult(phase={self.phase.value!r}, "
            f"trigger={self.trigger.value!r}, mode={self.mode.value!r}, "
            "mailbox_counts=<redacted>, private_values=<redacted>, "
            f"mutation_budget_max={self.mutation_budget_max}, "
            f"timeline_state={self.timeline_state.value!r})"
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": "moomooau.ga-full-pipeline-run-public.v1",
            "phase": self.phase.value,
            "run_status": "GA_MECHANISM_COMPLETED_NOT_FINAL",
            "trigger": self.trigger.value,
            "mode": self.mode.value,
            "target_time": "04:30",
            "timezone": "Australia/Sydney",
            "scheduled_0430_target": self.scheduled_0430_target,
            "catch_up_required": self.catch_up_required,
            "full_reconcile_runs": self.full_reconcile_runs,
            "full_reconcile_comparison": (
                "ZERO_DIFFERENCE"
                if self.full_reconcile_difference == 0
                else ("NOT_RUN" if self.full_reconcile_runs == 0 else "NOT_COMPARABLE")
            ),
            "verified_bucket": _bucket(self.verified_candidates),
            "processed_or_safe_deferred_bucket": _bucket(self.full_recovery_successes),
            "mutation_budget_max": self.mutation_budget_max,
            "mutation_calls_bucket": _bucket(self.mutation_calls),
            "timeline_publish_attempts": 1,
            "final_live_timeline_assets": 1,
            "sync_checkpoint_remote_recovery": True,
            "pending_verified_bucket": _bucket(self.pending_verified_refs),
            "production_health_claimed": False,
        }


@dataclass(frozen=True, slots=True, repr=False)
class GAFullPipelineOutcome:
    result: GAFullPipelineRunResult
    sync_checkpoint: GmailSyncCheckpointCommitResult
    timeline_snapshot: TimelineSnapshotRecoveryProof

    def __post_init__(self) -> None:
        if (
            not isinstance(self.result, GAFullPipelineRunResult)
            or not isinstance(self.sync_checkpoint, GmailSyncCheckpointCommitResult)
            or not isinstance(self.timeline_snapshot, TimelineSnapshotRecoveryProof)
            or self.result.sync_checkpoint_mutations != self.sync_checkpoint.state_mutations
            or self.result.final_live_timeline_assets != 1
        ):
            raise GARuntimeError("GA full-pipeline outcome is inconsistent")

    def __repr__(self) -> str:
        return "GAFullPipelineOutcome(result=<aggregate>, private_proofs=<redacted>)"


class GAFullPipelineRunner:
    """Run discovery, Raw, Processed, exact-message M3 and one recovered Timeline."""

    def __init__(
        self,
        gmail: GmailReadClient,
        reconciler: GmailReconciler,
        sync_checkpoint: EncryptedGmailSyncCheckpoint,
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
        current_pointer_source: CurrentProcessedPointerSource,
        snapshot_planner: TimelineSnapshotPlanner,
        snapshot_commit: TimelineSnapshotCommitSaga,
        snapshot_recovery: TimelineSnapshotRecoveryGate,
        timeline_publisher: SingleLatestTimelinePublisher,
        operational_gate: OperationalGate,
    ) -> None:
        if (
            sender_registry.activation is not RegistryActivation.ACTIVE
            or classification_registry.activation is not ClassificationActivation.ACTIVE
            or parser_registry.activation is not ParserActivation.ACTIVE
        ):
            raise GARuntimeError("protected GA registries are not active")
        self._gmail = gmail
        self._reconciler = reconciler
        self._sync_checkpoint = sync_checkpoint
        self._sender_registry = sender_registry
        self._verifier = verifier
        self._raw_fetcher = raw_fetcher
        self._inspector = inspector
        self._raw_planner = raw_planner
        self._raw_commit = raw_commit
        self._classification_registry = classification_registry
        self._parser_registry = parser_registry
        self._processed_plan_factory = processed_plan_factory
        self._processed_commit = processed_commit
        self._recovery = recovery
        self._trash_executor = trash_executor
        self._first_import_timestamps = first_import_timestamps
        self._current_pointer_source = current_pointer_source
        self._snapshot_planner = snapshot_planner
        self._snapshot_commit = snapshot_commit
        self._snapshot_recovery = snapshot_recovery
        self._timeline_publisher = timeline_publisher
        self._operational_gate = operational_gate
        self._classifier = DocumentClassifier()
        self._envelope_factory = DocumentEnvelopeFactory()
        self._extractor = SafeArtifactExtractor()
        self._parser = StatementParser()
        self._product_builder = ProcessedProductBuilder()
        self._event_factory = TimelineEventFactory(USMarketCalendar())
        self._expectation_policy = ExpectationPolicy()

    def run(
        self,
        plan: ScheduledRunPlan,
        *,
        key_epoch: str,
        parser_current_version: str,
        predecessor_observations: tuple[PhaseObservation, ...],
        beta_message_budget: int,
        ga_mutation_budget_per_run: int,
        ga_capacity_authorized: bool,
    ) -> GAFullPipelineOutcome:
        if (
            not isinstance(plan, ScheduledRunPlan)
            or not key_epoch
            or not _is_utc(plan.started_at_utc)
            or type(ga_capacity_authorized) is not bool
        ):
            raise GARuntimeError("GA run configuration is invalid")
        promotion = Stage7ReleaseGate().evaluate_promotion(
            ReleasePhase.GA,
            predecessor_observations,
            beta_message_budget=beta_message_budget,
            parser_current_version=parser_current_version,
            ga_mutation_budget_per_run=ga_mutation_budget_per_run,
            ga_capacity_authorized=ga_capacity_authorized,
        )
        if not promotion.ready:
            raise GARuntimeError("GA protected predecessor or capacity gate is blocked")
        flags = FeatureFlags.for_phase(
            ReleasePhase.GA,
            parser_current_version=parser_current_version,
            ga_mutation_budget_per_run=ga_mutation_budget_per_run,
        )
        if not all(
            (
                flags.discovery_enabled,
                flags.raw_archive_enabled,
                flags.processing_enabled,
                flags.m3_enabled,
                flags.timeline_enabled,
                flags.public_evidence_enabled,
                flags.full_reconcile_enabled,
            )
        ) or not any(
            profile.parser_version == parser_current_version
            for profile in self._parser_registry.profiles
        ):
            raise GARuntimeError("GA feature or current parser configuration is invalid")

        # Every capability and the explicit stable budget are closed before the first injected
        # remote read.  Individual writes are authorized again at their exact call sites.
        for operation in (
            SensitiveOperation.PRODUCTION_RUN,
            SensitiveOperation.RAW_WRITE,
            SensitiveOperation.PROCESSED_WRITE,
            SensitiveOperation.M3,
            SensitiveOperation.TIMELINE_WRITE,
        ):
            self._operational_gate.preflight(operation)
        budget = MutationBudget.for_phase(
            MutationPhase.STABLE,
            stable_maximum_calls=ga_mutation_budget_per_run,
        )
        recovered_checkpoint = self._operational_gate.execute(
            SensitiveOperation.REMOTE_READ,
            self._sync_checkpoint.recover,
        )
        audit = self._reconciler.reconcile_for_run(
            (
                recovered_checkpoint.checkpoint.sync_state
                if recovered_checkpoint is not None
                else None
            ),
            now_sydney=plan.started_at_utc.astimezone(plan.target_at_sydney.tzinfo),
            full_reconcile=plan.full_reconcile,
        )
        if audit.full_difference_count not in {None, 0}:
            raise GARuntimeError("Full Reconciliation candidate set differs from full truth")

        previous_snapshot_root = self._operational_gate.execute(
            SensitiveOperation.REMOTE_READ,
            self._timeline_publisher.recover_committed_snapshot_root,
        )
        facts_by_source: dict[str, TimelineSnapshotFact] = {}
        if previous_snapshot_root is not None:
            previous = self._operational_gate.execute(
                SensitiveOperation.REMOTE_READ,
                partial(self._snapshot_recovery.recover_root, previous_snapshot_root),
            )
            for fact in previous.facts:
                current = self._current_pointer_source.resolve(fact.event.source_id)
                if current.pointer != fact.current_pointer:
                    raise GARuntimeError("prior Timeline fact is no longer current")
                facts_by_source[fact.event.source_id] = fact

        known_refs = {item.message_id: item for item in audit.result.state.known_refs}
        candidates = {item.message_id: item for item in audit.result.changed_refs}
        prior_pending_ids: set[str] = set()
        if recovered_checkpoint is not None:
            for ref in recovered_checkpoint.checkpoint.pending_verified_refs:
                prior_pending_ids.add(ref.message_id)
                current_ref = known_refs.get(ref.message_id)
                if current_ref is None or current_ref.thread_id != ref.thread_id:
                    raise GARuntimeError("pending verified source disappeared or changed identity")
                candidates[ref.message_id] = current_ref
        candidate_refs = tuple(candidates[key] for key in sorted(candidates))

        metadata_reads = verified = unknown = rejected = quarantined = 0
        raw_archived = complete = safe_deferred = processing_blocked = recovered = 0
        confirmed = already = deferred = 0
        pending: dict[str, MessageRef] = {}
        for ref in candidate_refs:
            message = self._gmail.get_metadata(
                ref.message_id,
                header_names=self._sender_registry.requested_header_names,
            )
            metadata_reads += 1
            first = self._verifier.verify_message(
                message,
                self._sender_registry,
                phase=VerificationPhase.PRE_RAW,
            )
            if first.decision is not SenderDecision.VERIFIED:
                if first.decision is SenderDecision.UNKNOWN:
                    unknown += 1
                elif first.decision is SenderDecision.REJECTED:
                    rejected += 1
                else:
                    quarantined += 1
                if ref.message_id in prior_pending_ids:
                    pending[ref.message_id] = ref
                continue
            verified += 1
            permit = first.raw_fetch_permit
            if permit is None:
                raise GARuntimeError("verified PRE_RAW result did not issue a fetch permit")
            canonical = self._raw_fetcher.fetch(permit, self._sender_registry)
            attachments = self._inspector.inspect(canonical)
            raw_plan = self._raw_planner.plan(canonical, attachments, key_epoch=key_epoch)
            self._operational_gate.execute(
                SensitiveOperation.RAW_WRITE,
                partial(self._raw_commit.commit, raw_plan),
                demand=git_capacity_demand(item.ciphertext for item in raw_plan.objects),
            )
            raw_proof = self._recovery.verify_raw_only(canonical, first, raw_plan)
            if raw_proof.recovered_object_count != len(raw_plan.objects):
                raise GARuntimeError("GA Raw remote recovery count differs from the plan")
            raw_archived += 1

            classification = self._classifier.classify(
                canonical,
                first,
                attachments,
                self._classification_registry,
            )
            imported_at_utc = self._first_import_timestamps.resolve(
                raw_plan.opaque_message_id,
                plan.started_at_utc,
            )
            if not _is_utc(imported_at_utc) or imported_at_utc > plan.started_at_utc:
                raise GARuntimeError("first-import timestamp is invalid")
            envelope = self._envelope_factory.issue(
                canonical,
                first,
                attachments,
                raw_plan,
                classification,
                imported_at_utc=imported_at_utc,
                recovered_raw_ciphertext_sha256=raw_proof.raw_ciphertext_sha256,
            )
            extraction = self._extractor.extract(attachments)
            profile = self._profile_for(
                classification.document_class,
                parser_current_version,
            )
            outcome = self._parser.parse(envelope, classification, extraction, profile)
            if outcome.disposition is ProcessingDisposition.BLOCKED:
                processing_blocked += 1
                pending[ref.message_id] = ref
                continue
            bundle = self._product_builder.build(envelope, outcome)
            processed_plan = self._processed_plan_factory.plan(bundle, key_epoch=key_epoch)
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
                raise GARuntimeError("GA full remote recovery count differs from the plans")
            recovered += 1
            if outcome.disposition is ProcessingDisposition.COMPLETE:
                complete += 1
            else:
                safe_deferred += 1

            timeline_m3_state = M3State.ELIGIBLE
            can_confirm_without_new_call = "TRASH" in message.label_ids
            if budget.consumed_calls < budget.maximum_calls or can_confirm_without_new_call:
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
                m3_result = self._operational_gate.execute(
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
                if m3_result.state is M3State.TRASHED:
                    confirmed += 1
                    timeline_m3_state = M3State.TRASHED
                elif m3_result.state is M3State.ALREADY_TRASHED:
                    already += 1
                    # Normalize the final Gmail state so an idempotent retry does not change the
                    # Timeline solely because it observed rather than performed the same Trash.
                    timeline_m3_state = M3State.TRASHED
                else:
                    raise GARuntimeError("exact source-message Trash outcome is unresolved")
            else:
                deferred += 1
                pending[ref.message_id] = ref

            current = self._current_pointer_source.resolve(bundle.source_id)
            if not _pointer_matches_bundle(current.pointer, bundle, key_epoch):
                raise GARuntimeError("current Processed pointer differs from recovered output")
            event = self._timeline_event(
                envelope,
                outcome,
                canonical,
                timeline_m3_state,
            )
            facts_by_source[event.source_id] = TimelineSnapshotFact(current.pointer, event)

        if not facts_by_source:
            raise GARuntimeError("GA Timeline has no recovered current Processed facts")
        snapshot_plan = self._snapshot_planner.plan(
            tuple(facts_by_source.values()),
            key_epoch=key_epoch,
        )
        self._operational_gate.execute(
            SensitiveOperation.PROCESSED_WRITE,
            partial(self._snapshot_commit.commit, snapshot_plan),
            demand=git_capacity_demand(item.ciphertext for item in snapshot_plan.objects),
        )
        snapshot_proof = self._snapshot_recovery.verify(snapshot_plan)
        if snapshot_proof.recovered_object_count != len(snapshot_plan.objects):
            raise GARuntimeError("GA Timeline snapshot recovery count differs")
        for fact in snapshot_proof.facts:
            current = self._current_pointer_source.resolve(fact.event.source_id)
            if current.pointer != fact.current_pointer:
                raise GARuntimeError("current Processed pointer changed before GA Timeline publish")
        publish = self._operational_gate.execute(
            SensitiveOperation.TIMELINE_WRITE,
            partial(
                self._timeline_publisher.publish,
                tuple(fact.event for fact in snapshot_proof.facts),
                processed_snapshot_root=snapshot_proof.processed_snapshot_root,
                key_epoch=key_epoch,
                now_utc=plan.started_at_utc,
            ),
            demand=reserved_git_capacity_demand(
                MAXIMUM_TIMELINE_STATE_CIPHERTEXT_BYTES,
                mutation_count=MAXIMUM_TIMELINE_STATE_MUTATIONS_PER_PUBLISH,
                release_asset_bytes=MAXIMUM_TIMELINE_ASSET_CIPHERTEXT_BYTES,
            ),
        )
        if publish.state is not TimelinePublishStateName.HEALTHY or publish.asset_count != 1:
            raise GARuntimeError("GA Timeline did not converge to exactly one recoverable Asset")

        checkpoint = self._operational_gate.execute(
            SensitiveOperation.PROCESSED_WRITE,
            partial(
                self._sync_checkpoint.commit,
                recovered_checkpoint,
                GmailRunCheckpoint(
                    audit.result.state,
                    tuple(pending[key] for key in sorted(pending)),
                    plan.run_date_sydney,
                ),
            ),
            demand=reserved_git_capacity_demand(MAXIMUM_GMAIL_SYNC_CIPHERTEXT_BYTES),
        )
        result = GAFullPipelineRunResult(
            phase=ReleasePhase.GA,
            trigger=plan.trigger,
            mode=plan.mode,
            scheduled_0430_target=plan.trigger is RunTrigger.SCHEDULE,
            catch_up_required=plan.catch_up_required,
            reconciliation_mode=audit.result.mode,
            full_reconcile_runs=audit.full_reconcile_runs,
            full_reconcile_comparisons=int(audit.full_difference_count is not None),
            full_reconcile_difference=audit.full_difference_count,
            candidate_refs=len(candidate_refs),
            metadata_reads=metadata_reads,
            verified_candidates=verified,
            unknown_candidates=unknown,
            rejected_candidates=rejected,
            quarantined_candidates=quarantined,
            raw_archived=raw_archived,
            processed_complete=complete,
            processed_safe_deferred=safe_deferred,
            processing_blocked=processing_blocked,
            full_recovery_successes=recovered,
            mutation_budget_max=budget.maximum_calls,
            mutation_calls=budget.consumed_calls,
            confirmed_trashed=confirmed,
            already_trashed=already,
            deferred_mutations=deferred,
            timeline_snapshot_recoveries=1,
            timeline_publish_attempts=1,
            final_live_timeline_assets=publish.asset_count,
            timeline_action=publish.action,
            timeline_state=publish.state,
            sync_checkpoint_mutations=checkpoint.state_mutations,
            sync_checkpoint_recoveries=1,
            pending_verified_refs=len(pending),
        )
        return GAFullPipelineOutcome(result, checkpoint, snapshot_proof)

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
            raise GARuntimeError("multiple current parser profiles match one document")
        return matches[0] if matches else None

    def _timeline_event(
        self,
        envelope: DocumentEnvelope,
        outcome: ParserOutcome,
        canonical: CanonicalRaw,
        m3_state: M3State,
    ) -> TimelineEvent:
        statement = outcome.statement
        final_envelope = envelope.with_processing(
            outcome.state,
            outcome.reason_code,
            parser_name=outcome.parser_name,
            parser_version=outcome.parser_version,
            field_lineage=statement.field_lineage if statement is not None else (),
        )
        expectation = self._expectation_policy.assess(
            observed=True,
            independent_activity_evidence=None,
            market_session_expected=None,
            sla_exceeded=None,
            parser_state=outcome.state,
        )
        return self._event_factory.issue(
            final_envelope,
            statement_label_date=(
                statement.statement_label_date if statement is not None else None
            ),
            date_header_observed=_date_header(canonical.data),
            m3_state=m3_state,
            expectation=expectation,
        )


def _pointer_matches_bundle(pointer: object, bundle: ProcessedBundle, key_epoch: str) -> bool:
    return all(
        getattr(pointer, name, None) == expected
        for name, expected in (
            ("source_id", bundle.source_id),
            ("parser_name", bundle.parser_name),
            ("parser_version", bundle.parser_version),
            ("schema_version", bundle.schema_version),
            ("business_root", bundle.business_root),
            ("snapshot_root", bundle.snapshot_root),
            ("key_epoch", key_epoch),
        )
    )


def _date_header(raw: bytes) -> str | None:
    try:
        parsed = BytesHeaderParser(policy=policy.default).parsebytes(raw, headersonly=True)
    except Exception:
        return None
    if parsed.defects:
        return None
    values = parsed.get_all("Date", [])
    if len(values) != 1:
        return None
    value = str(values[0])
    defects = getattr(values[0], "defects", ())
    if defects or not value or len(value) > 16_384 or "\r" in value or "\n" in value:
        return None
    return value


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
