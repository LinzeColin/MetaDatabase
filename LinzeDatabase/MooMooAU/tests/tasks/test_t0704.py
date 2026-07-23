from __future__ import annotations

import json
from typing import cast

import pytest
from stage7_support import (
    BlueGreenContext,
    blue_green_context,
    observations_through,
    phase_observation,
)
from validate_evidence import PROJECT_ROOT, validate_record

from moomooau_archive.blue_green_runtime import (
    BlueGreenRuntimeError,
    BlueGreenTimelineRunResult,
)
from moomooau_archive.capacity import CapacityAssessment, CapacityState
from moomooau_archive.github_guard import LIVE_ASSET_NAME
from moomooau_archive.m3 import M3State
from moomooau_archive.operation_gate import OperationGateError
from moomooau_archive.processed_commit import CurrentProcessedPointer, PromotionAction
from moomooau_archive.release_control import (
    GateStatus,
    PhaseObservation,
    ReleasePhase,
    Stage7ReleaseGate,
)
from moomooau_archive.timeline_event import TimelineEvent, TimelineEventError
from moomooau_archive.timeline_publish import (
    TimelinePublishAction,
    TimelinePublishError,
    TimelinePublishStateName,
)
from moomooau_archive.timeline_snapshot import (
    TimelineSnapshotError,
    TimelineSnapshotFact,
    TimelineSnapshotRecoveryProof,
)


def _run_blue_green(
    context: BlueGreenContext,
    *,
    observed_days: int,
    predecessors: tuple[PhaseObservation, ...] | None = None,
) -> tuple[BlueGreenTimelineRunResult, TimelineSnapshotRecoveryProof]:
    return cast(
        tuple[BlueGreenTimelineRunResult, TimelineSnapshotRecoveryProof],
        context.runner.run(
            context.canonical,
            context.first_verification,
            context.raw_plan,
            context.raw_proof,
            incumbent_parser_version="1.0.0",
            candidate_parser_version="2.0.0",
            key_epoch=context.key_epoch,
            imported_at_utc=context.imported_at_utc,
            observed_at_utc=context.observed_at_utc,
            observed_days=observed_days,
            m3_state=M3State.TRASHED,
            independent_activity_evidence=True,
            market_session_expected=True,
            sla_exceeded=False,
            predecessor_observations=(
                observations_through(ReleasePhase.M3_CANARY)
                if predecessors is None
                else predecessors
            ),
            beta_message_budget=1,
        ),
    )


def _clone_snapshot_fact(
    fact: TimelineSnapshotFact,
    *,
    source_id: str,
) -> TimelineSnapshotFact:
    pointer_value = json.loads(fact.current_pointer.to_bytes())
    pointer_value["source_id"] = source_id
    pointer_value["manifest_path"] = (
        pointer_value["manifest_path"].rsplit("/", 1)[0] + f"/{source_id}.json.age"
    )
    pointer = CurrentProcessedPointer.from_bytes(
        json.dumps(pointer_value, sort_keys=True, separators=(",", ":")).encode()
    )
    event_value = fact.event.to_private_dict()
    event_value["source_id"] = source_id
    event = TimelineEvent.from_bytes(
        json.dumps(event_value, sort_keys=True, separators=(",", ":")).encode()
    )
    return TimelineSnapshotFact(pointer, event)


