"""Deterministic, read-only Patch Lifecycle and operations policy for Stage 7.

This module classifies public-repository changes and combines immutable supply-chain,
recovery, capacity, reconciliation, Kill and scope evidence.  It emits only an aggregate
decision.  It has no environment discovery, command execution, network client, deployment,
rollback or Feature Flag mutation surface.

``provenance`` is validated caller input, not a platform attestation.  A READY policy result
therefore remains an owner-approval prerequisite and never proves that a canary or patch ran.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from .capacity import CapacityAssessment, CapacityState
from .kill_switch import KillId
from .release_control import GateStatus, ObservationProvenance
from .stage7_ops import PatchCandidate, PatchLifecycleGate, PatchSurface

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_CONTAINER_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^patch-[0-9a-f]{32}$")
_PROJECT_PREFIX = "LinzeDatabase/MooMooAU/"
_WORKFLOW_PREFIX = ".github/workflows/moomooau-"


class PatchLifecycleError(RuntimeError):
    """Patch policy input or output is malformed or exceeds its authority."""


class PatchImpact(StrEnum):
    ASSURANCE_ONLY = "ASSURANCE_ONLY"
    APPLICATION_RUNTIME = "APPLICATION_RUNTIME"
    DATA_CONTRACT = "DATA_CONTRACT"
    CONTROL_PLANE = "CONTROL_PLANE"
    PRODUCTION_ORCHESTRATION = "PRODUCTION_ORCHESTRATION"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


_PROTECTED_CANARY_IMPACTS = frozenset(
    {
        PatchImpact.APPLICATION_RUNTIME,
        PatchImpact.DATA_CONTRACT,
        PatchImpact.CONTROL_PLANE,
        PatchImpact.PRODUCTION_ORCHESTRATION,
        PatchImpact.SUPPLY_CHAIN,
        PatchImpact.OUT_OF_SCOPE,
    }
)


class PatchLifecycleDecision(StrEnum):
    FREEZE_KEEP_LAST_VERIFIED = "FREEZE_KEEP_LAST_VERIFIED"
    READY_FOR_OWNER_APPROVED_PROMOTION = "READY_FOR_OWNER_APPROVED_PROMOTION"


class OperationsAction(StrEnum):
    DISABLE_PUBLIC_EVIDENCE = "DISABLE_PUBLIC_EVIDENCE"
    FREEZE_PATCH = "FREEZE_PATCH"
    HOLD_ACTIVE_KILL = "HOLD_ACTIVE_KILL"
    HOLD_M3 = "HOLD_M3"
    HOLD_M3_AND_NEW_WRITES = "HOLD_M3_AND_NEW_WRITES"
    KEEP_LAST_VERIFIED_COMMIT = "KEEP_LAST_VERIFIED_COMMIT"
    LIMIT_DERIVED_DATA = "LIMIT_DERIVED_DATA"
    OWNER_APPROVAL_REQUIRED = "OWNER_APPROVAL_REQUIRED"
    PAUSE_PROCESSED_TIMELINE = "PAUSE_PROCESSED_TIMELINE"
    REBUILD_PUBLIC_EVIDENCE = "REBUILD_PUBLIC_EVIDENCE"
    REMOVE_SCOPE_DRIFT = "REMOVE_SCOPE_DRIFT"
    REPAIR_SINGLE_TIMELINE = "REPAIR_SINGLE_TIMELINE"
    STOP_BACKFILL = "STOP_BACKFILL"


@dataclass(frozen=True, slots=True, repr=False)
class PatchChangeSet:
    """Canonical public path set; exact paths never enter the aggregate result."""

    paths: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.paths) is not tuple
            or not self.paths
            or any(not _valid_repository_path(path) for path in self.paths)
            or self.paths != tuple(sorted(set(self.paths)))
        ):
            raise PatchLifecycleError("patch change set is not canonical and repository relative")

    @property
    def surfaces(self) -> tuple[PatchSurface, ...]:
        return tuple(
            sorted({_surface_for(path) for path in self.paths}, key=lambda item: item.value)
        )

    @property
    def impacts(self) -> tuple[PatchImpact, ...]:
        return tuple(
            sorted({_impact_for(path) for path in self.paths}, key=lambda item: item.value)
        )

    @property
    def protected_canary_required(self) -> bool:
        return bool(set(self.impacts).intersection(_PROTECTED_CANARY_IMPACTS))

    @property
    def out_of_scope_path_count(self) -> int:
        return sum(_impact_for(path) is PatchImpact.OUT_OF_SCOPE for path in self.paths)

    @property
    def opaque_root(self) -> str:
        canonical = json.dumps(self.paths, ensure_ascii=False, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()

    def __repr__(self) -> str:
        return (
            "PatchChangeSet(paths=<redacted>, "
            f"count={len(self.paths)}, opaque_root={self.opaque_root!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OperationsReadinessSnapshot:
    capacity: CapacityAssessment
    active_kill_id: KillId | None
    public_evidence_fresh: bool
    full_reconciliation_clean: bool
    protected_recovery_ready: bool
    benefit_over_cost: bool
    live_timeline_assets: int
    private_evidence_findings: int

    def __post_init__(self) -> None:
        booleans = (
            self.public_evidence_fresh,
            self.full_reconciliation_clean,
            self.protected_recovery_ready,
            self.benefit_over_cost,
        )
        if (
            not isinstance(self.capacity, CapacityAssessment)
            or not isinstance(self.capacity.state, CapacityState)
            or type(self.capacity.write_allowed) is not bool
            or type(self.capacity.backfill_allowed) is not bool
            or type(self.capacity.reason_codes) is not tuple
            or not self.capacity.reason_codes
            or any(
                not isinstance(reason, str) or not reason for reason in self.capacity.reason_codes
            )
            or (self.active_kill_id is not None and not isinstance(self.active_kill_id, KillId))
            or any(type(value) is not bool for value in booleans)
            or type(self.live_timeline_assets) is not int
            or self.live_timeline_assets < 0
            or type(self.private_evidence_findings) is not int
            or self.private_evidence_findings < 0
        ):
            raise PatchLifecycleError("operations readiness snapshot is invalid")

    def __repr__(self) -> str:
        return (
            "OperationsReadinessSnapshot(private_values=<redacted>, "
            f"capacity={self.capacity.state.value!r}, "
            f"active_kill={self.active_kill_id.value if self.active_kill_id else None!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class PatchLifecycleRunContract:
    """Exact read-only authority and evidence envelope for one patch decision."""

    run_id: str
    candidate_commit: str
    last_verified_commit: str
    candidate_container_digest: str
    provenance: ObservationProvenance
    predecessor_ready: bool
    candidate: PatchCandidate
    changes: PatchChangeSet
    operations: OperationsReadinessSnapshot
    predecessor_task_id: str = "T0707"
    public_repository_reads_allowed: bool = True
    public_repository_writes_allowed: bool = False
    private_repository_access_allowed: bool = False
    gmail_access_allowed: bool = False
    secret_access_allowed: bool = False
    workflow_dispatches_allowed: bool = False
    deployment_allowed: bool = False
    rollback_execution_allowed: bool = False
    feature_flag_mutations_allowed: bool = False
    m3_mutations_allowed: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provenance, ObservationProvenance)
            or not isinstance(self.candidate, PatchCandidate)
            or not isinstance(self.changes, PatchChangeSet)
            or not isinstance(self.operations, OperationsReadinessSnapshot)
        ):
            raise PatchLifecycleError("patch lifecycle contract exceeds the frozen boundary")
        booleans = (
            self.predecessor_ready,
            self.public_repository_reads_allowed,
            self.public_repository_writes_allowed,
            self.private_repository_access_allowed,
            self.gmail_access_allowed,
            self.secret_access_allowed,
            self.workflow_dispatches_allowed,
            self.deployment_allowed,
            self.rollback_execution_allowed,
            self.feature_flag_mutations_allowed,
            self.m3_mutations_allowed,
        )
        forbidden_authority = booleans[2:]
        local_claims_protected = self.provenance is ObservationProvenance.LOCAL_SYNTHETIC and (
            self.predecessor_ready
            or self.operations.protected_recovery_ready
            or self.candidate.protected_canary_passed
        )
        if (
            not isinstance(self.run_id, str)
            or not isinstance(self.candidate_commit, str)
            or not isinstance(self.last_verified_commit, str)
            or not isinstance(self.candidate_container_digest, str)
            or _RUN_ID.fullmatch(self.run_id) is None
            or _COMMIT.fullmatch(self.candidate_commit) is None
            or _COMMIT.fullmatch(self.last_verified_commit) is None
            or self.candidate_commit == self.last_verified_commit
            or _CONTAINER_DIGEST.fullmatch(self.candidate_container_digest) is None
            or self.predecessor_task_id != "T0707"
            or self.candidate.rollback_commit != self.last_verified_commit
            or self.predecessor_ready is not self.operations.protected_recovery_ready
            or self.candidate.surfaces != self.changes.surfaces
            or self.candidate.protected_canary_required
            is not self.changes.protected_canary_required
            or not all(type(value) is bool for value in booleans)
            or not self.public_repository_reads_allowed
            or any(forbidden_authority)
            or (self.candidate.protected_canary_passed and not self.predecessor_ready)
            or local_claims_protected
        ):
            raise PatchLifecycleError("patch lifecycle contract exceeds the frozen boundary")

    def __repr__(self) -> str:
        return (
            "PatchLifecycleRunContract(paths=<redacted>, "
            f"run_id={self.run_id!r}, provenance={self.provenance.value!r}, "
            f"candidate_commit={self.candidate_commit!r}, "
            f"last_verified_commit={self.last_verified_commit!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class PatchLifecycleRunResult:
    contract: PatchLifecycleRunContract
    status: GateStatus
    decision: PatchLifecycleDecision
    reason_codes: tuple[str, ...]
    required_actions: tuple[OperationsAction, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.contract, PatchLifecycleRunContract):
            raise PatchLifecycleError("patch lifecycle result is inconsistent")
        status, decision, reasons, actions = _evaluate(self.contract)
        if (
            self.status is not status
            or self.decision is not decision
            or self.reason_codes != reasons
            or self.required_actions != actions
        ):
            raise PatchLifecycleError("patch lifecycle result is inconsistent")

    def __repr__(self) -> str:
        return (
            "PatchLifecycleRunResult(paths=<redacted>, private_values=<redacted>, "
            f"status={self.status.value!r}, decision={self.decision.value!r})"
        )

    def to_public_dict(self) -> dict[str, object]:
        contract = self.contract
        return {
            "schema_version": "moomooau.patch-lifecycle-public.v1",
            "run_id": contract.run_id,
            "candidate_commit": contract.candidate_commit,
            "last_verified_commit": contract.last_verified_commit,
            "rollback_commit": contract.candidate.rollback_commit,
            "candidate_container_digest": contract.candidate_container_digest,
            "provenance": contract.provenance.value,
            "status": self.status.value,
            "decision": self.decision.value,
            "reason_codes": list(self.reason_codes),
            "required_actions": [item.value for item in self.required_actions],
            "patch_surfaces": [item.value for item in contract.changes.surfaces],
            "patch_impacts": [item.value for item in contract.changes.impacts],
            "changed_path_count": len(contract.changes.paths),
            "opaque_change_root": contract.changes.opaque_root,
            "protected_canary_required": contract.changes.protected_canary_required,
            "capacity_state": contract.operations.capacity.state.value,
            "active_kill_id": (
                contract.operations.active_kill_id.value
                if contract.operations.active_kill_id is not None
                else None
            ),
            "public_repository_writes": 0,
            "private_repository_calls": 0,
            "gmail_calls": 0,
            "secret_reads": 0,
            "workflow_dispatches": 0,
            "deployments": 0,
            "rollback_executions": 0,
            "feature_flag_mutations": 0,
            "m3_mutations": 0,
            "patch_applied": False,
            "production_health_claimed": False,
            "stage7_completion_claimed": False,
        }


class PatchLifecycleRunner:
    """Return a deterministic policy decision without performing the decision."""

    def evaluate(self, contract: PatchLifecycleRunContract) -> PatchLifecycleRunResult:
        if not isinstance(contract, PatchLifecycleRunContract):
            raise PatchLifecycleError("patch lifecycle run contract is invalid")
        status, decision, reasons, actions = _evaluate(contract)
        return PatchLifecycleRunResult(contract, status, decision, reasons, actions)


def _evaluate(
    contract: PatchLifecycleRunContract,
) -> tuple[
    GateStatus,
    PatchLifecycleDecision,
    tuple[str, ...],
    tuple[OperationsAction, ...],
]:
    reasons = list(PatchLifecycleGate().evaluate(contract.candidate).reason_codes)
    operations = contract.operations
    if contract.provenance is not ObservationProvenance.PROTECTED_GITHUB_ACTIONS:
        reasons.append("PROTECTED_PATCH_LIFECYCLE_NOT_RUN")
    if not contract.predecessor_ready:
        reasons.append("T0707_PROTECTED_PREDECESSOR_NOT_READY")
    if not operations.protected_recovery_ready:
        reasons.append("PROTECTED_RECOVERY_NOT_READY")
    if operations.capacity.state is CapacityState.UNKNOWN:
        reasons.append("CAPACITY_UNKNOWN")
    elif operations.capacity.state is CapacityState.RED:
        reasons.append("CAPACITY_RED")
    if not operations.capacity.write_allowed:
        reasons.append("CAPACITY_WRITE_NOT_AUTHORIZED")
    if operations.active_kill_id is not None:
        reasons.append("ACTIVE_KILL_CRITERION")
    if not operations.public_evidence_fresh:
        reasons.append("PUBLIC_EVIDENCE_STALE")
    if not operations.full_reconciliation_clean:
        reasons.append("FULL_RECONCILIATION_NOT_CLEAN")
    if not operations.benefit_over_cost:
        reasons.append("BENEFIT_OVER_COST_NOT_PROVEN")
    if operations.live_timeline_assets != 1:
        reasons.append("LIVE_TIMELINE_ASSET_COUNT_NOT_ONE")
    if operations.private_evidence_findings:
        reasons.append("PRIVATE_VALUE_IN_PUBLIC_EVIDENCE")
    if contract.changes.out_of_scope_path_count:
        reasons.append("PATCH_PATH_OUTSIDE_MOOMOOAU_SCOPE")
    unique_reasons = tuple(dict.fromkeys(reasons))
    if unique_reasons:
        status = GateStatus.BLOCKED
        decision = PatchLifecycleDecision.FREEZE_KEEP_LAST_VERIFIED
    else:
        status = GateStatus.READY
        decision = PatchLifecycleDecision.READY_FOR_OWNER_APPROVED_PROMOTION
    return status, decision, unique_reasons, _actions(contract, unique_reasons)


def _actions(
    contract: PatchLifecycleRunContract,
    reasons: tuple[str, ...],
) -> tuple[OperationsAction, ...]:
    actions: set[OperationsAction] = set()
    operations = contract.operations
    if reasons:
        actions.update(
            {
                OperationsAction.FREEZE_PATCH,
                OperationsAction.KEEP_LAST_VERIFIED_COMMIT,
            }
        )
    else:
        actions.add(OperationsAction.OWNER_APPROVAL_REQUIRED)
    if operations.capacity.state is CapacityState.YELLOW:
        actions.add(OperationsAction.LIMIT_DERIVED_DATA)
    elif operations.capacity.state in {CapacityState.UNKNOWN, CapacityState.RED}:
        actions.add(OperationsAction.STOP_BACKFILL)
    if not operations.capacity.write_allowed:
        actions.add(OperationsAction.HOLD_M3_AND_NEW_WRITES)
    if operations.active_kill_id is not None:
        actions.add(OperationsAction.HOLD_ACTIVE_KILL)
    if not operations.public_evidence_fresh:
        actions.add(OperationsAction.REBUILD_PUBLIC_EVIDENCE)
    if not operations.full_reconciliation_clean:
        actions.add(OperationsAction.HOLD_M3)
    if not operations.protected_recovery_ready:
        actions.add(OperationsAction.HOLD_M3_AND_NEW_WRITES)
    if not operations.benefit_over_cost:
        actions.add(OperationsAction.PAUSE_PROCESSED_TIMELINE)
    if operations.live_timeline_assets != 1:
        actions.add(OperationsAction.REPAIR_SINGLE_TIMELINE)
    if operations.private_evidence_findings:
        actions.add(OperationsAction.DISABLE_PUBLIC_EVIDENCE)
    if contract.candidate.scope_scan_findings or contract.changes.out_of_scope_path_count:
        actions.add(OperationsAction.REMOVE_SCOPE_DRIFT)
    return tuple(sorted(actions, key=lambda item: item.value))


def _valid_repository_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and value == path.as_posix()
        and all(part not in {"", ".", ".."} for part in path.parts)
        and not any(ord(character) < 32 for character in value)
    )


def _project_relative(path: str) -> str | None:
    return path.removeprefix(_PROJECT_PREFIX) if path.startswith(_PROJECT_PREFIX) else None


def _surface_for(path: str) -> PatchSurface:
    relative = _project_relative(path)
    if path.startswith(_WORKFLOW_PREFIX):
        return PatchSurface.GITHUB_ACTION
    if relative is None:
        return PatchSurface.APPLICATION
    if relative == "pyproject.toml" or relative.startswith("requirements/"):
        return PatchSurface.PYTHON_DEPENDENCY
    if relative.startswith("container/"):
        return PatchSurface.CONTAINER_BASE
    return PatchSurface.APPLICATION


def _impact_for(path: str) -> PatchImpact:
    relative = _project_relative(path)
    if path.startswith(_WORKFLOW_PREFIX):
        return (
            PatchImpact.PRODUCTION_ORCHESTRATION
            if path.endswith("moomooau-production.yml")
            else PatchImpact.SUPPLY_CHAIN
        )
    if relative is None:
        return PatchImpact.OUT_OF_SCOPE
    if (
        relative == "pyproject.toml"
        or relative.startswith("requirements/")
        or relative.startswith("container/")
    ):
        return PatchImpact.SUPPLY_CHAIN
    if relative.startswith("src/"):
        return PatchImpact.APPLICATION_RUNTIME
    if relative.startswith("schemas/"):
        return PatchImpact.DATA_CONTRACT
    if relative.startswith(("machine/", "release/")):
        return PatchImpact.CONTROL_PLANE
    assurance_prefixes = (
        "design/",
        "evidence/",
        "implementation/",
        "inventory/",
        "operations/",
        "prd/",
        "research/",
        "security/",
        "taskpack/",
        "testing/",
        "tests/",
        "文档/",
    )
    if relative.startswith(assurance_prefixes) or relative in {
        ".gitattributes",
        ".gitignore",
        "AGENTS.md",
        "HANDOFF.md",
        "README.md",
        "VERSION",
    }:
        return PatchImpact.ASSURANCE_ONLY
    return PatchImpact.OUT_OF_SCOPE
