from __future__ import annotations

import json
from typing import cast

import pytest
import yaml
from stage7_support import (
    BlueGreenContext,
    blue_green_context,
    m3_canary_message,
    observations_through,
    phase_observation,
    protected_blue_green_context,
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
from moomooau_archive.protected_blue_green import (
    BLUE_GREEN_SECRET_NAMES,
    ProtectedBlueGreenBootstrapError,
)
from moomooau_archive.protected_blue_green_entrypoint import (
    BLUE_GREEN_CONFIRMATION,
    CONTROL_OWNER_ID,
    CONTROL_REF,
    CONTROL_REPOSITORY_ID,
    CONTROL_WORKFLOW_REF,
    PROTECTED_ENVIRONMENT,
    blue_green_gate_sha256,
    execute_protected,
    execution_contract,
    m3_receipt_sha256,
)
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


def test_t0704_blue_green_requires_complete_evidence_and_exactly_one_live_asset() -> None:
    through_m3 = observations_through(ReleasePhase.M3_CANARY)
    same_day = phase_observation(ReleasePhase.BLUE_GREEN, days=0, scheduled_runs=0)
    same_day_report = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.GA,
        through_m3 + (same_day,),
        beta_message_budget=1,
        parser_current_version="1.0.0",
        ga_mutation_budget_per_run=10,
        ga_capacity_authorized=True,
    )
    assert same_day_report.status is GateStatus.READY

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

        same_day, first_proof = _run_blue_green(context, observed_days=0)
        assert same_day.candidate_action is PromotionAction.SEMANTICALLY_EQUAL_PROMOTION
        assert same_day.ready_for_protected_promotion
        assert same_day.current_pointer_mutations == 0
        assert same_day.unresolved_comparison_differences == 0
        assert same_day.timeline_action is TimelinePublishAction.ASSET_REPAIRED
        assert same_day.timeline_state is TimelinePublishStateName.HEALTHY
        assert same_day.final_live_timeline_assets == 1
        public = same_day.to_public_dict()
        assert public["calendar_wait_required"] is False
        assert public["deterministic_evidence_complete"] is True
        assert context.processed_store.fetch_current(pointer_path) == incumbent
        assert first_proof.facts[0].current_pointer.parser_version == "1.0.0"

        repeated, repeated_proof = _run_blue_green(context, observed_days=0)
        assert repeated.candidate_action is PromotionAction.SEMANTICALLY_EQUAL_PROMOTION
        assert repeated.ready_for_protected_promotion
        assert repeated.current_pointer_mutations == 0
        assert repeated.timeline_action is TimelinePublishAction.NO_CHANGE
        assert repeated.final_live_timeline_assets == 1
        assert repeated_proof == first_proof
        assert context.processed_store.fetch_current(pointer_path) == incumbent
        assert sum(action == "upload" for action in context.timeline_remote.actions) == 1
        assert context.timeline_remote.maximum_observed_asset_count == 1
        assert len(context.timeline_remote.list_assets(context.timeline_remote.release_id)) == 1
        assert any("/2.0.0/" in path for path in context.processed_store.immutable_names())


def test_t0704_t0703_safe_deferred_current_supports_versioned_shadow_without_promotion() -> None:
    with blue_green_context(safe_deferred_pair=True) as context:
        pointer_path = (
            f"MooMooAU/State/processed-current/{context.raw_plan.opaque_message_id}.json.age"
        )
        incumbent = context.processed_store.fetch_current(pointer_path)
        assert incumbent is not None

        result, proof = _run_blue_green(context, observed_days=0)

        assert result.candidate_action is PromotionAction.SEMANTICALLY_EQUAL_PROMOTION
        assert result.unresolved_comparison_differences == 0
        assert result.current_pointer_mutations == 0
        assert result.final_live_timeline_assets == 1
        assert result.ready_for_protected_promotion
        assert proof.facts[0].current_pointer.parser_name == "protected-profile-parser"
        assert proof.facts[0].current_pointer.parser_version == "1.0.0"
        assert context.processed_store.fetch_current(pointer_path) == incumbent
        assert any("/2.0.0/" in path for path in context.processed_store.immutable_names())


