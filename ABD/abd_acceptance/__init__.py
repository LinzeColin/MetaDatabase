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

__all__ = [
    "DuplicateKeyError",
    "build_evidence",
    "evaluate_contract",
    "perform_rollback_drill",
    "strict_json_load",
    "write_phase_evidence",
]
