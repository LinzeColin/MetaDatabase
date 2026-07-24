"""Explicit protected entrypoint for one Stage 7 M3 Budget-1 Canary.

Before reading any protected Secret the entrypoint binds a first-attempt owner dispatch to exact
``main``, validates the protected Beta PASS receipt, verifies the current Run Contract explicitly
authorizes T0703, and checks a same-tree gate digest.  A successful execution emits aggregate-only
evidence and never enables Timeline, Blue-Green, GA or scheduling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from .canary_runtime import M3CanaryRunResult
from .http_transport import StdlibHttpsTransport
from .protected_m3 import M3_SECRET_NAMES, ProtectedM3Bootstrap
from .protected_m3_diagnostics import (
    ProtectedM3AggregateFailureClass,
    ProtectedM3Diagnostics,
    ProtectedM3FailurePhase,
    public_failure_payload,
)
from .release_control import (
    GateStatus,
    ObservationProvenance,
    PhaseObservation,
    ReleasePhase,
    Stage7ReleaseGate,
)
from .secret_values import SecretText

CONTROL_REPOSITORY_ID = 1_300_525_906
CONTROL_OWNER_ID = 68_840_188
CONTROL_REF = "refs/heads/main"
CONTROL_WORKFLOW_REF = "LinzeColin/MetaDatabase/.github/workflows/moomooau-m3.yml@refs/heads/main"
PROTECTED_ENVIRONMENT = "moomooau-beta"
M3_CONFIRMATION = "M3_BUDGET_ONE"

_BETA_RECEIPT_PATH = Path("machine/stages/S7/reviews/t0702/execution-receipt.json")
_BETA_RECEIPT_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-beta-execution-receipt-v2.schema.json"
)
_RUN_CONTRACT_PATH = Path("machine/stages/S7/contracts/run_contract.json")
_M3_ATTEMPT_LEDGER_PATH = Path("machine/stages/S7/reviews/t0703/attempt-ledger.json")
_M3_ATTEMPT_LEDGER_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-m3-attempt-ledger-v1.schema.json"
)
_GATE_PATHS = (
    _BETA_RECEIPT_PATH,
    _BETA_RECEIPT_SCHEMA_PATH,
    _RUN_CONTRACT_PATH,
    _M3_ATTEMPT_LEDGER_PATH,
    _M3_ATTEMPT_LEDGER_SCHEMA_PATH,
    Path("machine/stages/S7/contracts/stage7_acceptance_contract.json"),
    Path("src/moomooau_archive/release_control.py"),
    Path("src/moomooau_archive/canary_runtime.py"),
    Path("src/moomooau_archive/document_parser.py"),
    Path("src/moomooau_archive/protected_m3.py"),
    Path("src/moomooau_archive/protected_m3_diagnostics.py"),
    Path("tests/tasks/test_t0703.py"),
)
_PRIOR_FAILED_ATTEMPTS = 4
_CUMULATIVE_DISPATCHES_AFTER_SUCCESS = 5
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]*$")


class ProtectedM3EntrypointError(RuntimeError):
    """A protected M3 execution prerequisite failed without exposing a protected value."""


class ExactM3EnvironmentSecretSource:
    """Read only the eight exact M3 Secret values injected into the execution step."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._environment = environment

    def read(self, name: str) -> SecretText:
        if name not in M3_SECRET_NAMES:
            raise ProtectedM3EntrypointError("protected M3 Secret name is not allowlisted")
        value = self._environment.get(name)
        if not isinstance(value, str) or not value:
            raise ProtectedM3EntrypointError("required protected M3 Secret is unavailable")
        return SecretText(value)


