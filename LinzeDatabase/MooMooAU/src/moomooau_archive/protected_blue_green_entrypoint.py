"""Exact-main protected entrypoint for one Stage 7 T0704 Blue-Green execution.

Before any Secret read, this module validates the immutable T0703 PASS receipt, the explicit
T0704-only Run Contract, the exact first-attempt GitHub context and a same-tree gate digest.
Success emits aggregate-only evidence.  Failure emits one fixed public-safe code without dynamic
exception text, protected identifiers, mailbox counts or private repository values.
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

from .http_transport import StdlibHttpsTransport
from .protected_blue_green import (
    BLUE_GREEN_SECRET_NAMES,
    ProtectedBlueGreenBootstrap,
    ProtectedBlueGreenRunResult,
)
from .protected_m3_entrypoint import _load_beta_predecessors
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
CONTROL_WORKFLOW_REF = (
    "LinzeColin/MetaDatabase/.github/workflows/moomooau-blue-green.yml@refs/heads/main"
)
PROTECTED_ENVIRONMENT = "moomooau-beta"
BLUE_GREEN_CONFIRMATION = "BLUE_GREEN_SAME_RECOVERED_RAW_SHADOW_ONLY"

_M3_RECEIPT_PATH = Path("machine/stages/S7/reviews/t0703/execution-receipt.json")
_M3_RECEIPT_SCHEMA_PATH = Path(
    "machine/stages/S7/schemas/protected-m3-execution-receipt-v1.schema.json"
)
_RUN_CONTRACT_PATH = Path("machine/stages/S7/contracts/run_contract.json")
_SUCCESS_RECEIPT_PATH = Path("machine/stages/S7/reviews/t0704/execution-receipt.json")
_GATE_PATHS = (
    _M3_RECEIPT_PATH,
    _M3_RECEIPT_SCHEMA_PATH,
    _RUN_CONTRACT_PATH,
    Path("machine/stages/S7/contracts/stage7_acceptance_contract.json"),
    Path("src/moomooau_archive/document_parser.py"),
    Path("src/moomooau_archive/blue_green_runtime.py"),
    Path("src/moomooau_archive/github_guard.py"),
    Path("src/moomooau_archive/protected_beta.py"),
    Path("src/moomooau_archive/protected_m3.py"),
    Path("src/moomooau_archive/protected_blue_green.py"),
    Path("src/moomooau_archive/protected_blue_green_entrypoint.py"),
    Path("tests/stage7_support.py"),
    Path("tests/tasks/test_t0704.py"),
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]*$")


class ProtectedBlueGreenEntrypointError(RuntimeError):
    """A T0704 execution prerequisite failed without exposing a protected value."""


class ExactBlueGreenEnvironmentSecretSource:
    """Read only the existing exact eight protected Environment values."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._environment = environment

    def read(self, name: str) -> SecretText:
        if name not in BLUE_GREEN_SECRET_NAMES:
            raise ProtectedBlueGreenEntrypointError(
                "protected Blue-Green Secret name is not allowlisted"
            )
        value = self._environment.get(name)
        if not isinstance(value, str) or not value:
            raise ProtectedBlueGreenEntrypointError(
                "required protected Blue-Green Secret is unavailable"
            )
        return SecretText(value)


