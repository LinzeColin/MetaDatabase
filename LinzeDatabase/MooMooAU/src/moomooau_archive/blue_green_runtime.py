"""Fail-closed Parser/Timeline Blue-Green mechanism for Stage 7 T0704.

The runner accepts one Raw object that has already passed remote recovery, parses that exact
plaintext through incumbent and candidate profiles, appends/re-recovers only the candidate
Processed partition, proves the encrypted current pointer did not change, commits/re-recovers a
deterministic Timeline fact snapshot, and only then invokes the single-latest publisher.  It has
no Gmail transport or pointer-promotion capability.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesHeaderParser
from functools import partial
from typing import Protocol

from .attachment_inspector import AttachmentInspector
from .canonical_raw import CanonicalRaw
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
from .m3 import M3State
from .market_calendar import ExpectationPolicy, USMarketCalendar
from .operation_gate import OperationalGate, SensitiveOperation
from .processed_commit import (
    CurrentProcessedPointer,
    ParserBlueGreenComparator,
    ProcessedCiphertextStore,
    ProcessedCommitPlanner,
    ProcessedCommitSaga,
    ProcessedCommitState,
    PromotionAction,
)
from .processed_models import (
    ClassificationActivation,
    ClassificationRegistry,
    DocumentClass,
    DocumentClassifier,
    DocumentEnvelope,
    DocumentEnvelopeFactory,
)
from .processed_product import ProcessedBundle, ProcessedProductBuilder
from .raw_commit import RawCommitPlan, RawObjectRole
from .release_control import FeatureFlags, PhaseObservation, ReleasePhase, Stage7ReleaseGate
from .remote_recovery_gate import (
    CiphertextDecryptor,
    MessageRecoveryProof,
    RecoveryScope,
    RemoteRecoveryGate,
)
from .sender_registry import MessageVerification, SenderDecision, VerificationPhase
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

_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEMVER = re.compile(r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")


class BlueGreenRuntimeError(RuntimeError):
    """The T0704 mechanism failed closed without exposing private values."""


@dataclass(frozen=True, slots=True, repr=False)
class RecoveredCurrentPointer:
    pointer: CurrentProcessedPointer
    revision: str
    ciphertext_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.pointer, CurrentProcessedPointer)
            or _REVISION.fullmatch(self.revision) is None
            or _SHA256.fullmatch(self.ciphertext_sha256) is None
        ):
            raise BlueGreenRuntimeError("recovered current pointer is invalid")

    def __repr__(self) -> str:
        return (
            "RecoveredCurrentPointer(pointer=<redacted>, revision=<redacted>, "
            "ciphertext_sha256=<redacted>)"
        )


class CurrentProcessedPointerSource(Protocol):
    def resolve(self, source_id: str) -> RecoveredCurrentPointer: ...


class RemoteCurrentProcessedPointerSource:
    """Decrypt the exact current pointer from the single private Processed store."""

    def __init__(
        self,
        store: ProcessedCiphertextStore,
        decryptor: CiphertextDecryptor,
    ) -> None:
        self._store = store
        self._decryptor = decryptor

    def resolve(self, source_id: str) -> RecoveredCurrentPointer:
        if _SHA256.fullmatch(source_id) is None:
            raise BlueGreenRuntimeError("current pointer source ID is invalid")
        path = f"MooMooAU/State/processed-current/{source_id}.json.age"
        revisioned = self._store.fetch_current(path)
        if revisioned is None:
            raise BlueGreenRuntimeError("current Processed pointer is unavailable")
        try:
            pointer = CurrentProcessedPointer.from_bytes(
                self._decryptor.decrypt(revisioned.ciphertext)
            )
        except Exception as exc:
            raise BlueGreenRuntimeError("current Processed pointer recovery failed") from exc
        if pointer.source_id != source_id:
            raise BlueGreenRuntimeError("current Processed pointer source differs")
        return RecoveredCurrentPointer(
            pointer,
            revisioned.revision,
            hashlib.sha256(revisioned.ciphertext).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class BlueGreenTimelineRunResult:
    phase: ReleasePhase
    observed_days: int
    candidate_action: PromotionAction
    candidate_reason_code: str
    parser_comparisons: int
    candidate_processed_recoveries: int
    unresolved_comparison_differences: int
    current_pointer_mutations: int
    timeline_snapshot_recoveries: int
    timeline_publish_attempts: int
    final_live_timeline_assets: int
    timeline_action: TimelinePublishAction
    timeline_state: TimelinePublishStateName
    ready_for_protected_promotion: bool

    def __post_init__(self) -> None:
        allowed_actions = {
            PromotionAction.SEMANTICALLY_EQUAL_PROMOTION,
            PromotionAction.PROTECTED_APPROVAL_REQUIRED,
        }
        counters = (
            self.observed_days,
            self.parser_comparisons,
            self.candidate_processed_recoveries,
            self.unresolved_comparison_differences,
            self.current_pointer_mutations,
            self.timeline_snapshot_recoveries,
            self.timeline_publish_attempts,
            self.final_live_timeline_assets,
        )
        expected_ready = (
            self.candidate_action is PromotionAction.SEMANTICALLY_EQUAL_PROMOTION
            and self.unresolved_comparison_differences == 0
            and self.timeline_state is TimelinePublishStateName.HEALTHY
            and self.final_live_timeline_assets == 1
        )
        if (
            self.phase is not ReleasePhase.BLUE_GREEN
            or self.candidate_action not in allowed_actions
            or not self.candidate_reason_code
            or len(self.candidate_reason_code) > 256
            or "\r" in self.candidate_reason_code
            or "\n" in self.candidate_reason_code
            or any(type(value) is not int or value < 0 for value in counters)
            or self.parser_comparisons != 1
            or self.candidate_processed_recoveries != 1
            or self.unresolved_comparison_differences not in {0, 1}
            or self.current_pointer_mutations != 0
            or self.timeline_snapshot_recoveries != 1
            or self.timeline_publish_attempts != 1
            or self.final_live_timeline_assets not in {0, 1}
            or not isinstance(self.timeline_action, TimelinePublishAction)
            or not isinstance(self.timeline_state, TimelinePublishStateName)
            or (self.timeline_state is TimelinePublishStateName.HEALTHY)
            != (self.final_live_timeline_assets == 1)
            or type(self.ready_for_protected_promotion) is not bool
            or self.ready_for_protected_promotion != expected_ready
        ):
            raise BlueGreenRuntimeError("Blue-Green Timeline result is inconsistent")

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema_version": "moomooau.blue-green-timeline-run-public.v1",
            "phase": self.phase.value,
            "run_status": "BLUE_GREEN_MECHANISM_COMPLETED_NOT_FINAL",
            "calendar_wait_required": False,
            "deterministic_evidence_complete": (
                self.parser_comparisons == 1
                and self.candidate_processed_recoveries == 1
                and self.timeline_snapshot_recoveries == 1
                and self.timeline_publish_attempts == 1
                and self.timeline_state is TimelinePublishStateName.HEALTHY
                and self.final_live_timeline_assets == 1
            ),
            "candidate_action": self.candidate_action.value,
            "parser_comparisons": self.parser_comparisons,
            "unresolved_comparison_differences": self.unresolved_comparison_differences,
            "current_pointer_mutations": 0,
            "timeline_snapshot_recoveries": self.timeline_snapshot_recoveries,
            "timeline_publish_attempts": self.timeline_publish_attempts,
            "final_live_timeline_assets": self.final_live_timeline_assets,
            "timeline_state": self.timeline_state.value,
            "ready_for_protected_promotion": self.ready_for_protected_promotion,
            "production_health_claimed": False,
        }


class BlueGreenTimelineRunner:
    """Shadow one candidate and publish only facts selected by recovered current pointers."""

    def __init__(
        self,
        classification_registry: ClassificationRegistry,
        parser_registry: ParserProfileRegistry,
        current_pointer_source: CurrentProcessedPointerSource,
        processed_planner: ProcessedCommitPlanner,
        processed_commit: ProcessedCommitSaga,
        processed_recovery: RemoteRecoveryGate,
        snapshot_planner: TimelineSnapshotPlanner,
        snapshot_commit: TimelineSnapshotCommitSaga,
        snapshot_recovery: TimelineSnapshotRecoveryGate,
        timeline_publisher: SingleLatestTimelinePublisher,
        operational_gate: OperationalGate,
    ) -> None:
        if (
            classification_registry.activation is not ClassificationActivation.ACTIVE
            or parser_registry.activation is not ParserActivation.ACTIVE
        ):
            raise BlueGreenRuntimeError("protected Blue-Green registries are not active")
        self._classification_registry = classification_registry
        self._parser_registry = parser_registry
        self._current_pointer_source = current_pointer_source
        self._processed_planner = processed_planner
        self._processed_commit = processed_commit
        self._processed_recovery = processed_recovery
        self._snapshot_planner = snapshot_planner
        self._snapshot_commit = snapshot_commit
        self._snapshot_recovery = snapshot_recovery
        self._timeline_publisher = timeline_publisher
        self._operational_gate = operational_gate
        self._inspector = AttachmentInspector()
        self._classifier = DocumentClassifier()
        self._envelope_factory = DocumentEnvelopeFactory()
        self._extractor = SafeArtifactExtractor()
        self._parser = StatementParser()
        self._product_builder = ProcessedProductBuilder()
        self._comparator = ParserBlueGreenComparator()
        self._event_factory = TimelineEventFactory(USMarketCalendar())
        self._expectation_policy = ExpectationPolicy()

    def run(
        self,
        canonical: CanonicalRaw,
        first_verification: MessageVerification,
        raw_plan: RawCommitPlan,
        raw_recovery: MessageRecoveryProof,
        *,
        incumbent_parser_version: str,
        candidate_parser_version: str,
        key_epoch: str,
        imported_at_utc: datetime,
        observed_at_utc: datetime,
        observed_days: int,
        m3_state: M3State,
        independent_activity_evidence: bool | None,
        market_session_expected: bool | None,
        sla_exceeded: bool | None,
        predecessor_observations: tuple[PhaseObservation, ...],
        beta_message_budget: int,
    ) -> tuple[BlueGreenTimelineRunResult, TimelineSnapshotRecoveryProof]:
        if (
            _SEMVER.fullmatch(incumbent_parser_version) is None
            or _SEMVER.fullmatch(candidate_parser_version) is None
            or type(observed_days) is not int
            or observed_days < 0
            or not key_epoch
            or not _is_utc(imported_at_utc)
            or not _is_utc(observed_at_utc)
            or imported_at_utc > observed_at_utc
            or m3_state not in {M3State.TRASHED, M3State.ALREADY_TRASHED}
            or any(
                value is not None and type(value) is not bool
                for value in (
                    independent_activity_evidence,
                    market_session_expected,
                    sla_exceeded,
                )
            )
        ):
            raise BlueGreenRuntimeError("Blue-Green run configuration is invalid")
        promotion = Stage7ReleaseGate().evaluate_promotion(
            ReleasePhase.BLUE_GREEN,
            predecessor_observations,
            beta_message_budget=beta_message_budget,
            parser_current_version=incumbent_parser_version,
        )
        if not promotion.ready:
            raise BlueGreenRuntimeError("Blue-Green protected predecessor gate is blocked")
        flags = FeatureFlags.for_phase(
            ReleasePhase.BLUE_GREEN,
            parser_current_version=incumbent_parser_version,
        )
        if (
            not flags.processing_enabled
            or not flags.m3_enabled
            or not flags.timeline_enabled
            or flags.mutation_budget_per_run != 1
        ):
            raise BlueGreenRuntimeError("Blue-Green feature configuration is invalid")
        self._validate_recovered_raw(
            canonical,
            first_verification,
            raw_plan,
            raw_recovery,
            key_epoch,
        )

        # Capacity/Kill authorization precedes every injected remote source or store call.
        self._operational_gate.preflight(SensitiveOperation.PRODUCTION_RUN)
        self._operational_gate.preflight(SensitiveOperation.PROCESSED_WRITE)
        self._operational_gate.preflight(SensitiveOperation.TIMELINE_WRITE)
        previous_snapshot_root = self._operational_gate.execute(
            SensitiveOperation.REMOTE_READ,
            self._timeline_publisher.recover_committed_snapshot_root,
        )

        attachments = self._inspector.inspect(canonical)
        classification = self._classifier.classify(
            canonical,
            first_verification,
            attachments,
            self._classification_registry,
        )
        incumbent_profile = self._profile_for(
            classification.document_class,
            incumbent_parser_version,
        )
        candidate_profile = self._profile_for(
            classification.document_class,
            candidate_parser_version,
        )
        if (
            incumbent_profile is None
            or candidate_profile is None
            or incumbent_profile.parser_name != candidate_profile.parser_name
            or _semver_key(candidate_parser_version) <= _semver_key(incumbent_parser_version)
        ):
            raise BlueGreenRuntimeError("Blue-Green parser pair is invalid")

        envelope = self._envelope_factory.issue(
            canonical,
            first_verification,
            attachments,
            raw_plan,
            classification,
            imported_at_utc=imported_at_utc,
            recovered_raw_ciphertext_sha256=raw_recovery.raw_ciphertext_sha256,
        )
        extraction = self._extractor.extract(attachments)
        incumbent_outcome = self._parser.parse(
            envelope,
            classification,
            extraction,
            incumbent_profile,
        )
        candidate_outcome = self._parser.parse(
            envelope,
            classification,
            extraction,
            candidate_profile,
        )
        if any(
            outcome.disposition is ProcessingDisposition.BLOCKED
            for outcome in (incumbent_outcome, candidate_outcome)
        ):
            raise BlueGreenRuntimeError("Blue-Green parser output is quarantined")
        incumbent_bundle = self._product_builder.build(envelope, incumbent_outcome)
        candidate_bundle = self._product_builder.build(envelope, candidate_outcome)

        before = self._current_pointer_source.resolve(incumbent_bundle.source_id)
        if not _pointer_matches_bundle(before.pointer, incumbent_bundle):
            raise BlueGreenRuntimeError("incumbent output differs from remote current pointer")
        decision = self._comparator.compare(
            candidate_bundle,
            before.pointer,
            observed_days=observed_days,
        )
        if decision.action not in {
            PromotionAction.SEMANTICALLY_EQUAL_PROMOTION,
            PromotionAction.PROTECTED_APPROVAL_REQUIRED,
        }:
            raise BlueGreenRuntimeError("candidate is not eligible for Blue-Green shadowing")

        # T0704 always persists the candidate as an append-only shadow.  It cannot mutate
        # current; a later protected promotion remains a separate authority.
        shadow_decision = self._comparator.shadow(
            candidate_bundle,
            before.pointer,
        )
        if shadow_decision.action is not PromotionAction.CANDIDATE_SHADOW_ONLY:
            raise BlueGreenRuntimeError("candidate shadow decision is not pointer-safe")
        candidate_plan = self._processed_planner.plan(
            candidate_bundle,
            shadow_decision,
            before.pointer,
            key_epoch=key_epoch,
            expected_pointer_revision=before.revision,
        )
        if candidate_plan.current_pointer is not None:
            raise BlueGreenRuntimeError("candidate shadow unexpectedly contains a current pointer")
        commit_result = self._operational_gate.execute(
            SensitiveOperation.PROCESSED_WRITE,
            partial(self._processed_commit.commit, candidate_plan),
            demand=git_capacity_demand(
                tuple(item.ciphertext for item in candidate_plan.immutable_objects)
                + (
                    (candidate_plan.current_pointer.ciphertext,)
                    if candidate_plan.current_pointer is not None
                    else ()
                )
            ),
        )
        if (
            commit_result.state is not ProcessedCommitState.CANDIDATE_COMMITTED_CURRENT_UNCHANGED
            or commit_result.current_pointer_updated
        ):
            raise BlueGreenRuntimeError("candidate shadow mutated the current pointer")
        candidate_proof = self._processed_recovery.verify(
            canonical,
            first_verification,
            raw_plan,
            candidate_bundle,
            candidate_plan,
        )
        expected_recovered = len(raw_plan.objects) + len(candidate_plan.immutable_objects)
        if candidate_proof.recovered_object_count != expected_recovered:
            raise BlueGreenRuntimeError("candidate remote recovery count differs")
        after = self._current_pointer_source.resolve(incumbent_bundle.source_id)
        if after != before:
            raise BlueGreenRuntimeError("current pointer changed during candidate shadow commit")

        incumbent_event = self._timeline_event(
            envelope,
            incumbent_outcome,
            canonical,
            m3_state=m3_state,
            independent_activity_evidence=independent_activity_evidence,
            market_session_expected=market_session_expected,
            sla_exceeded=sla_exceeded,
        )
        candidate_event = self._timeline_event(
            envelope,
            candidate_outcome,
            canonical,
            m3_state=m3_state,
            independent_activity_evidence=independent_activity_evidence,
            market_session_expected=market_session_expected,
            sla_exceeded=sla_exceeded,
        )
        difference_count = int(
            candidate_bundle.business_root != incumbent_bundle.business_root
            or candidate_event.canonical_bytes() != incumbent_event.canonical_bytes()
        )

        facts_by_source: dict[str, TimelineSnapshotFact] = {}
        if previous_snapshot_root is not None:
            recovered_previous = self._snapshot_recovery.recover_root(previous_snapshot_root)
            for fact in recovered_previous.facts:
                current = self._current_pointer_source.resolve(fact.event.source_id)
                if current.pointer != fact.current_pointer:
                    raise BlueGreenRuntimeError("prior Timeline fact is no longer current")
                facts_by_source[fact.event.source_id] = fact
        facts_by_source[incumbent_event.source_id] = TimelineSnapshotFact(
            before.pointer,
            incumbent_event,
        )
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
            raise BlueGreenRuntimeError("Timeline snapshot recovery count differs")
        for fact in snapshot_proof.facts:
            current = self._current_pointer_source.resolve(fact.event.source_id)
            if current.pointer != fact.current_pointer:
                raise BlueGreenRuntimeError(
                    "current Processed pointer changed before Timeline publish"
                )

        publish_result = self._operational_gate.execute(
            SensitiveOperation.TIMELINE_WRITE,
            partial(
                self._timeline_publisher.publish,
                tuple(fact.event for fact in snapshot_proof.facts),
                processed_snapshot_root=snapshot_proof.processed_snapshot_root,
                key_epoch=key_epoch,
                now_utc=observed_at_utc,
            ),
            demand=reserved_git_capacity_demand(
                MAXIMUM_TIMELINE_STATE_CIPHERTEXT_BYTES,
                mutation_count=MAXIMUM_TIMELINE_STATE_MUTATIONS_PER_PUBLISH,
                release_asset_bytes=MAXIMUM_TIMELINE_ASSET_CIPHERTEXT_BYTES,
            ),
        )
        ready = (
            decision.action is PromotionAction.SEMANTICALLY_EQUAL_PROMOTION
            and difference_count == 0
            and publish_result.state is TimelinePublishStateName.HEALTHY
            and publish_result.asset_count == 1
        )
        result = BlueGreenTimelineRunResult(
            phase=ReleasePhase.BLUE_GREEN,
            observed_days=observed_days,
            candidate_action=decision.action,
            candidate_reason_code=decision.reason_code,
            parser_comparisons=1,
            candidate_processed_recoveries=1,
            unresolved_comparison_differences=difference_count,
            current_pointer_mutations=0,
            timeline_snapshot_recoveries=1,
            timeline_publish_attempts=1,
            final_live_timeline_assets=publish_result.asset_count,
            timeline_action=publish_result.action,
            timeline_state=publish_result.state,
            ready_for_protected_promotion=ready,
        )
        return result, snapshot_proof

    def _profile_for(
        self,
        document_class: DocumentClass,
        parser_version: str,
    ) -> ParserProfile | None:
        matches = [
            profile
            for profile in self._parser_registry.profiles
            if profile.document_class is document_class and profile.parser_version == parser_version
        ]
        if len(matches) > 1:
            raise BlueGreenRuntimeError("multiple parser profiles match one version")
        return matches[0] if matches else None

    def _timeline_event(
        self,
        envelope: DocumentEnvelope,
        outcome: ParserOutcome,
        canonical: CanonicalRaw,
        *,
        m3_state: M3State,
        independent_activity_evidence: bool | None,
        market_session_expected: bool | None,
        sla_exceeded: bool | None,
    ) -> TimelineEvent:
        statement = outcome.statement
        field_lineage = statement.field_lineage if statement is not None else ()
        final_envelope = envelope.with_processing(
            outcome.state,
            outcome.reason_code,
            parser_name=outcome.parser_name,
            parser_version=outcome.parser_version,
            field_lineage=field_lineage,
        )
        expectation = self._expectation_policy.assess(
            observed=True,
            independent_activity_evidence=independent_activity_evidence,
            market_session_expected=market_session_expected,
            sla_exceeded=sla_exceeded,
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

    @staticmethod
    def _validate_recovered_raw(
        canonical: CanonicalRaw,
        verification: MessageVerification,
        raw_plan: RawCommitPlan,
        proof: MessageRecoveryProof,
        key_epoch: str,
    ) -> None:
        messages = [item for item in raw_plan.objects if item.role is RawObjectRole.MESSAGE]
        if (
            verification.phase is not VerificationPhase.PRE_RAW
            or verification.decision is not SenderDecision.VERIFIED
            or verification.verification_digest is None
            or verification.message_id != canonical.message_id
            or verification.internal_date_ms != canonical.internal_date_ms
            or len(messages) != 1
            or messages[0].plaintext_sha256 != canonical.plaintext_sha256
            or raw_plan.key_epoch != key_epoch
            or proof.recovery_scope not in {RecoveryScope.RAW_ONLY, RecoveryScope.RAW_AND_PROCESSED}
            or proof.message_id != canonical.message_id
            or proof.internal_date_ms != canonical.internal_date_ms
            or proof.source_id != raw_plan.opaque_message_id
            or proof.raw_plaintext_sha256 != canonical.plaintext_sha256
            or proof.verification_digest != verification.verification_digest
        ):
            raise BlueGreenRuntimeError("Blue-Green Raw recovery inputs are not bound")


def _pointer_matches_bundle(
    pointer: CurrentProcessedPointer,
    bundle: ProcessedBundle,
) -> bool:
    return (
        pointer.source_id == bundle.source_id
        and pointer.parser_name == bundle.parser_name
        and pointer.parser_version == bundle.parser_version
        and pointer.schema_version == bundle.schema_version
        and pointer.business_root == bundle.business_root
        and pointer.snapshot_root == bundle.snapshot_root
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


def _semver_key(value: str) -> tuple[int, int, int]:
    if _SEMVER.fullmatch(value) is None:
        raise BlueGreenRuntimeError("parser version is invalid")
    major, minor, patch = value.split(".")
    return (int(major), int(minor), int(patch))


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)
