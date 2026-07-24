"""Stage 7 recovery-drill and patch-lifecycle gates.

The records contain aggregate results only.  They intentionally cannot carry ciphertext,
plaintext, identities, repository locators, Gmail IDs or exact financial values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .release_control import GateStatus, ObservationProvenance

_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class Stage7OpsError(RuntimeError):
    """An operations observation is malformed or unsafe."""


class RecoveryArtifactRole(StrEnum):
    RAW = "RAW"
    PROCESSED = "PROCESSED"
    TIMELINE = "TIMELINE"


@dataclass(frozen=True, slots=True, repr=False)
class RecoveryDrillObservation:
    provenance: ObservationProvenance
    observed_at_utc: datetime
    attempted_roles: tuple[RecoveryArtifactRole, ...]
    recovered_roles: tuple[RecoveryArtifactRole, ...]
    digest_mismatches: int
    identity_disclosures: int
    persistent_plaintext_objects: int
    private_values_recorded: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provenance, ObservationProvenance)
            or not isinstance(self.observed_at_utc, datetime)
            or type(self.attempted_roles) is not tuple
            or type(self.recovered_roles) is not tuple
            or self.observed_at_utc.tzinfo is None
            or self.observed_at_utc.utcoffset() != timedelta(0)
            or any(not isinstance(role, RecoveryArtifactRole) for role in self.attempted_roles)
            or any(not isinstance(role, RecoveryArtifactRole) for role in self.recovered_roles)
        ):
            raise Stage7OpsError("recovery drill identity, roles or UTC timestamp is invalid")
        counters = (
            self.digest_mismatches,
            self.identity_disclosures,
            self.persistent_plaintext_objects,
            self.private_values_recorded,
        )
        if any(type(value) is not int or value < 0 for value in counters):
            raise Stage7OpsError("recovery drill counters are invalid")
        if len(set(self.attempted_roles)) != len(self.attempted_roles) or len(
            set(self.recovered_roles)
        ) != len(self.recovered_roles):
            raise Stage7OpsError("recovery drill roles must be unique")
        if not set(self.recovered_roles).issubset(self.attempted_roles):
            raise Stage7OpsError("recovered roles must be a subset of attempted roles")

    def __repr__(self) -> str:
        return (
            "RecoveryDrillObservation("
            f"provenance={self.provenance.value!r}, attempted={len(self.attempted_roles)}, "
            f"recovered={len(self.recovered_roles)}, private_values=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class OperationsGateReport:
    status: GateStatus
    reason_codes: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status is GateStatus.READY


class RecoveryDrillGate:
    """Evaluate aggregate evidence; provenance never grants protected credentials."""

    _REQUIRED = frozenset(RecoveryArtifactRole)

    def evaluate(self, observation: RecoveryDrillObservation | None) -> OperationsGateReport:
        reasons: list[str] = []
        if observation is None:
            reasons.append("PROTECTED_RECOVERY_DRILL_NOT_RUN")
        else:
            if observation.provenance is not ObservationProvenance.PROTECTED_GITHUB_ACTIONS:
                reasons.append("PROTECTED_RECOVERY_DRILL_NOT_RUN")
            if frozenset(observation.attempted_roles) != self._REQUIRED:
                reasons.append("RECOVERY_ARTIFACT_SET_INCOMPLETE")
            if frozenset(observation.recovered_roles) != self._REQUIRED:
                reasons.append("RECOVERY_SUCCESS_NOT_ONE_HUNDRED_PERCENT")
            if observation.digest_mismatches:
                reasons.append("RECOVERY_DIGEST_MISMATCH")
            if observation.identity_disclosures:
                reasons.append("RECOVERY_IDENTITY_DISCLOSED")
            if observation.persistent_plaintext_objects:
                reasons.append("RECOVERY_PLAINTEXT_PERSISTED")
            if observation.private_values_recorded:
                reasons.append("RECOVERY_EVIDENCE_CONTAINS_PRIVATE_VALUES")
        unique = tuple(dict.fromkeys(reasons))
        return OperationsGateReport(
            GateStatus.READY if not unique else GateStatus.BLOCKED,
            unique,
        )


class PatchSurface(StrEnum):
    PYTHON_DEPENDENCY = "PYTHON_DEPENDENCY"
    GITHUB_ACTION = "GITHUB_ACTION"
    CONTAINER_BASE = "CONTAINER_BASE"
    APPLICATION = "APPLICATION"


@dataclass(frozen=True, slots=True)
class PatchCandidate:
    surfaces: tuple[PatchSurface, ...]
    rollback_commit: str
    candidate_commit_verified: bool
    rollback_commit_verified: bool
    immutable_pin_verified: bool
    hash_lock_verified: bool
    sbom_verified: bool
    reproducible_build_verified: bool
    build_provenance_verified: bool
    full_test_suite_passed: bool
    dependency_audit_verified: bool
    high_or_critical_findings: int
    secret_scan_findings: int
    scope_scan_findings: int
    frozen_baseline_verified: bool
    synthetic_recovery_passed: bool
    protected_canary_required: bool
    protected_canary_passed: bool

    def __post_init__(self) -> None:
        booleans = (
            self.immutable_pin_verified,
            self.candidate_commit_verified,
            self.rollback_commit_verified,
            self.hash_lock_verified,
            self.sbom_verified,
            self.reproducible_build_verified,
            self.build_provenance_verified,
            self.full_test_suite_passed,
            self.dependency_audit_verified,
            self.frozen_baseline_verified,
            self.synthetic_recovery_passed,
            self.protected_canary_required,
            self.protected_canary_passed,
        )
        counters = (
            self.high_or_critical_findings,
            self.secret_scan_findings,
            self.scope_scan_findings,
        )
        if (
            type(self.surfaces) is not tuple
            or not self.surfaces
            or any(not isinstance(surface, PatchSurface) for surface in self.surfaces)
            or self.surfaces != tuple(sorted(set(self.surfaces), key=lambda item: item.value))
            or not isinstance(self.rollback_commit, str)
            or _COMMIT.fullmatch(self.rollback_commit) is None
            or any(type(value) is not bool for value in booleans)
            or any(type(value) is not int or value < 0 for value in counters)
            or (not self.protected_canary_required and self.protected_canary_passed)
        ):
            raise Stage7OpsError("patch candidate contract is invalid")


class PatchLifecycleGate:
    """A patch is ready only after immutable supply-chain and recovery closure."""

    def evaluate(self, candidate: PatchCandidate) -> OperationsGateReport:
        reasons: list[str] = []
        if not candidate.candidate_commit_verified:
            reasons.append("CANDIDATE_COMMIT_NOT_VERIFIED")
        if not candidate.rollback_commit_verified:
            reasons.append("ROLLBACK_COMMIT_NOT_VERIFIED")
        if not candidate.immutable_pin_verified:
            reasons.append("IMMUTABLE_PIN_NOT_VERIFIED")
        if not candidate.hash_lock_verified:
            reasons.append("HASH_LOCK_NOT_VERIFIED")
        if not candidate.sbom_verified:
            reasons.append("SBOM_NOT_VERIFIED")
        if not candidate.reproducible_build_verified:
            reasons.append("REPRODUCIBLE_BUILD_NOT_VERIFIED")
        if not candidate.build_provenance_verified:
            reasons.append("BUILD_PROVENANCE_NOT_VERIFIED")
        if not candidate.full_test_suite_passed:
            reasons.append("FULL_TEST_SUITE_NOT_PASSED")
        if not candidate.dependency_audit_verified:
            reasons.append("DEPENDENCY_AUDIT_NOT_VERIFIED")
        if candidate.high_or_critical_findings:
            reasons.append("HIGH_OR_CRITICAL_FINDING_OPEN")
        if candidate.secret_scan_findings:
            reasons.append("SECRET_SCAN_FINDING_OPEN")
        if candidate.scope_scan_findings:
            reasons.append("NON_GOAL_SCOPE_FINDING_OPEN")
        if not candidate.frozen_baseline_verified:
            reasons.append("FROZEN_BASELINE_NOT_VERIFIED")
        if not candidate.synthetic_recovery_passed:
            reasons.append("SYNTHETIC_RECOVERY_NOT_PASSED")
        if candidate.protected_canary_required and not candidate.protected_canary_passed:
            reasons.append("PROTECTED_PATCH_CANARY_NOT_PASSED")
        unique = tuple(reasons)
        return OperationsGateReport(
            GateStatus.READY if not unique else GateStatus.BLOCKED,
            unique,
        )