@dataclass(frozen=True, slots=True)
class ProtectedM3GitHubContext:
    """Exact non-secret provenance for one protected GitHub-hosted M3 execution."""

    repository_id: int
    owner_id: int
    actor_id: int
    run_id: int
    run_attempt: int
    head_sha: str
    ref: str
    workflow_ref: str
    runner_environment: str
    environment_name: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> ProtectedM3GitHubContext:
        if (
            environment.get("GITHUB_ACTIONS") != "true"
            or environment.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        ):
            raise ProtectedM3EntrypointError("protected M3 requires GitHub workflow_dispatch")
        context = cls(
            repository_id=_positive_environment_integer(environment, "GITHUB_REPOSITORY_ID"),
            owner_id=_positive_environment_integer(environment, "GITHUB_REPOSITORY_OWNER_ID"),
            actor_id=_positive_environment_integer(environment, "GITHUB_ACTOR_ID"),
            run_id=_positive_environment_integer(environment, "GITHUB_RUN_ID"),
            run_attempt=_positive_environment_integer(environment, "GITHUB_RUN_ATTEMPT"),
            head_sha=_environment_string(environment, "GITHUB_SHA"),
            ref=_environment_string(environment, "GITHUB_REF"),
            workflow_ref=_environment_string(environment, "GITHUB_WORKFLOW_REF"),
            runner_environment=_environment_string(environment, "RUNNER_ENVIRONMENT"),
            environment_name=_environment_string(
                environment,
                "MOOMOOAU_PROTECTED_ENVIRONMENT",
            ),
        )
        if (
            context.repository_id != CONTROL_REPOSITORY_ID
            or context.owner_id != CONTROL_OWNER_ID
            or context.actor_id != CONTROL_OWNER_ID
            or context.ref != CONTROL_REF
            or context.workflow_ref != CONTROL_WORKFLOW_REF
            or context.runner_environment != "github-hosted"
            or context.environment_name != PROTECTED_ENVIRONMENT
            or context.run_attempt != 1
            or _COMMIT.fullmatch(context.head_sha) is None
        ):
            raise ProtectedM3EntrypointError("protected M3 GitHub context is not allowed")
        return context


@dataclass(frozen=True, slots=True)
class ProtectedM3ExecutionEvidence:
    """Public-safe aggregate evidence for one successful protected M3 run."""

    context: ProtectedM3GitHubContext
    beta_receipt_sha256: str
    gate_sha256: str
    observation: PhaseObservation
    public_result: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        observation = self.observation
        return {
            "schema_version": "moomooau.protected-m3-execution.v1",
            "status": "PROTECTED_M3_CANARY_COMPLETED_NOT_FINAL",
            "control": {
                "repository_id": self.context.repository_id,
                "run_id": self.context.run_id,
                "run_attempt": self.context.run_attempt,
                "head_sha": self.context.head_sha,
                "ref": self.context.ref,
                "workflow_ref": self.context.workflow_ref,
                "runner_environment": self.context.runner_environment,
                "environment": self.context.environment_name,
                "beta_receipt_sha256": self.beta_receipt_sha256,
                "m3_gate_sha256": self.gate_sha256,
            },
            "phase_observation": {
                "phase": observation.phase.value,
                "provenance": observation.provenance.value,
                "started_at_utc": _format_utc(observation.started_at_utc),
                "ended_at_utc": _format_utc(observation.ended_at_utc),
                "observed_runs": observation.observed_runs,
                "processed_or_safe_deferred_present": observation.processed_messages >= 1,
                "source_mutation_budget": observation.mutation_budget_max,
                "source_mutation_confirmed": observation.source_mutations == 1,
                "remote_recovery_one_hundred_percent": (
                    observation.recovery_attempts >= 1
                    and observation.recovery_successes == observation.recovery_attempts
                ),
                "collateral_mutations": observation.collateral_mutations,
                "timeline_publish_attempts": observation.timeline_publish_attempts,
                "maximum_live_timeline_assets": observation.maximum_live_timeline_assets,
                "unresolved_failures": observation.unresolved_failures,
                "exact_mailbox_counts_disclosed": False,
            },
            "public_result": self.public_result,
            "boundaries": {
                "maximum_verified_candidates": 1,
                "maximum_source_mutations": 1,
                "timeline_enabled": False,
                "blue_green_enabled": False,
                "schedule_enabled": False,
            },
            "m3_gate_status": "PASS",
            "production_health_claimed": False,
            "final_acceptance_claimed": False,
        }


def beta_receipt_sha256(project_root: Path) -> str:
    """Return the digest of the exact committed T0702 protected PASS receipt."""

    root = _validated_project_root(project_root)
    receipt = root / _BETA_RECEIPT_PATH
    if not receipt.is_file() or receipt.is_symlink():
        raise ProtectedM3EntrypointError("protected Beta receipt is missing or unsafe")
    return hashlib.sha256(receipt.read_bytes()).hexdigest()


