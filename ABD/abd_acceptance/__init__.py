"""ABD deterministic acceptance oracles.

Proprietary project code. No order-submission capability is implemented here.
"""

from .canonical_facts import (
    DuplicateKeyError,
    build_evidence,
    evaluate_contract,
    perform_rollback_drill,
    strict_json_load,
    write_phase_evidence,
)
from .authorization import (
    build_evidence as build_authorization_evidence,
    evaluate_contract as evaluate_authorization_contract,
    perform_rollback_drill as perform_authorization_rollback_drill,
    write_phase_evidence as write_authorization_phase_evidence,
)
from .budget import (
    build_evidence as build_budget_evidence,
    evaluate_contract as evaluate_budget_contract,
    perform_rollback_drill as perform_budget_rollback_drill,
    render_scan_report,
    scan_dependency_budget,
    write_phase_evidence as write_budget_phase_evidence,
    write_scan_report,
)

__all__ = [
    "DuplicateKeyError",
    "build_evidence",
    "evaluate_contract",
    "perform_rollback_drill",
    "strict_json_load",
    "write_phase_evidence",
    "build_authorization_evidence",
    "evaluate_authorization_contract",
    "perform_authorization_rollback_drill",
    "write_authorization_phase_evidence",
    "build_budget_evidence",
    "evaluate_budget_contract",
    "perform_budget_rollback_drill",
    "render_scan_report",
    "scan_dependency_budget",
    "write_budget_phase_evidence",
    "write_scan_report",
]