def test_t0704_protected_cloud_composition_reuses_t0703_source_without_gmail_mutation() -> None:
    message = m3_canary_message("msg-stage7-protected-blue-green")
    with protected_blue_green_context(message) as context:
        pointer_paths = [
            path
            for path in context.github_transport.objects
            if path.startswith("MooMooAU/State/processed-current/")
        ]
        assert len(pointer_paths) == 1
        pointer_path = pointer_paths[0]
        pointer_before = context.github_transport.objects[pointer_path]
        pointer_revision_before = context.github_transport.revisions[pointer_path]
        trash_calls_before = len(context.gmail_transport.trashed_ids)

        with context.bootstrap.open(
            predecessor_observations=observations_through(ReleasePhase.M3_CANARY),
        ) as runtime:
            result = runtime.run()

        public = result.to_public_dict()
        assert public["status"] == "PROTECTED_BLUE_GREEN_COMPLETED_NOT_FINAL"
        assert public["processed_recoveries"] == 1
        assert public["parser_comparisons"] == 1
        assert public["timeline_publish_attempts"] == 1
        assert public["full_reconcile_runs"] == 1
        assert public["full_reconcile_difference"] == 0
        assert public["minimum_live_timeline_assets"] == 1
        assert public["maximum_live_timeline_assets"] == 1
        assert public["gmail_mutations"] == 0
        assert context.github_transport.objects[pointer_path] == pointer_before
        assert context.github_transport.revisions[pointer_path] == pointer_revision_before
        assert len(context.gmail_transport.trashed_ids) == trash_calls_before == 1
        assert len(context.github_transport.release_assets) == 1
        assert context.source.all_issued_destroyed


def test_t0704_stale_config_capacity_is_replaced_by_a_live_private_repo_observation() -> None:
    message = m3_canary_message("msg-stage7-protected-blue-green-live-capacity")
    with protected_blue_green_context(message, capacity_age_hours=72) as context:
        oauth_calls_before = len(context.oauth_transport.requests)
        with context.bootstrap.open(
            predecessor_observations=observations_through(ReleasePhase.M3_CANARY),
        ) as runtime:
            assert runtime._config.capacity_observed_at_utc == context.now
            snapshot = runtime._config.capacity.observed_snapshot
            assert snapshot is not None
            assert snapshot.git_repository_bytes > 0
            result = runtime.run()

        assert result.mechanism.ready_for_protected_promotion
        assert len(context.oauth_transport.requests) == oauth_calls_before + 1
        assert any(
            "/git/trees/main?recursive=1" in item.url for item in context.github_transport.requests
        )


def test_t0704_incomplete_live_capacity_tree_blocks_before_gmail_or_repository_write() -> None:
    message = m3_canary_message("msg-stage7-protected-blue-green-capacity-block")
    with protected_blue_green_context(message, capacity_age_hours=72) as context:
        context.github_transport.capacity_tree_truncated = True
        oauth_calls_before = len(context.oauth_transport.requests)
        gmail_calls_before = len(context.gmail_transport.inner.requests)
        writes_before = context.github_transport.write_calls
        objects_before = dict(context.github_transport.objects)

        with pytest.raises(ProtectedBlueGreenBootstrapError, match="incomplete or unbounded"):
            with context.bootstrap.open(
                predecessor_observations=observations_through(ReleasePhase.M3_CANARY),
            ):
                pass

        assert len(context.oauth_transport.requests) == oauth_calls_before
        assert len(context.gmail_transport.inner.requests) == gmail_calls_before
        assert context.github_transport.write_calls == writes_before
        assert context.github_transport.objects == objects_before
        assert context.github_transport.release_assets == {}
        assert context.source.all_issued_destroyed


def test_t0704_entrypoint_binds_exact_main_t0703_receipt_and_aggregate_only_result() -> None:
    message = m3_canary_message("msg-stage7-protected-blue-green-entrypoint")
    head_sha = "a" * 40
    environment = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY_ID": str(CONTROL_REPOSITORY_ID),
        "GITHUB_REPOSITORY_OWNER_ID": str(CONTROL_OWNER_ID),
        "GITHUB_ACTOR_ID": str(CONTROL_OWNER_ID),
        "GITHUB_RUN_ID": "7004001",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": head_sha,
        "GITHUB_REF": CONTROL_REF,
        "GITHUB_WORKFLOW_REF": CONTROL_WORKFLOW_REF,
        "RUNNER_ENVIRONMENT": "github-hosted",
        "MOOMOOAU_PROTECTED_ENVIRONMENT": PROTECTED_ENVIRONMENT,
    }
    contract = execution_contract(PROJECT_ROOT)
    assert contract["blue_green_authorized"] is True
    assert contract["required_protected_input_count"] == len(BLUE_GREEN_SECRET_NAMES) == 8
    assert contract["same_head_rerun_allowed"] is False
    assert contract["fixed_calendar_wait_days"] == 0
    with protected_blue_green_context(message) as context:
        evidence = execute_protected(
            environment,
            project_root=PROJECT_ROOT,
            expected_head_sha=head_sha,
            supplied_m3_receipt_sha256=m3_receipt_sha256(PROJECT_ROOT),
            supplied_blue_green_gate_sha256=blue_green_gate_sha256(PROJECT_ROOT),
            confirmation=BLUE_GREEN_CONFIRMATION,
            bootstrap=context.bootstrap,
            clock=lambda: context.now,
        ).to_dict()
    assert evidence["status"] == "PROTECTED_BLUE_GREEN_COMPLETED_NOT_FINAL"
    assert evidence["blue_green_gate_status"] == "PASS"
    assert evidence["production_health_claimed"] is False
    assert evidence["final_acceptance_claimed"] is False
    assert evidence["boundaries"] == {
        "maximum_verified_full_raw_reads": 1,
        "gmail_mutations": 0,
        "current_pointer_mutations": 0,
        "candidate_pointer_promotion": False,
        "maximum_live_timeline_assets": 1,
        "schedule_enabled": False,
        "ga_enabled": False,
    }
    serialized = json.dumps(evidence, sort_keys=True)
    assert "msg-stage7" not in serialized
    assert "synthetic-private-database" not in serialized


