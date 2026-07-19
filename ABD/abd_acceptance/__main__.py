from __future__ import annotations

import argparse
import json
from pathlib import Path

from .authorization import write_phase_evidence as write_authorization_phase_evidence
from .budget import write_phase_evidence as write_budget_phase_evidence
from .canonical_facts import write_phase_evidence as write_canonical_phase_evidence
from .external_consent import write_phase_evidence as write_external_consent_phase_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="ABD fail-closed acceptance oracle")
    parser.add_argument("--contract", required=True, help="acceptance contract id")
    parser.add_argument(
        "--evidence",
        default="machine/evidence",
        help="evidence directory, relative to --root unless absolute",
    )
    parser.add_argument("--root", default=".", help="ABD project root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    evidence_dir = Path(args.evidence)
    if not evidence_dir.is_absolute():
        evidence_dir = root / evidence_dir

    writers = {
        "AC-S00-P01": write_canonical_phase_evidence,
        "AC-S00-P02": write_authorization_phase_evidence,
        "AC-S00-P03": write_budget_phase_evidence,
        "AC-S00-P04": write_external_consent_phase_evidence,
    }
    if args.contract not in writers:
        parser.error("contract is not implemented: %s" % args.contract)
    result = writers[args.contract](root, evidence_dir)
    print(
        json.dumps(
            {
                "contract_id": result["contract_id"],
                "status": result["status"],
                "evidence": result["evidence_path"],
                "evidence_sha256": result["evidence_sha256"],
                "next": result["next"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
