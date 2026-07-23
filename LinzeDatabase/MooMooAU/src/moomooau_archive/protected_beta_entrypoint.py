"""Explicit GitHub Actions entrypoint for one protected Raw-only Beta run.

The entrypoint accepts only the six Beta Secrets, binds execution to the owner-dispatched
``main`` workflow in the exact control repository, revalidates the same-tree Alpha gate, and
emits aggregate-only protected evidence.  It has no schedule, M3, Parser, Timeline, Gmail
mutation or general production mode.
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

from .auth import GMAIL_OAUTH_SECRET_NAME
from .canary_runtime import CanaryRunResult
from .http_transport import StdlibHttpsTransport
from .protected_beta import (
    AGE_IDENTITY_SECRET_NAME,
    BETA_CONFIG_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    OPAQUE_ID_KEY_SECRET_NAME,
    SENDER_REGISTRY_SECRET_NAME,
    ProtectedBetaBootstrap,
)
from .release_control import (
    FeatureFlags,
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
CONTROL_WORKFLOW_REF = "LinzeColin/MetaDatabase/.github/workflows/moomooau-beta.yml@refs/heads/main"
PROTECTED_ENVIRONMENT = "moomooau-beta"
RAW_ONLY_CONFIRMATION = "BETA_RAW_ONLY"

BETA_SECRET_NAMES = (
    BETA_CONFIG_SECRET_NAME,
    SENDER_REGISTRY_SECRET_NAME,
    GITHUB_APP_PRIVATE_KEY_SECRET_NAME,
    AGE_IDENTITY_SECRET_NAME,
    OPAQUE_ID_KEY_SECRET_NAME,
    GMAIL_OAUTH_SECRET_NAME,
)

_ALPHA_GATE_PATHS = (
    Path("evidence/tasks/T0701.json"),
    Path("machine/stages/S7/contracts/stage7_acceptance_contract.json"),
    Path("machine/stages/S7/tools/validate_stage7.py"),
    Path("tests/tasks/test_t0701.py"),
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]*$")


class ProtectedBetaEntrypointError(RuntimeError):
    """A protected execution prerequisite failed without exposing a protected value."""


class ExactBetaEnvironmentSecretSource:
    """Read only the six exact Beta Secret values injected into the execution step."""

    def __init__(self, environment: Mapping[str, str]) -> None:
        self._environment = environment

    def read(self, name: str) -> SecretText:
        if name not in BETA_SECRET_NAMES:
            raise ProtectedBetaEntrypointError("protected Beta Secret name is not allowlisted")
        value = self._environment.get(name)
        if not isinstance(value, str) or not value:
            raise ProtectedBetaEntrypointError("required protected Beta Secret is unavailable")
        return SecretText(value)


@dataclass(frozen=True, slots=True)
class ProtectedGitHubContext:
    """Exact non-secret provenance for the protected GitHub-hosted execution."""

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
    def from_environment(cls, environment: Mapping[str, str]) -> ProtectedGitHubContext:
        if (
            environment.get("GITHUB_ACTIONS") != "true"
            or environment.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        ):
            raise ProtectedBetaEntrypointError("protected Beta requires GitHub workflow_dispatch")
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
            raise ProtectedBetaEntrypointError("protected GitHub execution context is not allowed")
        return context


@dataclass(frozen=True, slots=True)
class ProtectedBetaExecutionEvidence:
    """Public-safe aggregate evidence for one successful protected Beta run."""

    context: ProtectedGitHubContext
    alpha_gate_sha256: str
    beta_message_budget: int
    observation: PhaseObservation
    public_result: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        observation = self.observation
        return {
            "schema_version": "moomooau.protected-beta-execution.v1",
            "status": "PROTECTED_BETA_RAW_ONLY_COMPLETED_NOT_FINAL",
            "control": {
                "repository_id": self.context.repository_id,
                "run_id": self.context.run_id,
                "run_attempt": self.context.run_attempt,
                "head_sha": self.context.head_sha,
                "ref": self.context.ref,
                "workflow_ref": self.context.workflow_ref,
                "runner_environment": self.context.runner_environment,
                "environment": self.context.environment_name,
                "alpha_gate_sha256": self.alpha_gate_sha256,
            },
            "beta_message_budget_configured": self.beta_message_budget > 0,
            "phase_observation": _public_observation_dict(
                observation,
                beta_message_budget=self.beta_message_budget,
            ),
            "public_result": self.public_result,
            "boundaries": {
                "processing_enabled": False,
                "m3_enabled": False,
                "timeline_enabled": False,
                "gmail_mutations": 0,
                "processed_writes": 0,
                "timeline_mutations": 0,
            },
            "beta_gate_status": "PASS",
            "m3_executed": False,
            "production_health_claimed": False,
            "final_acceptance_claimed": False,
        }


def alpha_gate_sha256(project_root: Path) -> str:
    """Bind the local Alpha evidence, contract, validator and executable task oracle."""

    root = _validated_project_root(project_root)
    digest = hashlib.sha256()
    for relative in _ALPHA_GATE_PATHS:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ProtectedBetaEntrypointError("Alpha gate authority is missing or unsafe")
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def execution_contract(project_root: Path) -> dict[str, object]:
    """Return the public, non-executing protected Beta contract."""

    flags = FeatureFlags.for_phase(ReleasePhase.BETA_RAW_ONLY)
    return {
        "schema_version": "moomooau.protected-beta-entrypoint-contract.v1",
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
        "required_confirmation": RAW_ONLY_CONFIRMATION,
        "required_secret_names": list(BETA_SECRET_NAMES),
        "alpha_gate_paths": [path.as_posix() for path in _ALPHA_GATE_PATHS],
        "alpha_gate_sha256": alpha_gate_sha256(project_root),
        "feature_flags": flags.to_public_dict(),
        "maximum_source_mutations": 0,
        "maximum_processed_writes": 0,
        "maximum_timeline_mutations": 0,
        "production_health_claimed": False,
    }


def execute_protected(
    environment: Mapping[str, str],
    *,
    project_root: Path,
    expected_head_sha: str,
    supplied_alpha_gate_sha256: str,
    confirmation: str,
    bootstrap: ProtectedBetaBootstrap | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ProtectedBetaExecutionEvidence:
    """Execute exactly one protected Beta run after all non-secret context gates pass."""

    context = ProtectedGitHubContext.from_environment(environment)
    if (
        confirmation != RAW_ONLY_CONFIRMATION
        or expected_head_sha != context.head_sha
        or _COMMIT.fullmatch(expected_head_sha) is None
    ):
        raise ProtectedBetaEntrypointError("protected Beta dispatch confirmation is invalid")
    expected_alpha_gate = alpha_gate_sha256(project_root)
    if supplied_alpha_gate_sha256 != expected_alpha_gate:
        raise ProtectedBetaEntrypointError("protected Alpha gate binding differs")

    now = clock or (lambda: datetime.now(UTC))
    started_at = _utc_now(now)
    alpha = _alpha_observation(started_at)
    active_bootstrap = bootstrap
    if active_bootstrap is None:
        transport = StdlibHttpsTransport()
        active_bootstrap = ProtectedBetaBootstrap(
            ExactBetaEnvironmentSecretSource(environment),
            oauth_transport=transport,
            gmail_transport=transport,
            github_transport=transport,
            clock=now,
        )
    with active_bootstrap.open(predecessor_observations=(alpha,)) as runtime:
        beta_message_budget = runtime.beta_message_budget
        result = runtime.run()
    ended_at = _utc_now(now)
    observation = _beta_observation(result, started_at, ended_at)
    gate = Stage7ReleaseGate().evaluate_completed_phase(
        observation,
        beta_message_budget=beta_message_budget,
    )
    if gate.status is not GateStatus.READY:
        raise ProtectedBetaEntrypointError("protected Beta aggregate gate is blocked")
    return ProtectedBetaExecutionEvidence(
        context=context,
        alpha_gate_sha256=expected_alpha_gate,
        beta_message_budget=beta_message_budget,
        observation=observation,
        public_result=result.to_public_dict(),
    )


def _alpha_observation(observed_at: datetime) -> PhaseObservation:
    return PhaseObservation(
        phase=ReleasePhase.ALPHA,
        provenance=ObservationProvenance.LOCAL_SYNTHETIC,
        started_at_utc=observed_at,
        ended_at_utc=observed_at,
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


def _beta_observation(
    result: CanaryRunResult,
    started_at: datetime,
    ended_at: datetime,
) -> PhaseObservation:
    if result.archived_and_recovered < 1:
        raise ProtectedBetaEntrypointError("protected Beta recovered no verified Raw")
    return PhaseObservation(
        phase=ReleasePhase.BETA_RAW_ONLY,
        provenance=ObservationProvenance.PROTECTED_GITHUB_ACTIONS,
        started_at_utc=started_at,
        ended_at_utc=ended_at,
        observed_runs=1,
        scheduled_0430_runs=0,
        verified_messages=result.archived_and_recovered,
        source_mutations=0,
        mutation_budget_max=0,
        recovery_attempts=result.archived_and_recovered,
        recovery_successes=result.archived_and_recovered,
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


def _public_observation_dict(
    observation: PhaseObservation,
    *,
    beta_message_budget: int,
) -> dict[str, object]:
    return {
        "phase": observation.phase.value,
        "provenance": observation.provenance.value,
        "started_at_utc": _format_utc(observation.started_at_utc),
        "ended_at_utc": _format_utc(observation.ended_at_utc),
        "observed_runs": observation.observed_runs,
        "scheduled_0430_runs": observation.scheduled_0430_runs,
        "verified_within_configured_budget": (
            1 <= observation.verified_messages <= beta_message_budget
        ),
        "raw_recovery_one_hundred_percent": (
            observation.recovery_attempts == observation.verified_messages
            and observation.recovery_successes == observation.recovery_attempts
        ),
        "source_mutations": observation.source_mutations,
        "mutation_budget_max": observation.mutation_budget_max,
        "processed_messages": observation.processed_messages,
        "parser_blue_green_comparisons": observation.parser_blue_green_comparisons,
        "timeline_publish_attempts": observation.timeline_publish_attempts,
        "full_reconcile_runs": observation.full_reconcile_runs,
        "collateral_mutations": observation.collateral_mutations,
        "public_sensitive_findings": observation.public_sensitive_findings,
        "logical_duplicates": observation.logical_duplicates,
        "full_reconcile_difference": observation.full_reconcile_difference,
        "minimum_live_timeline_assets": observation.minimum_live_timeline_assets,
        "maximum_live_timeline_assets": observation.maximum_live_timeline_assets,
        "unresolved_failures": observation.unresolved_failures,
        "exact_mailbox_counts_disclosed": False,
    }


def _validated_project_root(project_root: Path) -> Path:
    try:
        root = project_root.resolve(strict=True)
    except OSError as exc:
        raise ProtectedBetaEntrypointError("project root is unavailable") from exc
    if not root.is_dir() or not (root / "pyproject.toml").is_file():
        raise ProtectedBetaEntrypointError("project root is invalid")
    return root


def _positive_environment_integer(environment: Mapping[str, str], name: str) -> int:
    value = environment.get(name)
    if not isinstance(value, str) or _POSITIVE_INTEGER.fullmatch(value) is None:
        raise ProtectedBetaEntrypointError("protected GitHub integer context is invalid")
    return int(value)


def _environment_string(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name)
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ProtectedBetaEntrypointError("protected GitHub string context is invalid")
    return value


def _utc_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ProtectedBetaEntrypointError("protected Beta clock must return UTC")
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
    parser.add_argument("--alpha-gate-sha256")
    parser.add_argument("--confirm")
    args = parser.parse_args(argv)
    execution_values = (
        args.expected_head_sha,
        args.alpha_gate_sha256,
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
        parser.error("protected execution requires head SHA, Alpha gate and confirmation")
    try:
        evidence = execute_protected(
            os.environ,
            project_root=args.project_root,
            expected_head_sha=args.expected_head_sha,
            supplied_alpha_gate_sha256=args.alpha_gate_sha256,
            confirmation=args.confirm,
        )
        print(json.dumps(evidence.to_dict(), sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "schema_version": "moomooau.protected-beta-execution.v1",
                    "status": "BLOCKED",
                    "reason_code": "PROTECTED_BETA_RUN_FAILED",
                    "production_health_claimed": False,
                    "final_acceptance_claimed": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
