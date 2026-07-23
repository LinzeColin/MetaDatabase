"""Public, deliberately low-information Stage 1 evidence."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Literal

GateState = Literal["PASS", "FAIL", "DEGRADED", "NOT_RUN"]


def build_public_evidence(*, recovery_ok: bool, verified_count: int) -> dict[str, object]:
    gates: dict[str, GateState] = {
        "age_round_trip": "PASS" if recovery_ok else "FAIL",
        "gmail_production": "NOT_RUN",
        "m3": "NOT_RUN",
        "private_remote_recovery": "PASS" if recovery_ok else "FAIL",
        "synthetic_verification": "PASS" if verified_count == 1 else "FAIL",
    }
    root_input = json.dumps(gates, sort_keys=True, separators=(",", ":")).encode("utf-8")
    opaque_root = (
        base64.urlsafe_b64encode(hashlib.sha256(root_input).digest()).rstrip(b"=").decode("ascii")
    )
    return {
        "schema_version": "1.0.0",
        "run_status": "DEGRADED" if recovery_ok else "UNHEALTHY",
        "freshness_bucket": "UNKNOWN",
        "count_bucket": "ONE_TO_NINE" if verified_count else "ZERO",
        "code_version": "stage1-synthetic-v1",
        "parser_versions": [],
        "opaque_evidence_root": opaque_root,
        "gates": gates,
        "failure_code": "STAGE_1_SYNTHETIC_ONLY" if recovery_ok else "SYNTHETIC_RECOVERY_FAILED",
    }