def m3_gate_sha256(project_root: Path) -> str:
    """Bind M3 authority, predecessor evidence, implementation and executable task oracle."""

    root = _validated_project_root(project_root)
    digest = hashlib.sha256()
    for relative in _GATE_PATHS:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ProtectedM3EntrypointError("protected M3 gate authority is missing or unsafe")
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def execution_contract(project_root: Path) -> dict[str, object]:
    """Return the non-executing M3 contract and current explicit authority state."""

    root = _validated_project_root(project_root)
    return {
        "schema_version": "moomooau.protected-m3-entrypoint-contract.v1",
        "mode": "CONTRACT_ONLY",
        "control_repository_id": CONTROL_REPOSITORY_ID,
        "control_owner_id": CONTROL_OWNER_ID,
        "required_actor_id": CONTROL_OWNER_ID,
        "required_ref": CONTROL_REF,
        "required_workflow_ref": CONTROL_WORKFLOW_REF,
        "protected_environment": PROTECTED_ENVIRONMENT,
        "required_runner_environment": "github-hosted",
        "required_run_attempt": 1,
        "required_event": "workflow_dispatch",
        "required_confirmation": M3_CONFIRMATION,
        "required_protected_input_count": len(M3_SECRET_NAMES),
        "protected_input_values_disclosed": False,
        "beta_receipt_path": _BETA_RECEIPT_PATH.as_posix(),
        "beta_receipt_sha256": beta_receipt_sha256(root),
        "prior_attempt_ledger_path": _M3_ATTEMPT_LEDGER_PATH.as_posix(),
        "prior_failed_attempts": _load_prior_attempt_count(root),
        "same_head_rerun_allowed": False,
        "m3_gate_paths": [path.as_posix() for path in _GATE_PATHS],
        "m3_gate_sha256": m3_gate_sha256(root),
        "m3_authorized": _m3_authorized(root),
        "feature_invariants": {
            "processing_enabled": True,
            "m3_enabled": True,
            "timeline_enabled": False,
            "mutation_budget_per_run": 1,
            "parser_current_version_required": True,
            "empty_protected_registries_force_safe_deferred": True,
        },
        "maximum_verified_candidates": 1,
        "maximum_source_mutations": 1,
        "maximum_timeline_mutations": 0,
        "fixed_calendar_wait_days": 0,
        "real_gmail_calls": 0,
        "private_repository_calls": 0,
        "protected_oracles_executed": 0,
        "production_health_claimed": False,
    }


def execute_protected(
    environment: Mapping[str, str],
    *,
    project_root: Path,
    expected_head_sha: str,
    supplied_beta_receipt_sha256: str,
    supplied_m3_gate_sha256: str,
    confirmation: str,
    bootstrap: ProtectedM3Bootstrap | None = None,
    clock: Callable[[], datetime] | None = None,
    diagnostics: ProtectedM3Diagnostics | None = None,
) -> ProtectedM3ExecutionEvidence:
    """Execute one M3 Canary only after every local non-secret gate passes."""

    active_diagnostics = diagnostics or ProtectedM3Diagnostics()
    active_diagnostics.enter(ProtectedM3FailurePhase.CONTEXT_GATE)
    context = ProtectedM3GitHubContext.from_environment(environment)
    if (
        confirmation != M3_CONFIRMATION
        or expected_head_sha != context.head_sha
        or _COMMIT.fullmatch(expected_head_sha) is None
        or _SHA256.fullmatch(supplied_beta_receipt_sha256) is None
        or _SHA256.fullmatch(supplied_m3_gate_sha256) is None
    ):
        raise ProtectedM3EntrypointError("protected M3 dispatch confirmation is invalid")
    expected_receipt = beta_receipt_sha256(project_root)
    expected_gate = m3_gate_sha256(project_root)
    if supplied_beta_receipt_sha256 != expected_receipt or supplied_m3_gate_sha256 != expected_gate:
        raise ProtectedM3EntrypointError("protected M3 same-tree binding differs")

    active_diagnostics.enter(ProtectedM3FailurePhase.BETA_BINDING)
    predecessors = _load_beta_predecessors(project_root)
    active_diagnostics.enter(ProtectedM3FailurePhase.PRIOR_ATTEMPT_BINDING)
    if _load_prior_attempt_count(project_root) != _PRIOR_FAILED_ATTEMPTS:
        raise ProtectedM3EntrypointError("protected M3 prior-attempt lineage is invalid")
    active_diagnostics.enter(ProtectedM3FailurePhase.RUN_CONTRACT)
    if not _m3_authorized(project_root):
        raise ProtectedM3EntrypointError("current Run Contract does not authorize M3")

    now = clock or (lambda: datetime.now(UTC))
    started_at = _utc_now(now)
    active_bootstrap = bootstrap
    if active_bootstrap is None:
        transport = StdlibHttpsTransport()
        active_bootstrap = ProtectedM3Bootstrap(
            ExactM3EnvironmentSecretSource(environment),
            oauth_transport=transport,
            gmail_transport=transport,
            github_transport=transport,
            clock=now,
            diagnostics=active_diagnostics,
        )
    with active_bootstrap.open(predecessor_observations=predecessors) as runtime:
        result = runtime.run()
    ended_at = _utc_now(now)
    active_diagnostics.enter(ProtectedM3FailurePhase.AGGREGATE_GATE)
    try:
        observation = _m3_observation(result, started_at, ended_at)
    except ProtectedM3EntrypointError:
        active_diagnostics.enter_aggregate_failure(_aggregate_failure_class(result))
        raise
    gate = Stage7ReleaseGate().evaluate_completed_phase(observation)
    if gate.status is not GateStatus.READY:
        raise ProtectedM3EntrypointError("protected M3 aggregate gate is blocked")
    return ProtectedM3ExecutionEvidence(
        context,
        expected_receipt,
        expected_gate,
        observation,
        result.to_public_dict(),
    )


