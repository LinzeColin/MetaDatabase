"""Deterministic correlation and platform-capacity primitives for ABD S12/P02."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Dict, Iterable, Mapping, Sequence


ZERO = Decimal("0")
ONE = Decimal("1")


class EquivalentSignalError(ValueError):
    """Raised when a frozen capacity input is malformed or unsafe to count."""


def require_int(value: Any, *, label: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise EquivalentSignalError("%s must be an integer >= %d" % (label, minimum))
    return value


def require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EquivalentSignalError("%s must be a non-empty string" % label)
    return value


def require_decimal(value: Any, *, label: str, minimum: Decimal = ZERO, maximum: Decimal = ONE) -> Decimal:
    if not isinstance(value, str):
        raise EquivalentSignalError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise EquivalentSignalError("%s is not decimal" % label) from exc
    if not parsed.is_finite() or parsed < minimum or parsed > maximum:
        raise EquivalentSignalError("%s is outside [%s, %s]" % (label, minimum, maximum))
    return parsed


def decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def floor_cents(value: Decimal, *, label: str) -> int:
    if not value.is_finite() or value < ZERO:
        raise EquivalentSignalError("%s must be finite and non-negative" % label)
    return int(value.quantize(Decimal("1"), rounding=ROUND_DOWN))


def select_cluster_representatives(
    opportunities: Sequence[Mapping[str, Any]],
    cluster_remaining_cents: Mapping[str, int],
) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    """Count one deterministic representative for every pre-declared correlation cluster."""

    grouped: Dict[str, list[Dict[str, Any]]] = {}
    for raw in opportunities:
        row = dict(raw)
        cluster_id = require_text(row.get("correlation_cluster_id"), label="correlation_cluster_id")
        grouped.setdefault(cluster_id, []).append(row)

    cluster_rows: list[Dict[str, Any]] = []
    representatives: list[Dict[str, Any]] = []
    for cluster_id in sorted(grouped):
        members = grouped[cluster_id]
        remaining = require_int(cluster_remaining_cents.get(cluster_id), label="cluster_remaining_cents")
        ordered = sorted(
            members,
            key=lambda row: (-require_int(row.get("pre_platform_executable_capacity_cents"), label="pre_platform_executable_capacity_cents"), require_text(row.get("opportunity_id"), label="opportunity_id")),
        )
        representative = dict(ordered[0])
        representative["cluster_remaining_capacity_cents"] = remaining
        representative["correlation_adjusted_capacity_cents"] = require_int(
            representative["pre_platform_executable_capacity_cents"],
            label="pre_platform_executable_capacity_cents",
        )
        naive_capacity = sum(
            require_int(member.get("pre_platform_executable_capacity_cents"), label="pre_platform_executable_capacity_cents")
            for member in ordered
        )
        not_counted = [require_text(member.get("opportunity_id"), label="opportunity_id") for member in ordered[1:]]
        cluster_rows.append(
            {
                "cluster_id": cluster_id,
                "member_opportunity_ids": [require_text(member.get("opportunity_id"), label="opportunity_id") for member in ordered],
                "cluster_remaining_capacity_cents": remaining,
                "naive_member_executable_capacity_cents": naive_capacity,
                "correlation_adjusted_capacity_cents": representative["correlation_adjusted_capacity_cents"],
                "representative_opportunity_id": representative["opportunity_id"],
                "not_counted_as_additional_coverage_ids": not_counted,
                "counting_rule": "ONE_REPRESENTATIVE_PER_PREDECLARED_HIGH_CORRELATION_CLUSTER",
            }
        )
        representatives.append(representative)
    return cluster_rows, representatives


def allocate_platform_capacity(
    representatives: Iterable[Mapping[str, Any]],
    platform_remaining_cents: Mapping[str, int],
) -> tuple[list[Dict[str, Any]], Dict[str, int]]:
    """Apply declared platform limits once, in stable identifier order."""

    remaining = {
        require_text(platform_id, label="platform_id"): require_int(capacity, label="platform_remaining_cents")
        for platform_id, capacity in platform_remaining_cents.items()
    }
    allocations: list[Dict[str, Any]] = []
    for raw in sorted(representatives, key=lambda row: require_text(row.get("opportunity_id"), label="opportunity_id")):
        row = dict(raw)
        platform_id = require_text(row.get("platform_id"), label="platform_id")
        if platform_id not in remaining:
            raise EquivalentSignalError("representative references unknown platform: %s" % platform_id)
        requested = require_int(row.get("correlation_adjusted_capacity_cents"), label="correlation_adjusted_capacity_cents")
        before = remaining[platform_id]
        allocated = min(requested, before)
        remaining[platform_id] = before - allocated
        allocations.append(
            {
                "opportunity_id": require_text(row.get("opportunity_id"), label="opportunity_id"),
                "cluster_id": require_text(row.get("correlation_cluster_id"), label="correlation_cluster_id"),
                "platform_id": platform_id,
                "capacity_before_platform_limit_cents": requested,
                "platform_remaining_before_cents": before,
                "final_executable_capacity_cents": allocated,
                "platform_remaining_after_cents": remaining[platform_id],
                "platform_rule": "DETERMINISTIC_DECLARED_REMAINING_CAPACITY_NO_OVERALLOCATION",
            }
        )
    return allocations, remaining
