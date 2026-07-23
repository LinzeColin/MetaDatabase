"""Fail-closed Git, LFS and live-asset capacity policy."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

GITHUB_REPOSITORY_RECOMMENDED_BYTES = 10_000_000_000
GITHUB_GIT_OBJECT_RECOMMENDED_BYTES = 1_000_000
GITHUB_GIT_OBJECT_ENFORCED_BYTES = 100_000_000
GITHUB_RELEASE_ASSET_MAXIMUM_BYTES = 2 * 1024 * 1024 * 1024
GIT_REPOSITORY_MUTATION_OVERHEAD_BYTES = 4096


class CapacityError(RuntimeError):
    """Capacity inputs are absent or inconsistent."""


class CapacityState(StrEnum):
    UNKNOWN = "UNKNOWN"
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass(frozen=True, slots=True)
class CapacityLimits:
    """LFS limits are owner-provisioned because they vary by GitHub plan and budget."""

    lfs_storage_budget_bytes: int | None
    lfs_object_maximum_bytes: int | None
    repository_recommended_bytes: int = GITHUB_REPOSITORY_RECOMMENDED_BYTES
    yellow_ratio_percent: int = 70
    red_ratio_percent: int = 90

    def __post_init__(self) -> None:
        optional = (self.lfs_storage_budget_bytes, self.lfs_object_maximum_bytes)
        if any(value is not None and (type(value) is not int or value <= 0) for value in optional):
            raise CapacityError("provisioned LFS limits must be positive integers")
        if (
            type(self.repository_recommended_bytes) is not int
            or self.repository_recommended_bytes <= 0
            or not 0 < self.yellow_ratio_percent < self.red_ratio_percent < 100
        ):
            raise CapacityError("capacity thresholds are invalid")


@dataclass(frozen=True, slots=True)
class CapacitySnapshot:
    git_repository_bytes: int
    lfs_storage_bytes: int
    largest_git_object_bytes: int
    largest_lfs_object_bytes: int
    live_release_asset_bytes: int

    def __post_init__(self) -> None:
        values = (
            self.git_repository_bytes,
            self.lfs_storage_bytes,
            self.largest_git_object_bytes,
            self.largest_lfs_object_bytes,
            self.live_release_asset_bytes,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise CapacityError("capacity observations must be non-negative integers")


@dataclass(frozen=True, slots=True)
class CapacityDemand:
    """Conservative upper bound for one prospective remote mutation group."""

    git_repository_add_bytes: int = 0
    lfs_storage_add_bytes: int = 0
    git_object_bytes: int = 0
    lfs_object_bytes: int = 0
    live_release_asset_bytes: int = 0

    def __post_init__(self) -> None:
        values = (
            self.git_repository_add_bytes,
            self.lfs_storage_add_bytes,
            self.git_object_bytes,
            self.lfs_object_bytes,
            self.live_release_asset_bytes,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise CapacityError("prospective capacity demand must be non-negative integers")

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.git_repository_add_bytes,
                self.lfs_storage_add_bytes,
                self.git_object_bytes,
                self.lfs_object_bytes,
                self.live_release_asset_bytes,
            )
        )

    def combine(self, other: CapacityDemand) -> CapacityDemand:
        if not isinstance(other, CapacityDemand):
            raise CapacityError("capacity demand can combine only with capacity demand")
        return CapacityDemand(
            git_repository_add_bytes=(
                self.git_repository_add_bytes + other.git_repository_add_bytes
            ),
            lfs_storage_add_bytes=self.lfs_storage_add_bytes + other.lfs_storage_add_bytes,
            git_object_bytes=max(self.git_object_bytes, other.git_object_bytes),
            lfs_object_bytes=max(self.lfs_object_bytes, other.lfs_object_bytes),
            live_release_asset_bytes=max(
                self.live_release_asset_bytes,
                other.live_release_asset_bytes,
            ),
        )


@dataclass(frozen=True, slots=True)
class CapacityAssessment:
    state: CapacityState
    write_allowed: bool
    backfill_allowed: bool
    reason_codes: tuple[str, ...]
    observed_snapshot: CapacitySnapshot | None = None
    limits: CapacityLimits | None = None
    prospective_demand: CapacityDemand = CapacityDemand()

    def __post_init__(self) -> None:
        if not self.reason_codes:
            raise CapacityError("capacity assessment needs a reason")
        if self.state in {CapacityState.UNKNOWN, CapacityState.RED} and self.write_allowed:
            raise CapacityError("unknown or red capacity cannot authorize writes")
        if self.state is not CapacityState.GREEN and self.backfill_allowed:
            raise CapacityError("only green capacity can authorize backfill")
        if (self.observed_snapshot is None) != (self.limits is None):
            raise CapacityError("capacity assessment context is incomplete")
        if not isinstance(self.prospective_demand, CapacityDemand):
            raise CapacityError("capacity assessment demand is invalid")


class CapacityPolicy:
    def evaluate(
        self,
        snapshot: CapacitySnapshot,
        limits: CapacityLimits,
        demand: CapacityDemand | None = None,
    ) -> CapacityAssessment:
        if not isinstance(snapshot, CapacitySnapshot) or not isinstance(limits, CapacityLimits):
            raise CapacityError("capacity policy inputs are invalid")
        prospective = demand if demand is not None else CapacityDemand()
        if not isinstance(prospective, CapacityDemand):
            raise CapacityError("prospective capacity demand is invalid")
        if limits.lfs_storage_budget_bytes is None or limits.lfs_object_maximum_bytes is None:
            return CapacityAssessment(
                CapacityState.UNKNOWN,
                False,
                False,
                ("OWNER_LFS_BUDGET_NOT_PROVISIONED",),
                snapshot,
                limits,
                prospective,
            )
        projected = CapacitySnapshot(
            git_repository_bytes=(
                snapshot.git_repository_bytes + prospective.git_repository_add_bytes
            ),
            lfs_storage_bytes=snapshot.lfs_storage_bytes + prospective.lfs_storage_add_bytes,
            largest_git_object_bytes=max(
                snapshot.largest_git_object_bytes,
                prospective.git_object_bytes,
            ),
            largest_lfs_object_bytes=max(
                snapshot.largest_lfs_object_bytes,
                prospective.lfs_object_bytes,
            ),
            live_release_asset_bytes=max(
                snapshot.live_release_asset_bytes,
                prospective.live_release_asset_bytes,
            ),
        )
        reasons: list[str] = []
        hard_red = (
            projected.git_repository_bytes >= limits.repository_recommended_bytes
            or projected.lfs_storage_bytes >= limits.lfs_storage_budget_bytes
            or projected.largest_git_object_bytes >= GITHUB_GIT_OBJECT_ENFORCED_BYTES
            or projected.largest_lfs_object_bytes >= limits.lfs_object_maximum_bytes
            or projected.live_release_asset_bytes >= GITHUB_RELEASE_ASSET_MAXIMUM_BYTES
        )
        if hard_red:
            return CapacityAssessment(
                CapacityState.RED,
                False,
                False,
                ("PLATFORM_OR_PROVISIONED_LIMIT_REACHED",),
                snapshot,
                limits,
                prospective,
            )
        git_percent = 100 * projected.git_repository_bytes // limits.repository_recommended_bytes
        lfs_percent = 100 * projected.lfs_storage_bytes // limits.lfs_storage_budget_bytes
        maximum_percent = max(git_percent, lfs_percent)
        if maximum_percent >= limits.red_ratio_percent:
            return CapacityAssessment(
                CapacityState.RED,
                False,
                False,
                ("RED_CAPACITY_SAFETY_THRESHOLD",),
                snapshot,
                limits,
                prospective,
            )
        if maximum_percent >= limits.yellow_ratio_percent:
            reasons.append("YELLOW_CAPACITY_SAFETY_THRESHOLD")
        if projected.largest_git_object_bytes > GITHUB_GIT_OBJECT_RECOMMENDED_BYTES:
            reasons.append("GIT_OBJECT_ABOVE_RECOMMENDATION")
        if reasons:
            return CapacityAssessment(
                CapacityState.YELLOW,
                True,
                False,
                tuple(sorted(reasons)),
                snapshot,
                limits,
                prospective,
            )
        return CapacityAssessment(
            CapacityState.GREEN,
            True,
            True,
            ("CAPACITY_WITHIN_BUDGET",),
            snapshot,
            limits,
            prospective,
        )


def git_capacity_demand(
    ciphertexts: Iterable[bytes],
    *,
    release_asset_bytes: int = 0,
) -> CapacityDemand:
    """Build a conservative Git capacity bound from already-encrypted payloads."""

    values = tuple(ciphertexts)
    if any(not isinstance(value, bytes) or not value for value in values):
        raise CapacityError("Git capacity payloads must be non-empty ciphertext bytes")
    if type(release_asset_bytes) is not int or release_asset_bytes < 0:
        raise CapacityError("release asset reservation is invalid")
    return CapacityDemand(
        git_repository_add_bytes=sum(
            len(value) + GIT_REPOSITORY_MUTATION_OVERHEAD_BYTES for value in values
        ),
        git_object_bytes=max((len(value) for value in values), default=0),
        live_release_asset_bytes=release_asset_bytes,
    )


def reserved_git_capacity_demand(
    maximum_object_bytes: int,
    *,
    mutation_count: int = 1,
    release_asset_bytes: int = 0,
) -> CapacityDemand:
    """Reserve a fail-closed upper bound where ciphertext exists only inside the action."""

    if (
        type(maximum_object_bytes) is not int
        or maximum_object_bytes <= 0
        or type(mutation_count) is not int
        or mutation_count <= 0
    ):
        raise CapacityError("Git capacity reservation is invalid")
    return CapacityDemand(
        git_repository_add_bytes=mutation_count
        * (maximum_object_bytes + GIT_REPOSITORY_MUTATION_OVERHEAD_BYTES),
        git_object_bytes=maximum_object_bytes,
        live_release_asset_bytes=release_asset_bytes,
    )