def _load_beta_predecessors(project_root: Path) -> tuple[PhaseObservation, ...]:
    root = _validated_project_root(project_root)
    try:
        receipt = _load_object(root / _BETA_RECEIPT_PATH)
        schema = _load_object(root / _BETA_RECEIPT_SCHEMA_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtectedM3EntrypointError("protected Beta receipt is unreadable") from exc
    if list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(receipt)
    ):
        raise ProtectedM3EntrypointError("protected Beta receipt schema is invalid")

    control = _object_field(receipt, "control")
    jobs = _object_field(receipt, "jobs")
    alpha_job = _object_field(jobs, "alpha_gate")
    beta_job = _object_field(jobs, "beta_raw_only")
    public = _object_field(receipt, "public_result")
    post_run = _object_field(receipt, "post_run_state")
    scope = _object_field(receipt, "scope_decision")
    claims = _object_field(receipt, "claims")
    if (
        receipt.get("task_id") != "T0702"
        or receipt.get("stage_acceptance_id") != "S7AC-002"
        or control.get("workflow_event") != "workflow_dispatch"
        or control.get("workflow_ref") != CONTROL_REF
        or control.get("workflow_attempt") != 1
        or control.get("dispatches_for_head") != 1
        or control.get("reruns") != 0
        or control.get("workflow_head_sha") != control.get("merge_commit_sha")
        or alpha_job.get("status") != "PASS"
        or beta_job.get("status") != "PASS"
        or public.get("status") != "PROTECTED_BETA_RAW_ONLY_COMPLETED_NOT_FINAL"
        or public.get("beta_gate_status") != "PASS"
        or public.get("phase") != ReleasePhase.BETA_RAW_ONLY.value
        or public.get("provenance") != ObservationProvenance.PROTECTED_GITHUB_ACTIONS.value
        or public.get("recovered_bucket") != "ONE"
        or public.get("verified_within_configured_budget") is not True
        or public.get("raw_recovery_one_hundred_percent") is not True
        or any(
            public.get(key) != 0
            for key in (
                "source_mutations",
                "processed_writes",
                "timeline_mutations",
            )
        )
        or public.get("m3_executed") is not False
        or post_run.get("raw_remote_recovery") != "ONE_HUNDRED_PERCENT"
        or post_run.get("gmail_mutations") != 0
        or post_run.get("m3_runs") != 0
        or post_run.get("processed_writes") != 0
        or post_run.get("timeline_writes") != 0
        or scope.get("t0702_complete") is not True
        or scope.get("m3_predecessor_satisfied") is not True
        or claims.get("t0702_complete") is not True
        or claims.get("s7ac_002_passed") is not True
        or claims.get("production_health") is not False
        or claims.get("final_acceptance") is not False
    ):
        raise ProtectedM3EntrypointError("protected Beta receipt does not satisfy M3 predecessor")

    alpha_started = _parse_utc(alpha_job.get("started_at_utc"))
    alpha_ended = _parse_utc(alpha_job.get("ended_at_utc"))
    beta_started = _parse_utc(beta_job.get("started_at_utc"))
    beta_ended = _parse_utc(beta_job.get("ended_at_utc"))
    alpha = PhaseObservation(
        phase=ReleasePhase.ALPHA,
        provenance=ObservationProvenance.LOCAL_SYNTHETIC,
        started_at_utc=alpha_started,
        ended_at_utc=alpha_ended,
        observed_runs=1,
        scheduled_0430_runs=0,
        verified_messages=0,
        source_mutations=0,
        mutation_budget_max=0,
        recovery_attempts=0,
        recovery_successes=0,
        processed_messages=0,
        parser_blue_green_comparisons=0,
        timeline_publish_attempts=0,
        full_reconcile_runs=0,
        collateral_mutations=0,
        public_sensitive_findings=0,
        logical_duplicates=0,
        full_reconcile_difference=0,
        minimum_live_timeline_assets=0,
        maximum_live_timeline_assets=0,
        unresolved_failures=0,
    )
    beta = PhaseObservation(
        phase=ReleasePhase.BETA_RAW_ONLY,
        provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
        started_at_utc=beta_started,
        ended_at_utc=beta_ended,
        observed_runs=1,
        scheduled_0430_runs=0,
        verified_messages=1,
        source_mutations=0,
        mutation_budget_max=0,
        recovery_attempts=1,
        recovery_successes=1,
        processed_messages=0,
        parser_blue_green_comparisons=0,
        timeline_publish_attempts=0,
        full_reconcile_runs=0,
        collateral_mutations=0,
        public_sensitive_findings=0,
        logical_duplicates=0,
        full_reconcile_difference=0,
        minimum_live_timeline_assets=0,
        maximum_live_timeline_assets=0,
        unresolved_failures=0,
    )
    gate = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.M3_CANARY,
        (alpha, beta),
        beta_message_budget=1,
        parser_current_version="1.0.0",
    )
    if gate.status is not GateStatus.READY:
        raise ProtectedM3EntrypointError("protected Beta predecessor aggregate gate is blocked")
    return alpha, beta