def test_t0704_blue_green_requires_fourteen_days_and_exactly_one_live_asset() -> None:
    through_m3 = observations_through(ReleasePhase.M3_CANARY)
    short = phase_observation(ReleasePhase.BLUE_GREEN, days=13, scheduled_runs=13)
    blocked = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.GA,
        through_m3 + (short,),
        beta_message_budget=1,
        parser_current_version="1.0.0",
        ga_mutation_budget_per_run=10,
        ga_capacity_authorized=True,
    )
    assert blocked.status is GateStatus.BLOCKED
    assert "BLUE_GREEN_FOURTEEN_DAY_WINDOW_INCOMPLETE" in blocked.reasons

    two_assets = phase_observation(ReleasePhase.BLUE_GREEN, maximum_live_assets=2)
    blocked_assets = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.GA,
        through_m3 + (two_assets,),
        beta_message_budget=1,
        parser_current_version="1.0.0",
        ga_mutation_budget_per_run=10,
        ga_capacity_authorized=True,
    )
    assert "BLUE_GREEN_EXACTLY_ONE_LIVE_TIMELINE_FAILED" in blocked_assets.reasons

    no_real_work = phase_observation(
        ReleasePhase.BLUE_GREEN,
        verified_messages=0,
        source_mutations=0,
        recovery_attempts=0,
        recovery_successes=0,
        processed_messages=0,
        parser_comparisons=0,
        timeline_publish_attempts=0,
        full_reconcile_runs=0,
    )
    blocked_no_work = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.GA,
        through_m3 + (no_real_work,),
        beta_message_budget=1,
        parser_current_version="1.0.0",
        ga_mutation_budget_per_run=10,
        ga_capacity_authorized=True,
    )
    assert set(blocked_no_work.reasons) >= {
        "BLUE_GREEN_NO_PROCESSED_MESSAGE_OBSERVED",
        "BLUE_GREEN_NO_PARSER_COMPARISON_OBSERVED",
        "BLUE_GREEN_NO_TIMELINE_PUBLISH_OBSERVED",
        "BLUE_GREEN_FULL_RECONCILIATION_NOT_OBSERVED",
    }

    ready = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.GA,
        observations_through(ReleasePhase.BLUE_GREEN),
        beta_message_budget=1,
        parser_current_version="1.0.0",
        ga_mutation_budget_per_run=10,
        ga_capacity_authorized=True,
    )
    assert ready.status is GateStatus.READY


def test_t0704_same_recovered_raw_shadows_candidate_and_publishes_one_recovered_timeline() -> None:
    with blue_green_context() as context:
        pointer_path = (
            f"MooMooAU/State/processed-current/{context.raw_plan.opaque_message_id}.json.age"
        )
        incumbent = context.processed_store.fetch_current(pointer_path)
        assert incumbent is not None

        day_13, proof_13 = _run_blue_green(context, observed_days=13)
        assert day_13.candidate_action is PromotionAction.OBSERVATION_WINDOW_PENDING
        assert not day_13.ready_for_protected_promotion
        assert day_13.current_pointer_mutations == 0
        assert day_13.unresolved_comparison_differences == 0
        assert day_13.timeline_action is TimelinePublishAction.ASSET_REPAIRED
        assert day_13.timeline_state is TimelinePublishStateName.HEALTHY
        assert day_13.final_live_timeline_assets == 1
        assert context.processed_store.fetch_current(pointer_path) == incumbent
        assert proof_13.facts[0].current_pointer.parser_version == "1.0.0"

        day_14, proof_14 = _run_blue_green(context, observed_days=14)
        assert day_14.candidate_action is PromotionAction.SEMANTICALLY_EQUAL_PROMOTION
        assert day_14.ready_for_protected_promotion
        assert day_14.current_pointer_mutations == 0
        assert day_14.timeline_action is TimelinePublishAction.NO_CHANGE
        assert day_14.final_live_timeline_assets == 1
        assert proof_14 == proof_13
        assert context.processed_store.fetch_current(pointer_path) == incumbent
        assert sum(action == "upload" for action in context.timeline_remote.actions) == 1
        assert context.timeline_remote.maximum_observed_asset_count == 1
        assert len(context.timeline_remote.list_assets(context.timeline_remote.release_id)) == 1
        assert any("/2.0.0/" in path for path in context.processed_store.immutable_names())


def test_t0704_timeline_snapshot_root_is_order_independent_retryable_and_recoverable() -> None:
    with blue_green_context() as context:
        _, one_fact_proof = _run_blue_green(context, observed_days=13)
        first = one_fact_proof.facts[0]
        second_source = "f" * 64 if first.event.source_id != "f" * 64 else "e" * 64
        second = _clone_snapshot_fact(first, source_id=second_source)
        forward = context.snapshot_planner.plan(
            (first, second),
            key_epoch=context.key_epoch,
        )
        reverse = context.snapshot_planner.plan(
            (second, first),
            key_epoch=context.key_epoch,
        )
        assert forward.processed_snapshot_root == reverse.processed_snapshot_root
        assert [item.plaintext_sha256 for item in forward.objects] == [
            item.plaintext_sha256 for item in reverse.objects
        ]
        assert any(
            left.ciphertext != right.ciphertext
            for left, right in zip(forward.objects, reverse.objects, strict=True)
        )

        committed = context.snapshot_commit.commit(forward)
        assert committed.created_count >= 1
        recovered = context.snapshot_recovery.verify(forward)
        assert recovered.facts == forward.facts
        retried = context.snapshot_commit.commit(reverse)
        assert retried.created_count == 0
        assert retried.existing_count == retried.object_count
        assert context.snapshot_recovery.verify(reverse) == recovered

        noncanonical = json.dumps(first.event.to_private_dict(), indent=2).encode()
        with pytest.raises(TimelineEventError, match="canonical"):
            TimelineEvent.from_bytes(noncanonical)
        context.processed_store.corrupt_next_immutable_path = forward.objects[-1].relative_path
        with pytest.raises(TimelineSnapshotError, match="ciphertext is unavailable"):
            context.snapshot_recovery.recover_root(forward.processed_snapshot_root)