@dataclass(frozen=True, slots=True)
class ProtectedBlueGreenGitHubContext:
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
    def from_environment(
        cls,
        environment: Mapping[str, str],
    ) -> ProtectedBlueGreenGitHubContext:
        if (
            environment.get("GITHUB_ACTIONS") != "true"
            or environment.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        ):
            raise ProtectedBlueGreenEntrypointError(
                "protected Blue-Green requires workflow_dispatch"
            )
        context = cls(
            repository_id=_positive_environment_integer(
                environment,
                "GITHUB_REPOSITORY_ID",
            ),
            owner_id=_positive_environment_integer(
                environment,
                "GITHUB_REPOSITORY_OWNER_ID",
            ),
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
            raise ProtectedBlueGreenEntrypointError(
                "protected Blue-Green GitHub context is not allowed"
            )
        return context


@dataclass(frozen=True, slots=True)
class ProtectedBlueGreenExecutionEvidence:
    context: ProtectedBlueGreenGitHubContext
    m3_receipt_sha256: str
    gate_sha256: str
    observation: PhaseObservation
    public_result: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        observation = self.observation
        return {
            "schema_version": "moomooau.protected-blue-green-execution.v1",
            "status": "PROTECTED_BLUE_GREEN_COMPLETED_NOT_FINAL",
            "control": {
                "repository_id": self.context.repository_id,
                "run_id": self.context.run_id,
                "run_attempt": self.context.run_attempt,
                "head_sha": self.context.head_sha,
                "ref": self.context.ref,
                "workflow_ref": self.context.workflow_ref,
                "runner_environment": self.context.runner_environment,
                "environment": self.context.environment_name,
                "m3_receipt_sha256": self.m3_receipt_sha256,
                "blue_green_gate_sha256": self.gate_sha256,
            },
            "phase_observation": {
                "phase": observation.phase.value,
                "provenance": observation.provenance.value,
                "started_at_utc": _format_utc(observation.started_at_utc),
                "ended_at_utc": _format_utc(observation.ended_at_utc),
                "observed_runs": observation.observed_runs,
                "processed_recoveries": observation.recovery_successes,
                "parser_comparisons": observation.parser_blue_green_comparisons,
                "timeline_publish_attempts": observation.timeline_publish_attempts,
                "full_reconcile_runs": observation.full_reconcile_runs,
                "full_reconcile_difference": observation.full_reconcile_difference,
                "unresolved_failures": observation.unresolved_failures,
                "minimum_live_timeline_assets": observation.minimum_live_timeline_assets,
                "maximum_live_timeline_assets": observation.maximum_live_timeline_assets,
                "exact_mailbox_counts_disclosed": False,
            },
            "public_result": self.public_result,
            "boundaries": {
                "maximum_verified_full_raw_reads": 1,
                "gmail_mutations": 0,
                "current_pointer_mutations": 0,
                "candidate_pointer_promotion": False,
                "maximum_live_timeline_assets": 1,
                "schedule_enabled": False,
                "ga_enabled": False,
            },
            "blue_green_gate_status": "PASS",
            "production_health_claimed": False,
            "final_acceptance_claimed": False,
        }


def m3_receipt_sha256(project_root: Path) -> str:
    root = _validated_project_root(project_root)
    path = root / _M3_RECEIPT_PATH
    if not path.is_file() or path.is_symlink():
        raise ProtectedBlueGreenEntrypointError("protected M3 receipt is missing or unsafe")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def blue_green_gate_sha256(project_root: Path) -> str:
    root = _validated_project_root(project_root)
    digest = hashlib.sha256()
    for relative in _GATE_PATHS:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ProtectedBlueGreenEntrypointError(
                "protected Blue-Green gate input is missing or unsafe"
            )
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def execution_contract(project_root: Path) -> dict[str, object]:
    root = _validated_project_root(project_root)
    authorized = _t0704_authorized(root)
    return {
        "schema_version": "moomooau.protected-blue-green-entrypoint-contract.v1",
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
        "required_confirmation": BLUE_GREEN_CONFIRMATION,
        "required_protected_input_count": len(BLUE_GREEN_SECRET_NAMES),
        "protected_input_values_disclosed": False,
        "m3_receipt_path": _M3_RECEIPT_PATH.as_posix(),
        "m3_receipt_sha256": m3_receipt_sha256(root),
        "completion_receipt_path": _SUCCESS_RECEIPT_PATH.as_posix(),
        "completion_receipt_present": (root / _SUCCESS_RECEIPT_PATH).is_file(),
        "same_head_rerun_allowed": False,
        "blue_green_gate_paths": [path.as_posix() for path in _GATE_PATHS],
        "blue_green_gate_sha256": blue_green_gate_sha256(root),
        "blue_green_authorized": authorized,
        "feature_invariants": {
            "same_recovered_raw_required": True,
            "candidate_shadow_only": True,
            "current_pointer_mutations": 0,
            "gmail_mutations": 0,
            "timeline_enabled": authorized,
            "single_live_timeline_required": True,
            "schedule_enabled": False,
            "ga_enabled": False,
            "paired_empty_registries_preserve_safe_deferred_lineage": True,
        },
        "fixed_calendar_wait_days": 0,
        "protected_oracles_executed": 0,
        "production_health_claimed": False,
        "final_acceptance_claimed": False,
    }


def execute_protected(
    environment: Mapping[str, str],
    *,
    project_root: Path,
    expected_head_sha: str,
    supplied_m3_receipt_sha256: str,
    supplied_blue_green_gate_sha256: str,
    confirmation: str,
    bootstrap: ProtectedBlueGreenBootstrap | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ProtectedBlueGreenExecutionEvidence:
    context = ProtectedBlueGreenGitHubContext.from_environment(environment)
    if (
        confirmation != BLUE_GREEN_CONFIRMATION
        or expected_head_sha != context.head_sha
        or _COMMIT.fullmatch(expected_head_sha) is None
        or _SHA256.fullmatch(supplied_m3_receipt_sha256) is None
        or _SHA256.fullmatch(supplied_blue_green_gate_sha256) is None
    ):
        raise ProtectedBlueGreenEntrypointError(
            "protected Blue-Green dispatch confirmation is invalid"
        )
    expected_receipt = m3_receipt_sha256(project_root)
    expected_gate = blue_green_gate_sha256(project_root)
    if (
        supplied_m3_receipt_sha256 != expected_receipt
        or supplied_blue_green_gate_sha256 != expected_gate
    ):
        raise ProtectedBlueGreenEntrypointError("protected Blue-Green same-tree binding differs")
    predecessors = _load_predecessors(project_root)
    if not _t0704_authorized(project_root):
        raise ProtectedBlueGreenEntrypointError("current Run Contract does not authorize T0704")

    now = clock or (lambda: datetime.now(UTC))
    started_at = _utc_now(now)
    active_bootstrap = bootstrap
    if active_bootstrap is None:
        transport = StdlibHttpsTransport()
        active_bootstrap = ProtectedBlueGreenBootstrap(
            ExactBlueGreenEnvironmentSecretSource(environment),
            oauth_transport=transport,
            gmail_transport=transport,
            github_transport=transport,
            clock=now,
        )
    with active_bootstrap.open(predecessor_observations=predecessors) as runtime:
        result = runtime.run()
    ended_at = _utc_now(now)
    observation = _blue_green_observation(result, started_at, ended_at)
    completed = Stage7ReleaseGate().evaluate_completed_phase(observation)
    if completed.status is not GateStatus.READY:
        raise ProtectedBlueGreenEntrypointError("protected Blue-Green aggregate gate is blocked")
    return ProtectedBlueGreenExecutionEvidence(
        context,
        expected_receipt,
        expected_gate,
        observation,
        result.to_public_dict(),
    )


def _load_predecessors(project_root: Path) -> tuple[PhaseObservation, ...]:
    root = _validated_project_root(project_root)
    alpha, beta = _load_beta_predecessors(root)
    try:
        receipt = _load_object(root / _M3_RECEIPT_PATH)
        schema = _load_object(root / _M3_RECEIPT_SCHEMA_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtectedBlueGreenEntrypointError("protected M3 receipt is unreadable") from exc
    if list(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(receipt)
    ):
        raise ProtectedBlueGreenEntrypointError("protected M3 receipt schema is invalid")
    control = _object_field(receipt, "control")
    jobs = _object_field(receipt, "jobs")
    job = _object_field(jobs, "m3_zero_mutation_reconciliation")
    public = _object_field(receipt, "public_result")
    scope = _object_field(receipt, "scope_decision")
    claims = _object_field(receipt, "claims")
    if (
        receipt.get("task_id") != "T0703"
        or receipt.get("stage_acceptance_id") != "S7AC-003"
        or control.get("workflow_event") != "workflow_dispatch"
        or control.get("workflow_attempt") != 1
        or control.get("dispatches_for_head") != 1
        or control.get("reruns") != 0
        or control.get("workflow_head_sha") != control.get("merge_commit_sha")
        or job.get("status") != "PASS"
        or public.get("status") != "PROTECTED_M3_ZERO_MUTATION_RECONCILIATION_COMPLETED_NOT_FINAL"
        or public.get("m3_gate_status") != "PASS"
        or public.get("processed_or_safe_deferred_present") is not True
        or public.get("remote_recovery_one_hundred_percent") is not True
        or public.get("prior_unknown_mutation_reconciled") is not True
        or public.get("collateral_mutations") != 0
        or public.get("timeline_publish_attempts") != 0
        or public.get("unresolved_failures") != 0
        or scope.get("t0703_complete") is not True
        or scope.get("m3_predecessor_satisfied") is not True
        or claims.get("t0703_complete") is not True
        or claims.get("s7ac_003_passed") is not True
        or claims.get("t0704_complete") is not False
        or claims.get("production_health") is not False
        or claims.get("final_acceptance") is not False
    ):
        raise ProtectedBlueGreenEntrypointError(
            "protected M3 receipt does not satisfy T0704 predecessor"
        )
    m3 = PhaseObservation(
        phase=ReleasePhase.M3_CANARY,
        provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
        started_at_utc=_parse_utc(job.get("started_at_utc")),
        ended_at_utc=_parse_utc(job.get("ended_at_utc")),
        observed_runs=2,
        scheduled_0430_runs=0,
        verified_messages=2,
        source_mutations=1,
        mutation_budget_max=1,
        recovery_attempts=2,
        recovery_successes=2,
        processed_messages=2,
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
    predecessors = (alpha, beta, m3)
    promotion = Stage7ReleaseGate().evaluate_promotion(
        ReleasePhase.BLUE_GREEN,
        predecessors,
        beta_message_budget=1,
        parser_current_version="1.0.0",
    )
    if promotion.status is not GateStatus.READY:
        raise ProtectedBlueGreenEntrypointError(
            "protected T0704 predecessor aggregate gate is blocked"
        )
    return predecessors


def _blue_green_observation(
    result: ProtectedBlueGreenRunResult,
    started_at: datetime,
    ended_at: datetime,
) -> PhaseObservation:
    public = result.to_public_dict()
    required_equal = {
        "processed_recoveries": 1,
        "parser_comparisons": 1,
        "timeline_publish_attempts": 1,
        "full_reconcile_runs": 1,
        "full_reconcile_difference": 0,
        "unresolved_comparison_differences": 0,
        "gmail_mutations": 0,
        "current_pointer_mutations": 0,
        "minimum_live_timeline_assets": 1,
        "maximum_live_timeline_assets": 1,
        "fixed_calendar_wait_days": 0,
    }
    if any(public.get(key) != value for key, value in required_equal.items()):
        raise ProtectedBlueGreenEntrypointError(
            "protected Blue-Green result is not evidence-complete"
        )
    return PhaseObservation(
        phase=ReleasePhase.BLUE_GREEN,
        provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
        started_at_utc=started_at,
        ended_at_utc=ended_at,
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


def _t0704_authorized(project_root: Path) -> bool:
    root = _validated_project_root(project_root)
    if (root / _SUCCESS_RECEIPT_PATH).exists():
        return False
    try:
        contract = _load_object(root / _RUN_CONTRACT_PATH)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    authorization = contract.get("authorization")
    budget = contract.get("authorized_effect_budget")
    return bool(
        contract.get("stage_id") == "S7"
        and contract.get("task_id") == "T0704"
        and isinstance(authorization, dict)
        and isinstance(budget, dict)
        and authorization.get("purpose") == "T0704_PROTECTED_BLUE_GREEN_ONLY"
        and authorization.get("t0703_receipt_required") is True
        and authorization.get("blue_green_authorized") is True
        and authorization.get("t0705_authorized") is False
        and authorization.get("final_publication_authorized") is False
        and authorization.get("dispatch_limit") == 1
        and budget.get("protected_blue_green_dispatches_maximum") == 1
        and budget.get("protected_blue_green_reruns_maximum") == 0
        and budget.get("verified_full_raw_message_reads_maximum") == 1
        and budget.get("gmail_mutations_maximum") == 0
        and budget.get("current_pointer_mutations_maximum") == 0
        and budget.get("candidate_processed_shadow_commits_maximum") == 1
        and budget.get("timeline_publish_attempts_maximum") == 1
        and budget.get("maximum_live_timeline_assets") == 1
        and budget.get("scheduled_runs_maximum") == 0
        and budget.get("ga_runs_maximum") == 0
    )


def _validated_project_root(project_root: Path) -> Path:
    try:
        root = project_root.resolve(strict=True)
    except OSError as exc:
        raise ProtectedBlueGreenEntrypointError("project root is unavailable") from exc
    if not root.is_dir() or not (root / "pyproject.toml").is_file():
        raise ProtectedBlueGreenEntrypointError("project root is invalid")
    return root


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProtectedBlueGreenEntrypointError("protected Blue-Green authority must be an object")
    return cast(dict[str, Any], value)


def _object_field(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ProtectedBlueGreenEntrypointError("protected Blue-Green authority object is invalid")
    return cast(dict[str, Any], item)


def _positive_environment_integer(environment: Mapping[str, str], name: str) -> int:
    value = environment.get(name)
    if not isinstance(value, str) or _POSITIVE_INTEGER.fullmatch(value) is None:
        raise ProtectedBlueGreenEntrypointError("protected Blue-Green integer context is invalid")
    return int(value)


def _environment_string(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name)
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ProtectedBlueGreenEntrypointError("protected Blue-Green string context is invalid")
    return value


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtectedBlueGreenEntrypointError(
            "protected Blue-Green predecessor timestamp is invalid"
        )
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ProtectedBlueGreenEntrypointError(
            "protected Blue-Green predecessor timestamp is invalid"
        ) from exc
    if parsed.utcoffset() != timedelta(0):
        raise ProtectedBlueGreenEntrypointError(
            "protected Blue-Green predecessor timestamp must be UTC"
        )
    return parsed.astimezone(UTC)


def _utc_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ProtectedBlueGreenEntrypointError("protected Blue-Green clock must return UTC")
    return value.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _public_failure() -> dict[str, object]:
    return {
        "schema_version": "moomooau.protected-blue-green-public-failure.v1",
        "status": "BLOCKED",
        "reason_code": "PROTECTED_BLUE_GREEN_FAILED",
        "exact_root_cause_claimed": False,
        "protected_values_disclosed": False,
        "gmail_mutation_claimed": False,
        "current_pointer_mutation_claimed": False,
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
    parser.add_argument("--m3-receipt-sha256")
    parser.add_argument("--blue-green-gate-sha256")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    execution_values = (
        args.expected_head_sha,
        args.m3_receipt_sha256,
        args.blue_green_gate_sha256,
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
        parser.error("protected Blue-Green execution requires exact gate inputs and confirmation")
    try:
        evidence = execute_protected(
            os.environ,
            project_root=args.project_root,
            expected_head_sha=args.expected_head_sha,
            supplied_m3_receipt_sha256=args.m3_receipt_sha256,
            supplied_blue_green_gate_sha256=args.blue_green_gate_sha256,
            confirmation=args.confirm,
        )
        print(json.dumps(evidence.to_dict(), sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print(json.dumps(_public_failure(), sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