def _load_prior_attempt_count(project_root: Path) -> int:
    root = _validated_project_root(project_root)
    try:
        ledger = _load_object(root / _M3_ATTEMPT_LEDGER_PATH)
        schema = _load_object(root / _M3_ATTEMPT_LEDGER_SCHEMA_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtectedM3EntrypointError("protected M3 attempt lineage is unreadable") from exc
    if list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(ledger)
    ):
        raise ProtectedM3EntrypointError("protected M3 attempt lineage schema is invalid")
    attempts = ledger.get("attempts")
    policy = ledger.get("completion_policy")
    claims = ledger.get("claims")
    if (
        ledger.get("task_id") != "T0703"
        or not isinstance(attempts, list)
        or len(attempts) != _PRIOR_FAILED_ATTEMPTS
        or not isinstance(policy, dict)
        or not isinstance(claims, dict)
    ):
        raise ProtectedM3EntrypointError("protected M3 attempt lineage is invalid")
    workflows: list[dict[str, Any]] = []
    for sequence, attempt in enumerate(attempts, start=1):
        if not isinstance(attempt, dict):
            raise ProtectedM3EntrypointError("protected M3 prior attempt is invalid")
        attempt_object = cast(dict[str, Any], attempt)
        delivery = _object_field(attempt_object, "delivery")
        workflow = _object_field(attempt_object, "workflow")
        jobs = _object_field(attempt_object, "jobs")
        failure = _object_field(attempt_object, "public_failure")
        effects = _object_field(attempt_object, "effects")
        if (
            attempt_object.get("sequence") != sequence
            or delivery.get("merge_commit_sha") != workflow.get("workflow_head_sha")
            or delivery.get("main_ci_runs_failed") != 0
            or workflow.get("event") != "workflow_dispatch"
            or workflow.get("run_attempt") != 1
            or workflow.get("reruns") != 0
            or _object_field(jobs, "authority_gate").get("status") != "PASS"
            or _object_field(jobs, "m3_budget_one").get("status") != "FAILED"
            or _object_field(jobs, "identity_plaintext_cleanup").get("status") != "PASS"
            or failure.get("status") != "BLOCKED"
            or failure.get("exact_root_cause_claimed") is not False
            or effects.get("private_repository_new_commits") != 0
            or effects.get("raw_ciphertext_creations") != "ZERO_OBSERVED"
            or effects.get("processed_writes") != "ZERO_OBSERVED"
            or effects.get("gmail_trash_messages_after_dispatch") != 0
            or effects.get("source_mutations") != 0
            or effects.get("timeline_writes") != 0
            or effects.get("scheduled_runs") != 0
        ):
            raise ProtectedM3EntrypointError("protected M3 prior attempt is not repair-eligible")
        workflows.append(workflow)
    if (
        len({item.get("workflow_head_sha") for item in workflows}) != _PRIOR_FAILED_ATTEMPTS
        or len({item.get("run_id") for item in workflows}) != _PRIOR_FAILED_ATTEMPTS
        or policy.get("same_head_rerun_allowed") is not False
        or policy.get("failed_head_redispatch_allowed") is not False
        or policy.get("repaired_exact_main_candidate_dispatch_allowed") is not True
        or policy.get("next_candidate_dispatch_limit") != 1
        or policy.get("t0704_authorized") is not False
        or policy.get("final_publication_authorized") is not False
        or claims.get("t0703_complete") is not False
        or claims.get("s7ac_003_passed") is not False
    ):
        raise ProtectedM3EntrypointError("protected M3 prior attempt is not repair-eligible")
    return _PRIOR_FAILED_ATTEMPTS