def test_t0704_business_change_requires_protected_approval_without_pointer_promotion() -> None:
    with blue_green_context(candidate_business_change=True) as context:
        pointer_path = (
            f"MooMooAU/State/processed-current/{context.raw_plan.opaque_message_id}.json.age"
        )
        incumbent = context.processed_store.fetch_current(pointer_path)
        assert incumbent is not None
        result, proof = _run_blue_green(context, observed_days=14)
        assert result.candidate_action is PromotionAction.PROTECTED_APPROVAL_REQUIRED
        assert result.unresolved_comparison_differences == 1
        assert not result.ready_for_protected_promotion
        assert result.current_pointer_mutations == 0
        assert result.timeline_state is TimelinePublishStateName.HEALTHY
        assert result.final_live_timeline_assets == 1
        assert proof.facts[0].current_pointer.parser_version == "1.0.0"
        assert context.processed_store.fetch_current(pointer_path) == incumbent


def test_t0704_live_asset_without_recoverable_snapshot_head_blocks_before_candidate_write() -> None:
    with blue_green_context() as context:
        pointer_path = (
            f"MooMooAU/State/processed-current/{context.raw_plan.opaque_message_id}.json.age"
        )
        incumbent = context.processed_store.fetch_current(pointer_path)
        immutable_before = context.processed_store.immutable_names()
        context.timeline_remote.inject_asset_for_test(
            LIVE_ASSET_NAME,
            context.processed_store.ciphertexts()[0],
        )
        with pytest.raises(TimelinePublishError, match="without a recoverable private"):
            _run_blue_green(context, observed_days=13)
        assert context.processed_store.fetch_current(pointer_path) == incumbent
        assert context.processed_store.immutable_names() == immutable_before


def test_t0704_current_pointer_drift_blocks_before_live_timeline_publish() -> None:
    with blue_green_context(drift_on_runner_resolve=3) as context:
        with pytest.raises(BlueGreenRuntimeError, match="before Timeline publish"):
            _run_blue_green(context, observed_days=13)
        assert "upload" not in context.timeline_remote.actions
        assert context.timeline_remote.list_assets(context.timeline_remote.release_id) == ()


def test_t0704_predecessor_and_capacity_fail_before_remote_blue_green_effects() -> None:
    with blue_green_context() as context:
        fetches = context.processed_store.fetch_calls
        with pytest.raises(BlueGreenRuntimeError, match="predecessor"):
            _run_blue_green(
                context,
                observed_days=13,
                predecessors=observations_through(ReleasePhase.BETA_RAW_ONLY),
            )
        assert context.processed_store.fetch_calls == fetches
        assert context.timeline_remote.actions == []

    red = CapacityAssessment(
        CapacityState.RED,
        False,
        False,
        ("SYNTHETIC_RED_CAPACITY",),
    )
    with blue_green_context(capacity=red) as context:
        fetches = context.processed_store.fetch_calls
        with pytest.raises(OperationGateError, match="PRODUCTION_RUN"):
            _run_blue_green(context, observed_days=13)
        assert context.processed_store.fetch_calls == fetches
        assert context.timeline_remote.actions == []


def test_t0704_stage_aware_evidence_validator_preserves_blocked_truth() -> None:
    path = PROJECT_ROOT / "evidence/tasks/T0704.json"
    assert validate_record(path) == []
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["record_status"] == "BLOCKED"
    assert all(item["status"] == "NOT_RUN" for item in record["production_oracles"])
    assert all(
        item["status"] in {"PARTIAL", "NOT_RUN"} for item in record["linked_final_acceptance"]
    )
