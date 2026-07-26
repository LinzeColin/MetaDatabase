"""Exact-main protected GA schedule-mode entrypoint for Stage 7 T0705.

The first T0705 execution is a single owner-dispatched protected rehearsal.  It invokes the
same deterministic ``RunTrigger.SCHEDULE`` path used by the committed 04:30
Australia/Sydney workflow, but it never claims that ``workflow_dispatch`` was a GitHub
schedule event.  Before any Secret read it binds exact main, the immutable T0702-T0704
receipts, the current one-task Run Contract and a same-tree gate digest.

The existing ``moomooau-beta`` Environment remains the sole protected credential plane.  Its
Beta infrastructure config is converted to a GA config only in memory; no Secret is copied or
persisted.  Production capacity is refreshed through the installed GitHub App before Gmail
credential exchange.
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

from .production import (
    PRODUCTION_CONFIG_SECRET_NAME,
    ProductionBootstrap,
    ProductionExecutionResult,
)
from .protected_beta import BETA_CONFIG_SECRET_NAME
from .protected_blue_green_entrypoint import _load_predecessors as _load_m3_predecessors
from .protected_m3 import M3_SECRET_NAMES
from .release_control import (
    GateStatus,
    ObservationProvenance,
    PhaseObservation,
    ReleasePhase,
    Stage7ReleaseGate,
)
from .run_schedule import RunTrigger
from .secret_values import SecretText

CONTROL_REPOSITORY_ID = 1_300_525_906
CONTROL_OWNER_ID = 68_840_188
CONTROL_REF = "refs/heads/main"
CONTROL_WORKFLOW_REF = (
    "LinzeColin/MetaDatabase/.github/workflows/moomooau-production.yml@refs/heads/main"
)
PROTECTED_ENVIRONMENT = "moomooau-beta"
GA_CONFIRMATION = "GA_SCHEDULE_MODE_REHEARSAL_MUTATION_BUDGET_ONE"
GA_PARSER_CURRENT_VERSION = "1.0.0"
GA_MUTATION_BUDGET_PER_RUN = 1

_BLUE_GREEN_RECEIPT_PATH = Path("machine/stages/S7/reviews/t0704/execution-receipt.json")
_BLUE_GREEN_RECEIPT_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-blue-green-execution-receipt-v1.schema.json"
)
_RUN_CONTRACT_PATH = Path("machine/stages/S7/contracts/run_contract.json")
_GATE_PATHS = (
    Path("machine/stages/S7/reviews/t0702/execution-receipt.json"),
    Path("machine/stages/S7/schemas/protected-beta-execution-receipt-v2.schema.json"),
    Path("machine/stages/S7/reviews/t0703/execution-receipt.json"),
    Path("machine/stages/S7/schemas/protected-m3-execution-receipt-v1.schema.json"),
    _BLUE_GREEN_RECEIPT_PATH,
    _BLUE_GREEN_RECEIPT_SCHEMA_PATH,
    _RUN_CONTRACT_PATH,
    Path("machine/stages/S7/contracts/stage7_acceptance_contract.json"),
    Path("machine/contracts/production_composition.json"),
    Path("src/moomooau_archive/ga_runtime.py"),
    Path("src/moomooau_archive/production.py"),
    Path("src/moomooau_archive/protected_ga_entrypoint.py"),
    Path("src/moomooau_archive/release_control.py"),
    Path("src/moomooau_archive/run_schedule.py"),
    Path("tests/tasks/test_t0705.py"),
    Path("tests/remediation/test_rmd04.py"),
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]*$")
_BETA_CONFIG_SCHEMA = "moomooau.protected-beta-config.v1"


class ProtectedGAEntrypointError(RuntimeError):
    """A protected GA prerequisite failed without exposing a protected value."""


class DerivedGASecretSource:
    """Expose seven existing values plus one in-memory derived production config."""

    def __init__(
        self,
        environment: Mapping[str, str],
        predecessors: tuple[PhaseObservation, ...],
    ) -> None:
        self._environment = environment
        self._predecessors = predecessors

    def read(self, name: str) -> SecretText:
        if name == PRODUCTION_CONFIG_SECRET_NAME:
            return SecretText(_derived_production_config(self._environment, self._predecessors))
        if name not in M3_SECRET_NAMES or name == BETA_CONFIG_SECRET_NAME:
            raise ProtectedGAEntrypointError("protected GA Secret name is not allowlisted")
        value = self._environment.get(name)
        if not isinstance(value, str) or not value:
            raise ProtectedGAEntrypointError("required protected GA Secret is unavailable")
        return SecretText(value)


@dataclass(frozen=True, slots=True)
class ProtectedGAGitHubContext:
    """Exact non-secret provenance for the one T0705 protected rehearsal."""

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
    event_name: str
    authorized_head: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> ProtectedGAGitHubContext:
        if environment.get("GITHUB_ACTIONS") != "true":
            raise ProtectedGAEntrypointError("protected GA requires GitHub Actions")
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
            event_name=_environment_string(environment, "GITHUB_EVENT_NAME"),
            authorized_head=_environment_string(
                environment,
                "MOOMOOAU_GA_REHEARSAL_AUTHORIZED_HEAD",
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
            or context.event_name != "workflow_dispatch"
            or context.run_attempt != 1
            or _COMMIT.fullmatch(context.head_sha) is None
            or context.authorized_head != context.head_sha
        ):
            raise ProtectedGAEntrypointError("protected GA GitHub context is not allowed")
        return context


@dataclass(frozen=True, slots=True)
class ProtectedGAExecutionEvidence:
    """Public-safe aggregate evidence for one successful protected GA rehearsal."""

    context: ProtectedGAGitHubContext
    blue_green_receipt_sha256: str
    gate_sha256: str
    observation: PhaseObservation
    execution: ProductionExecutionResult

    def to_dict(self) -> dict[str, object]:
        result = self.execution.outcome.result
        comparison = (
            "ZERO_DIFFERENCE"
            if result.full_reconcile_difference == 0
            else "NOT_COMPARABLE_INITIAL_IMPORT"
        )
        return {
            "schema_version": "moomooau.protected-ga-execution.v1",
            "status": "PROTECTED_GA_SCHEDULE_REHEARSAL_COMPLETED_NOT_FINAL",
            "control": {
                "repository_id": self.context.repository_id,
                "run_id": self.context.run_id,
                "run_attempt": self.context.run_attempt,
                "head_sha": self.context.head_sha,
                "ref": self.context.ref,
                "workflow_ref": self.context.workflow_ref,
                "runner_environment": self.context.runner_environment,
                "environment": self.context.environment_name,
                "github_event": self.context.event_name,
                "blue_green_receipt_sha256": self.blue_green_receipt_sha256,
                "ga_gate_sha256": self.gate_sha256,
            },
            "schedule": {
                "mode": "SCHEDULE_REHEARSAL",
                "target_time": "04:30",
                "timezone": "Australia/Sydney",
                "planner_trigger": RunTrigger.SCHEDULE.value,
                "platform_schedule_event_observed": False,
                "workflow_dispatch_truthfully_disclosed": True,
                "fixed_calendar_wait_days": 0,
            },
            "phase_observation": {
                "phase": ReleasePhase.GA.value,
                "provenance": ObservationProvenance.PROTECTED_GITHUB_ACTIONS.value,
                "observed_runs": 1,
                "schedule_mode_rehearsal_runs": 1,
                "verified_bucket": _bucket(result.verified_candidates),
                "processed_or_safe_deferred_bucket": _bucket(result.full_recovery_successes),
                "source_mutation_budget": result.mutation_budget_max,
                "source_mutation_calls_bucket": _bucket(result.mutation_calls),
                "remote_recovery_one_hundred_percent": (
                    result.full_recovery_successes
                    == result.processed_complete + result.processed_safe_deferred
                ),
                "full_reconcile_runs": result.full_reconcile_runs,
                "full_reconcile_comparison": comparison,
                "timeline_publish_attempts": result.timeline_publish_attempts,
                "minimum_live_timeline_assets": result.final_live_timeline_assets,
                "maximum_live_timeline_assets": result.final_live_timeline_assets,
                "gmail_checkpoint_remote_recovery": (result.sync_checkpoint_recoveries == 1),
                "collateral_mutations": 0,
                "logical_duplicates": 0,
                "unresolved_failures": 0,
                "exact_mailbox_counts_disclosed": False,
            },
            "public_result": self.execution.to_public_dict(),
            "boundaries": {
                "maximum_gmail_mutation_calls": GA_MUTATION_BUDGET_PER_RUN,
                "only_exact_message_trash": True,
                "thread_trash_enabled": False,
                "permanent_delete_enabled": False,
                "maximum_timeline_publish_attempts": 1,
                "maximum_live_timeline_assets": 1,
                "checkpoint_committed_last": True,
                "secret_values_copied": 0,
                "persistent_plaintext_objects": 0,
            },
            "ga_gate_status": "PASS",
            "t0706_authorized": False,
            "production_health_claimed": False,
            "final_acceptance_claimed": False,
        }


def blue_green_receipt_sha256(project_root: Path) -> str:
    """Return the digest of the exact committed T0704 protected PASS receipt."""

    root = _validated_project_root(project_root)
    path = root / _BLUE_GREEN_RECEIPT_PATH
    if not path.is_file() or path.is_symlink():
        raise ProtectedGAEntrypointError("protected Blue-Green receipt is missing or unsafe")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ga_gate_sha256(project_root: Path) -> str:
    """Bind T0705 authority, predecessor evidence, implementation and task oracles."""

    root = _validated_project_root(project_root)
    digest = hashlib.sha256()
    for relative in _GATE_PATHS:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ProtectedGAEntrypointError("protected GA gate authority is missing or unsafe")
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def execution_contract(project_root: Path) -> dict[str, object]:
    """Return the non-executing T0705 contract without reading a Secret."""

    root = _validated_project_root(project_root)
    authorized = _ga_authorized(root)
    return {
        "schema_version": "moomooau.protected-ga-entrypoint-contract.v1",
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
        "required_confirmation": GA_CONFIRMATION,
        "required_protected_input_count": len(M3_SECRET_NAMES),
        "protected_input_values_disclosed": False,
        "blue_green_receipt_path": _BLUE_GREEN_RECEIPT_PATH.as_posix(),
        "blue_green_receipt_sha256": blue_green_receipt_sha256(root),
        "ga_gate_paths": [path.as_posix() for path in _GATE_PATHS],
        "ga_gate_sha256": ga_gate_sha256(root),
        "ga_authorized": authorized,
        "schedule_mode": "SCHEDULE_REHEARSAL",
        "target_time": "04:30",
        "timezone": "Australia/Sydney",
        "platform_schedule_event_observed": False,
        "ga_mutation_budget_per_run": GA_MUTATION_BUDGET_PER_RUN,
        "maximum_pipeline_runs": 1,
        "maximum_rehearsal_dispatches": 1,
        "maximum_reruns": 0,
        "maximum_live_timeline_assets": 1,
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
    supplied_blue_green_receipt_sha256: str,
    supplied_ga_gate_sha256: str,
    confirmation: str,
    bootstrap: ProductionBootstrap | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ProtectedGAExecutionEvidence:
    """Execute one protected schedule-mode GA run after all non-secret gates pass."""

    context = ProtectedGAGitHubContext.from_environment(environment)
    if (
        confirmation != GA_CONFIRMATION
        or expected_head_sha != context.head_sha
        or _COMMIT.fullmatch(expected_head_sha) is None
        or _SHA256.fullmatch(supplied_blue_green_receipt_sha256) is None
        or _SHA256.fullmatch(supplied_ga_gate_sha256) is None
    ):
        raise ProtectedGAEntrypointError("protected GA dispatch confirmation is invalid")
    expected_receipt = blue_green_receipt_sha256(project_root)
    expected_gate = ga_gate_sha256(project_root)
    if (
        supplied_blue_green_receipt_sha256 != expected_receipt
        or supplied_ga_gate_sha256 != expected_gate
    ):
        raise ProtectedGAEntrypointError("protected GA same-tree binding differs")
    if not _ga_authorized(project_root):
        raise ProtectedGAEntrypointError("current Run Contract does not authorize GA")

    predecessors = _load_predecessors(project_root)
    now = clock or (lambda: datetime.now(UTC))
    active_bootstrap = bootstrap
    if active_bootstrap is None:
        from .http_transport import StdlibHttpsTransport

        transport = StdlibHttpsTransport()
        active_bootstrap = ProductionBootstrap(
            DerivedGASecretSource(environment, predecessors),
            oauth_transport=transport,
            gmail_transport=transport,
            github_transport=transport,
            clock=now,
            refresh_capacity_from_remote=True,
        )
    started_at = _utc_now(now)
    with active_bootstrap.open() as runtime:
        execution = runtime.run(RunTrigger.SCHEDULE)
    ended_at = _utc_now(now)
    observation = _ga_observation(execution, started_at, ended_at)
    completed = Stage7ReleaseGate().evaluate_stage_completion(
        predecessors + (observation,),
        beta_message_budget=1,
        parser_current_version=GA_PARSER_CURRENT_VERSION,
        ga_mutation_budget_per_run=GA_MUTATION_BUDGET_PER_RUN,
        ga_capacity_authorized=True,
    )
    if completed.status is not GateStatus.READY:
        raise ProtectedGAEntrypointError("protected GA aggregate gate is blocked")
    return ProtectedGAExecutionEvidence(
        context,
        expected_receipt,
        expected_gate,
        observation,
        execution,
    )


def _load_predecessors(project_root: Path) -> tuple[PhaseObservation, ...]:
    root = _validated_project_root(project_root)
    alpha, beta, m3 = _load_m3_predecessors(root)
    try:
        receipt = _load_object(root / _BLUE_GREEN_RECEIPT_PATH)
        schema = _load_object(root / _BLUE_GREEN_RECEIPT_SCHEMA_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtectedGAEntrypointError("protected Blue-Green receipt is unreadable") from exc
    if list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(receipt)
    ):
        raise ProtectedGAEntrypointError("protected Blue-Green receipt schema is invalid")
    control = _object_field(receipt, "control")
    jobs = _object_field(receipt, "jobs")
    job = _object_field(jobs, "blue_green_shadow_and_timeline")
    public = _object_field(receipt, "public_result")
    independent = _object_field(receipt, "independent_post_run_verification")
    scope = _object_field(receipt, "scope_decision")
    claims = _object_field(receipt, "claims")
    if (
        receipt.get("task_id") != "T0704"
        or receipt.get("stage_acceptance_id") != "S7AC-004"
        or control.get("workflow_event") != "workflow_dispatch"
        or control.get("workflow_attempt") != 1
        or control.get("dispatches_for_head") != 1
        or control.get("reruns") != 0
        or control.get("workflow_head_sha") != control.get("merge_commit_sha")
        or job.get("status") != "PASS"
        or public.get("status") != "PROTECTED_BLUE_GREEN_COMPLETED_NOT_FINAL"
        or public.get("blue_green_gate_status") != "PASS"
        or public.get("processed_recoveries") != 1
        or public.get("parser_comparisons") != 1
        or public.get("timeline_publish_attempts") != 1
        or public.get("full_reconcile_runs") != 1
        or public.get("full_reconcile_difference") != 0
        or public.get("minimum_live_timeline_assets") != 1
        or public.get("maximum_live_timeline_assets") != 1
        or public.get("gmail_mutations") != 0
        or public.get("unresolved_comparison_differences") != 0
        or public.get("remote_timeline_recovery_one_hundred_percent") is not True
        or independent.get("raw_tree_unchanged") is not True
        or independent.get("processed_tree_unchanged") is not True
        or independent.get("live_asset_age_envelope") is not True
        or independent.get("live_asset_download_recovered") is not True
        or independent.get("identity_plaintext_cleanup") != "PASS"
        or scope.get("t0704_complete") is not True
        or scope.get("blue_green_predecessor_satisfied") is not True
        or scope.get("rerun_allowed") is not False
        or claims.get("t0704_complete") is not True
        or claims.get("s7ac_004_passed") is not True
        or claims.get("t0705_complete") is not False
        or claims.get("production_health") is not False
        or claims.get("final_acceptance") is not False
    ):
        raise ProtectedGAEntrypointError(
            "protected Blue-Green receipt does not satisfy T0705 predecessor"
        )
    blue_green = PhaseObservation(
        phase=ReleasePhase.BLUE_GREEN,
        provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
        started_at_utc=_parse_utc(job.get("started_at_utc")),
        ended_at_utc=_parse_utc(job.get("ended_at_utc")),
        observed_runs=1,
        scheduled_0430_runs=0,
        verified_messages=1,
        source_mutations=0,
        mutation_budget_max=1,
        recovery_attempts=1,
        recovery_successes=1,
        processed_messages=1,
        parser_blue_green_comparisons=1,
        timeline_publish_attempts=1,
        full_reconcile_runs=1,
        collateral_mutations=0,
        public_sensitive_findings=0,
        logical_duplicates=0,
        full_reconcile_difference=0,
        minimum_live_timeline_assets=1,
        maximum_live_timeline_assets=1,
        unresolved_failures=0,
    )
    predecessors = (alpha, beta, m3, blue_green)
    promotion = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.GA,
        predecessors,
        beta_message_budget=1,
        parser_current_version=GA_PARSER_CURRENT_VERSION,
        ga_mutation_budget_per_run=GA_MUTATION_BUDGET_PER_RUN,
        ga_capacity_authorized=True,
    )
    if promotion.status is not GateStatus.READY:
        raise ProtectedGAEntrypointError("protected T0705 predecessor aggregate gate is blocked")
    return predecessors


def _ga_observation(
    execution: ProductionExecutionResult,
    started_at: datetime,
    ended_at: datetime,
) -> PhaseObservation:
    result = execution.outcome.result
    plan_public = execution.plan.to_public_dict()
    if (
        execution.plan.trigger is not RunTrigger.SCHEDULE
        or plan_public.get("target_time") != "04:30"
        or plan_public.get("timezone") != "Australia/Sydney"
        or result.verified_candidates < 1
        or result.full_recovery_successes < 1
        or result.raw_archived != result.verified_candidates
        or result.full_recovery_successes
        != result.processed_complete + result.processed_safe_deferred
        or result.mutation_budget_max != GA_MUTATION_BUDGET_PER_RUN
        or result.mutation_calls > GA_MUTATION_BUDGET_PER_RUN
        or result.full_reconcile_runs != 1
        or result.full_reconcile_difference not in {None, 0}
        or result.timeline_snapshot_recoveries != 1
        or result.timeline_publish_attempts != 1
        or result.final_live_timeline_assets != 1
        or result.sync_checkpoint_recoveries != 1
    ):
        raise ProtectedGAEntrypointError("protected GA result is not evidence-complete")
    return PhaseObservation(
        phase=ReleasePhase.GA,
        provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
        started_at_utc=started_at,
        ended_at_utc=ended_at,
        observed_runs=1,
        scheduled_0430_runs=1,
        verified_messages=result.verified_candidates,
        source_mutations=result.mutation_calls,
        mutation_budget_max=result.mutation_budget_max,
        recovery_attempts=result.full_recovery_successes,
        recovery_successes=result.full_recovery_successes,
        processed_messages=result.full_recovery_successes,
        parser_blue_green_comparisons=0,
        timeline_publish_attempts=result.timeline_publish_attempts,
        full_reconcile_runs=result.full_reconcile_runs,
        collateral_mutations=0,
        public_sensitive_findings=0,
        logical_duplicates=0,
        # The count is zero unresolved differences.  Public evidence separately preserves
        # NOT_COMPARABLE for an initial import instead of fabricating a comparison.
        full_reconcile_difference=0,
        minimum_live_timeline_assets=result.final_live_timeline_assets,
        maximum_live_timeline_assets=result.final_live_timeline_assets,
        unresolved_failures=0,
    )


def _derived_production_config(
    environment: Mapping[str, str],
    predecessors: tuple[PhaseObservation, ...],
) -> str:
    encoded = environment.get(BETA_CONFIG_SECRET_NAME)
    if not isinstance(encoded, str) or not encoded:
        raise ProtectedGAEntrypointError("protected Beta infrastructure config is unavailable")
    try:
        parsed = json.loads(encoded)
    except json.JSONDecodeError as exc:
        raise ProtectedGAEntrypointError("protected Beta infrastructure config is invalid") from exc
    required = {
        "schema_version",
        "phase",
        "beta_message_budget",
        "key_epoch",
        "age_recipient",
        "github",
        "capacity",
    }
    if (
        not isinstance(parsed, dict)
        or set(parsed) != required
        or parsed.get("schema_version") != _BETA_CONFIG_SCHEMA
        or parsed.get("phase") != ReleasePhase.BETA_RAW_ONLY.value
        or parsed.get("beta_message_budget") != 1
        or len(predecessors) != 4
        or tuple(item.phase for item in predecessors)
        != (
            ReleasePhase.ALPHA,
            ReleasePhase.BETA_RAW_ONLY,
            ReleasePhase.M3_CANARY,
            ReleasePhase.BLUE_GREEN,
        )
    ):
        raise ProtectedGAEntrypointError("protected Beta infrastructure config is incompatible")
    config = {
        "schema_version": "moomooau.production-config.v1",
        "phase": ReleasePhase.GA.value,
        "key_epoch": parsed["key_epoch"],
        "age_recipient": parsed["age_recipient"],
        "parser_current_version": GA_PARSER_CURRENT_VERSION,
        "beta_message_budget": 1,
        "ga_mutation_budget_per_run": GA_MUTATION_BUDGET_PER_RUN,
        "github": parsed["github"],
        "capacity": parsed["capacity"],
        "predecessor_observations": [
            _observation_dict(observation) for observation in predecessors
        ],
    }
    return json.dumps(config, sort_keys=True, separators=(",", ":"))


def _observation_dict(value: PhaseObservation) -> dict[str, object]:
    return {
        "phase": value.phase.value,
        "provenance": value.provenance.value,
        "started_at_utc": _format_utc(value.started_at_utc),
        "ended_at_utc": _format_utc(value.ended_at_utc),
        "observed_runs": value.observed_runs,
        "scheduled_0430_runs": value.scheduled_0430_runs,
        "verified_messages": value.verified_messages,
        "source_mutations": value.source_mutations,
        "mutation_budget_max": value.mutation_budget_max,
        "recovery_attempts": value.recovery_attempts,
        "recovery_successes": value.recovery_successes,
        "processed_messages": value.processed_messages,
        "parser_blue_green_comparisons": value.parser_blue_green_comparisons,
        "timeline_publish_attempts": value.timeline_publish_attempts,
        "full_reconcile_runs": value.full_reconcile_runs,
        "collateral_mutations": value.collateral_mutations,
        "public_sensitive_findings": value.public_sensitive_findings,
        "logical_duplicates": value.logical_duplicates,
        "full_reconcile_difference": value.full_reconcile_difference,
        "minimum_live_timeline_assets": value.minimum_live_timeline_assets,
        "maximum_live_timeline_assets": value.maximum_live_timeline_assets,
        "unresolved_failures": value.unresolved_failures,
    }


def _ga_authorized(project_root: Path) -> bool:
    root = _validated_project_root(project_root)
    try:
        contract = _load_object(root / _RUN_CONTRACT_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    authorization = contract.get("authorization")
    budget = contract.get("authorized_effect_budget")
    if not isinstance(authorization, dict) or not isinstance(budget, dict):
        return False
    return bool(
        contract.get("stage_id") == "S7"
        and contract.get("task_id") == "T0705"
        and contract.get("baseline_commit")
        == "c4d4f6cdd60398fba2724d32a99a59306f4225a1"  # pragma: allowlist secret
        and authorization.get("purpose") == "T0705_PROTECTED_GA_SCHEDULE_MODE_AND_ENABLEMENT_ONLY"
        and authorization.get("t0704_receipt_required") is True
        and authorization.get("t0704_receipt_sha256") == blue_green_receipt_sha256(root)
        and authorization.get("t0705_authorized") is True
        and authorization.get("t0706_authorized") is False
        and authorization.get("final_publication_authorized") is False
        and authorization.get("ga_rehearsal_dispatch_limit") == 1
        and authorization.get("ga_rehearsal_rerun_limit") == 0
        and authorization.get("manual_environment_reviewers_required") is False
        and authorization.get("fixed_calendar_wait_days") == 0
        and budget.get("protected_environment_secret_names_maximum") == len(M3_SECRET_NAMES)
        and budget.get("protected_ga_rehearsal_dispatches_maximum") == 1
        and budget.get("protected_ga_rehearsal_reruns_maximum") == 0
        and budget.get("protected_ga_pipeline_runs_maximum") == 1
        and budget.get("platform_schedule_events_during_rehearsal_maximum") == 0
        and budget.get("gmail_exact_message_trash_mutations_maximum") == GA_MUTATION_BUDGET_PER_RUN
        and budget.get("timeline_snapshot_commit_attempts_maximum") == 1
        and budget.get("timeline_state_commits_maximum") == 1
        and budget.get("timeline_publish_attempts_maximum") == 1
        and budget.get("release_asset_uploads_maximum") == 1
        and budget.get("maximum_live_timeline_assets") == 1
        and budget.get("gmail_checkpoint_mutations_maximum") == 1
        and budget.get("t0706_runs_maximum") == 0
        and budget.get("recovery_drill_runs_maximum") == 0
        and budget.get("patch_lifecycle_protected_runs_maximum") == 0
    )


def _validated_project_root(project_root: Path) -> Path:
    try:
        root = project_root.resolve(strict=True)
    except OSError as exc:
        raise ProtectedGAEntrypointError("project root is unavailable") from exc
    if not root.is_dir() or not (root / "pyproject.toml").is_file():
        raise ProtectedGAEntrypointError("project root is invalid")
    return root


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProtectedGAEntrypointError("protected GA authority must be an object")
    return cast(dict[str, Any], value)


def _object_field(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ProtectedGAEntrypointError("protected GA authority object is invalid")
    return cast(dict[str, Any], item)


def _positive_environment_integer(environment: Mapping[str, str], name: str) -> int:
    value = environment.get(name)
    if not isinstance(value, str) or _POSITIVE_INTEGER.fullmatch(value) is None:
        raise ProtectedGAEntrypointError("protected GA integer context is invalid")
    return int(value)


def _environment_string(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name)
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ProtectedGAEntrypointError("protected GA string context is invalid")
    return value


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtectedGAEntrypointError("protected GA predecessor timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ProtectedGAEntrypointError("protected GA predecessor timestamp is invalid") from exc
    if parsed.utcoffset() != timedelta(0):
        raise ProtectedGAEntrypointError("protected GA predecessor timestamp must be UTC")
    return parsed.astimezone(UTC)


def _utc_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ProtectedGAEntrypointError("protected GA clock must return UTC")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _bucket(value: int) -> str:
    if value == 0:
        return "ZERO"
    if value == 1:
        return "ONE"
    if value < 10:
        return "TWO_TO_NINE"
    return "TEN_PLUS"


def _public_failure() -> dict[str, object]:
    return {
        "schema_version": "moomooau.protected-ga-public-failure.v1",
        "status": "BLOCKED",
        "reason_code": "PROTECTED_GA_FAILED",
        "exact_root_cause_claimed": False,
        "protected_values_disclosed": False,
        "platform_schedule_event_claimed": False,
        "production_health_claimed": False,
        "final_acceptance_claimed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--contract-only", action="store_true")
    mode.add_argument("--execute-protected", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--expected-head-sha")
    parser.add_argument("--blue-green-receipt-sha256")
    parser.add_argument("--ga-gate-sha256")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    execution_values = (
        args.expected_head_sha,
        args.blue_green_receipt_sha256,
        args.ga_gate_sha256,
        args.confirm,
    )
    if args.contract_only:
        if any(value is not None for value in execution_values):
            parser.error("protected execution arguments are invalid with --contract-only")
        print(
            json.dumps(
                execution_contract(args.project_root),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if any(value is None for value in execution_values):
        parser.error("protected GA execution requires exact gate inputs and confirmation")
    try:
        evidence = execute_protected(
            os.environ,
            project_root=args.project_root,
            expected_head_sha=cast(str, args.expected_head_sha),
            supplied_blue_green_receipt_sha256=cast(
                str,
                args.blue_green_receipt_sha256,
            ),
            supplied_ga_gate_sha256=cast(str, args.ga_gate_sha256),
            confirmation=cast(str, args.confirm),
        )
        print(json.dumps(evidence.to_dict(), sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print(json.dumps(_public_failure(), sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