def _m3_authorized(project_root: Path) -> bool:
    root = _validated_project_root(project_root)
    try:
        contract = _load_object(root / _RUN_CONTRACT_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    authorization = contract.get("authorization")
    budget = contract.get("authorized_effect_budget")
    return bool(
        contract.get("stage_id") == "S7"
        and isinstance(authorization, dict)
        and isinstance(budget, dict)
        and authorization.get("purpose") == "T0703_PROTECTED_M3_REPAIR_ONLY"
        and authorization.get("m3_authorized") is True
        and authorization.get("final_publication_authorized") is False
        and authorization.get("prior_failed_attempts_exact") == _PRIOR_FAILED_ATTEMPTS
        and authorization.get("repair_candidate_dispatch_limit") == 1
        and budget.get("beta_message_budget") == 1
        and budget.get("m3_runs_maximum") == 1
        and budget.get("gmail_mutations_maximum") == 1
        and budget.get("m3_source_mutation_budget_per_run") == 1
        and budget.get("verified_full_raw_message_reads_maximum") == 1
        and budget.get("processed_writes_maximum") == 1
        and budget.get("protected_m3_dispatches_maximum") == 1
        and budget.get("protected_m3_reruns_maximum") == 0
        and budget.get("prior_protected_m3_dispatches_exact") == _PRIOR_FAILED_ATTEMPTS
        and budget.get("cumulative_protected_m3_dispatches_after_success_maximum")
        == _CUMULATIVE_DISPATCHES_AFTER_SUCCESS
        and budget.get("timeline_writes_maximum") == 0
        and budget.get("scheduled_runs_maximum") == 0
    )


def _m3_observation(
    result: M3CanaryRunResult,
    started_at: datetime,
    ended_at: datetime,
) -> PhaseObservation:
    processed = result.processed_complete + result.processed_safe_deferred
    if (
        result.raw_archived != 1
        or processed != 1
        or result.full_recovery_successes != 1
        or result.mutation_calls != 1
        or result.confirmed_trashed != 1
        or result.already_trashed != 0
        or result.failed_mutation_outcomes != 0
        or result.halted_fail_closed
        or result.maximum_live_timeline_assets != 0
    ):
        raise ProtectedM3EntrypointError("protected M3 result is not evidence-complete")
    return PhaseObservation(
        phase=ReleasePhase.M3_CANARY,
        provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
        started_at_utc=started_at,
        ended_at_utc=ended_at,
        observed_runs=1,
        scheduled_0430_runs=0,
        verified_messages=result.raw_archived,
        source_mutations=result.confirmed_trashed,
        mutation_budget_max=1,
        recovery_attempts=result.full_recovery_successes,
        recovery_successes=result.full_recovery_successes,
        processed_messages=processed,
        parser_blue_green_comparisons=0,
        timeline_publish_attempts=0,
        full_reconcile_runs=0,
        collateral_mutations=0,
        public_sensitive_findings=0,
        logical_duplicates=0,
        full_reconcile_difference=0,
        minimum_live_timeline_assets=0,
        maximum_live_timeline_assets=0,
        unresolved_failures=0,
    )


def _aggregate_failure_class(
    result: M3CanaryRunResult,
) -> ProtectedM3AggregateFailureClass:
    processed = result.processed_complete + result.processed_safe_deferred
    if result.verified_candidates == 0:
        return ProtectedM3AggregateFailureClass.NO_VERIFIED_CANDIDATE
    if result.raw_archived != 1:
        return ProtectedM3AggregateFailureClass.RAW_NOT_ARCHIVED
    if result.processing_blocked > 0:
        return ProtectedM3AggregateFailureClass.PROCESSING_BLOCKED
    if processed != 1 or result.full_recovery_successes != 1:
        return ProtectedM3AggregateFailureClass.PROCESSED_NOT_RECOVERED
    if result.already_trashed > 0:
        return ProtectedM3AggregateFailureClass.SOURCE_ALREADY_TRASHED
    if result.failed_mutation_outcomes > 0 or result.halted_fail_closed:
        return ProtectedM3AggregateFailureClass.MUTATION_FAILED
    if result.mutation_calls != 1 or result.confirmed_trashed != 1:
        return ProtectedM3AggregateFailureClass.MUTATION_NOT_CONFIRMED
    if result.maximum_live_timeline_assets != 0:
        return ProtectedM3AggregateFailureClass.TIMELINE_BOUNDARY_VIOLATION
    return ProtectedM3AggregateFailureClass.RESULT_INVARIANT_REJECTED


def _validated_project_root(project_root: Path) -> Path:
    try:
        root = project_root.resolve(strict=True)
    except OSError as exc:
        raise ProtectedM3EntrypointError("project root is unavailable") from exc
    if not root.is_dir() or not (root / "pyproject.toml").is_file():
        raise ProtectedM3EntrypointError("project root is invalid")
    return root


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProtectedM3EntrypointError("protected M3 authority must be an object")
    return cast(dict[str, Any], value)


def _object_field(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ProtectedM3EntrypointError("protected M3 authority object is invalid")
    return cast(dict[str, Any], item)


def _positive_environment_integer(environment: Mapping[str, str], name: str) -> int:
    value = environment.get(name)
    if not isinstance(value, str) or _POSITIVE_INTEGER.fullmatch(value) is None:
        raise ProtectedM3EntrypointError("protected M3 GitHub integer context is invalid")
    return int(value)


def _environment_string(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name)
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ProtectedM3EntrypointError("protected M3 GitHub string context is invalid")
    return value


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtectedM3EntrypointError("protected M3 predecessor timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ProtectedM3EntrypointError("protected M3 predecessor timestamp is invalid") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ProtectedM3EntrypointError("protected M3 predecessor timestamp must be UTC")
    return parsed.astimezone(UTC)


def _utc_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ProtectedM3EntrypointError("protected M3 clock must return UTC")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--contract-only", action="store_true")
    mode.add_argument("--execute-protected", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-head-sha")
    parser.add_argument("--beta-receipt-sha256")
    parser.add_argument("--m3-gate-sha256")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    execution_values = (
        args.expected_head_sha,
        args.beta_receipt_sha256,
        args.m3_gate_sha256,
        args.confirm,
    )
    if args.contract_only:
        if any(value is not None for value in execution_values):
            parser.error("protected execution arguments are invalid with --contract-only")
        print(
            json.dumps(execution_contract(args.project_root), sort_keys=True, separators=(",", ":"))
        )
        return 0
    if any(value is None for value in execution_values):
        parser.error("protected M3 execution requires exact gate inputs and confirmation")
    diagnostics = ProtectedM3Diagnostics()
    try:
        evidence = execute_protected(
            os.environ,
            project_root=args.project_root,
            expected_head_sha=args.expected_head_sha,
            supplied_beta_receipt_sha256=args.beta_receipt_sha256,
            supplied_m3_gate_sha256=args.m3_gate_sha256,
            confirmation=args.confirm,
            diagnostics=diagnostics,
        )
        print(json.dumps(evidence.to_dict(), sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print(
            json.dumps(
                public_failure_payload(diagnostics),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