def test_t0704_protected_workflow_is_manual_exact_main_attempt_one_and_eight_secret() -> None:
    path = PROJECT_ROOT.parents[1] / ".github/workflows/moomooau-blue-green.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert workflow["on"].keys() == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "moomooau-blue-green-single-writer",
        "cancel-in-progress": "false",
    }
    authority = workflow["jobs"]["blue-green-authority-gate"]
    execution = workflow["jobs"]["blue-green-shadow-and-timeline"]
    assert "if" not in authority
    assert "if" not in execution
    assert execution["needs"] == "blue-green-authority-gate"
    assert execution["environment"] == PROTECTED_ENVIRONMENT
    execution_env = execution["steps"][-2]["env"]
    assert set(execution_env) == {
        *BLUE_GREEN_SECRET_NAMES,
        "EXPECTED_HEAD_SHA",
        "M3_RECEIPT_SHA256",
        "BLUE_GREEN_GATE_SHA256",
        "BLUE_GREEN_CONFIRMATION",
        "MOOMOOAU_PROTECTED_ENVIRONMENT",
    }
    assert "schedule:" not in text
    assert "messages.trash" not in text
    assert "moomooau-production" not in text
    assert text.count("actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5") == 2
    assert text.count("actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065") == 2


def test_t0704_timeline_snapshot_root_is_order_independent_retryable_and_recoverable() -> None:
    with blue_green_context() as context:
        _, one_fact_proof = _run_blue_green(context, observed_days=0)
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
        result, proof = _run_blue_green(context, observed_days=0)
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
            _run_blue_green(context, observed_days=0)
        assert context.processed_store.fetch_current(pointer_path) == incumbent
        assert context.processed_store.immutable_names() == immutable_before


def test_t0704_current_pointer_drift_blocks_before_live_timeline_publish() -> None:
    with blue_green_context(drift_on_runner_resolve=3) as context:
        with pytest.raises(BlueGreenRuntimeError, match="before Timeline publish"):
            _run_blue_green(context, observed_days=0)
        assert "upload" not in context.timeline_remote.actions
        assert context.timeline_remote.list_assets(context.timeline_remote.release_id) == ()


def test_t0704_predecessor_and_capacity_fail_before_remote_blue_green_effects() -> None:
    with blue_green_context() as context:
        fetches = context.processed_store.fetch_calls
        with pytest.raises(BlueGreenRuntimeError, match="predecessor"):
            _run_blue_green(
                context,
                observed_days=0,
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
            _run_blue_green(context, observed_days=0)
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
    provenance = json.loads(
        (PROJECT_ROOT / "taskpack/SOURCE_PROVENANCE.v1.0.16.json").read_text(encoding="utf-8")
    )
    expected_base = "4924fad17fc4666761df9ec7088608db18cc6605"
    assert provenance["schema_version"] == "moomooau.source-provenance.v16"
    assert provenance["candidate_snapshot"] == {
        "repository": "LinzeColin/MetaDatabase",
        "mainline_base_commit": expected_base,
        "acceptance_remediation_base_commit": expected_base,
        "shallow_checkout_fallback": "EXACT_PIN_ONLY",
    }
    acceptance_source = (PROJECT_ROOT / "machine/acceptance/evidence.py").read_text(
        encoding="utf-8"
    )
    assert (
        'PORTABLE_SOURCE_PROVENANCE_SCHEMA: Final = "moomooau.source-provenance.v16"'
        in acceptance_source
    )
    assert acceptance_source.count(f'"{expected_base}"') == 2
