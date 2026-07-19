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
]
